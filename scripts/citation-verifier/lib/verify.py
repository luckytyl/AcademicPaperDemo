"""Citation verification engine — detect hallucinated references.

Verifies each BibTeX entry against real academic APIs using a four-layer strategy:

  L2:  DOI resolution      — CrossRef ``/works/{doi}`` + DataCite fallback
  L3a: OpenAlex title      — title.search (10K/day, generous limits)
  L1:  arXiv ID lookup     — direct ``id_list`` query to arXiv API
  L3b: Semantic Scholar    — title search (last resort)

Classifications:
  - VERIFIED:     API confirms existence + title similarity ≥ 0.80
  - SUSPICIOUS:   Found but metadata diverges (0.50 ≤ sim < 0.80)
  - HALLUCINATED: Not found via any API or sim < 0.50
  - SKIPPED:      Entry cannot be verified (no title, or all APIs unreachable)

Results are cached in .citation_verify_cache/ (or CITATION_VERIFY_CACHE_DIR env var) to avoid re-querying known papers.

Zero external dependencies — stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Sequence

from .models import Author, Paper

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public enums & data classes
# ---------------------------------------------------------------------------


class VerifyStatus(str, Enum):
    """Verification outcome for a single citation."""
    VERIFIED = "verified"
    SUSPICIOUS = "suspicious"
    HALLUCINATED = "hallucinated"
    SKIPPED = "skipped"


@dataclass
class CitationResult:
    """Verification result for one BibTeX entry."""
    cite_key: str
    title: str
    status: VerifyStatus
    confidence: float        # 0.0–1.0
    method: str              # "doi" | "openalex" | "arxiv_id" | "title_search" | "skipped"
    details: str = ""
    matched_paper: Paper | None = None
    relevance_score: float | None = None

    def to_dict(self) -> dict[str, object]:
        d: dict[str, object] = {
            "cite_key": self.cite_key,
            "title": self.title,
            "status": self.status.value,
            "confidence": round(self.confidence, 3),
            "method": self.method,
            "details": self.details,
        }
        if self.relevance_score is not None:
            d["relevance_score"] = round(self.relevance_score, 2)
        if self.matched_paper:
            d["matched_paper"] = {
                "title": self.matched_paper.title,
                "authors": [a.name for a in self.matched_paper.authors],
                "year": self.matched_paper.year,
                "source": self.matched_paper.source,
            }
        return d


@dataclass
class VerificationReport:
    """Aggregate report for all citations in a paper."""
    total: int = 0
    verified: int = 0
    suspicious: int = 0
    hallucinated: int = 0
    skipped: int = 0
    results: list[CitationResult] = field(default_factory=list)

    @property
    def integrity_score(self) -> float:
        """Fraction of verifiable citations that are verified (0.0–1.0)."""
        verifiable = self.total - self.skipped
        if verifiable <= 0:
            return 1.0
        return round(self.verified / verifiable, 3)

    def to_dict(self) -> dict[str, object]:
        return {
            "summary": {
                "total": self.total,
                "verified": self.verified,
                "suspicious": self.suspicious,
                "hallucinated": self.hallucinated,
                "skipped": self.skipped,
                "integrity_score": self.integrity_score,
            },
            "results": [r.to_dict() for r in self.results],
        }


# ---------------------------------------------------------------------------
# BibTeX parsing
# ---------------------------------------------------------------------------

_ENTRY_RE = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,\s*(.*?)\n\}", re.DOTALL)
_FIELD_RE = re.compile(r"(\w+)\s*=\s*\{([^}]*)\}", re.DOTALL)


def parse_bibtex_entries(bib_text: str) -> list[dict[str, str]]:
    """Parse BibTeX text into a list of field dicts.

    Each dict contains at least ``key`` and ``type``, plus any parsed fields
    (``title``, ``author``, ``year``, ``doi``, ``eprint``, ``url``, …).
    """
    entries: list[dict[str, str]] = []
    for m in _ENTRY_RE.finditer(bib_text):
        entry: dict[str, str] = {
            "type": m.group(1).lower(),
            "key": m.group(2).strip(),
        }
        for fm in _FIELD_RE.finditer(m.group(3)):
            entry[fm.group(1).lower()] = fm.group(2).strip()
        entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Title similarity
# ---------------------------------------------------------------------------


def title_similarity(a: str, b: str) -> float:
    """Word-overlap Jaccard-ish similarity between two titles (0.0–1.0)."""
    def _words(t: str) -> set[str]:
        return set(re.sub(r"[^a-z0-9\s]", "", t.lower()).split()) - {""}
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(len(wa), len(wb))


# ---------------------------------------------------------------------------
# Result cache
# ---------------------------------------------------------------------------

def _get_cache_dir() -> Path:
    """缓存目录：优先用环境变量，回退到项目目录下。"""
    env_dir = os.environ.get("CITATION_VERIFY_CACHE_DIR")
    if env_dir:
        return Path(env_dir)
    return Path(os.getcwd()) / ".citation_verify_cache"


_CACHE_DIR = _get_cache_dir()


def _cache_key(title: str) -> str:
    return hashlib.sha256(title.lower().strip().encode()).hexdigest()[:16]


def _read_cache(title: str) -> CitationResult | None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = _CACHE_DIR / f"{_cache_key(title)}.json"
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            return CitationResult(
                cite_key=data.get("cite_key", ""),
                title=data.get("title", title),
                status=VerifyStatus(data["status"]),
                confidence=data["confidence"],
                method=data["method"],
                details=data.get("details", ""),
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            return None
    return None


def _write_cache(title: str, result: CitationResult) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = _CACHE_DIR / f"{_cache_key(title)}.json"
    cache_file.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# L2: DOI verification via CrossRef + DataCite fallback
# ---------------------------------------------------------------------------

_CROSSREF_API = "https://api.crossref.org/works"
_DATACITE_API = "https://api.datacite.org/dois"
_TIMEOUT = 20


def verify_by_doi(doi: str, expected_title: str) -> CitationResult | None:
    """Verify a DOI via CrossRef, with DataCite fallback for arXiv DOIs."""
    encoded = urllib.parse.quote(doi, safe="")
    url = f"{_CROSSREF_API}/{encoded}"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "CitationVerifier/1.0 (mailto:research@example.com)",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            if doi.startswith("10.48550/") or doi.startswith("10.5281/"):
                return _verify_doi_datacite(doi, expected_title)
            return CitationResult(
                cite_key="", title=expected_title,
                status=VerifyStatus.HALLUCINATED, confidence=0.9,
                method="doi", details=f"DOI {doi} not found (HTTP 404)",
            )
        return None
    except Exception:
        return None

    titles = body.get("message", {}).get("title", [])
    found_title = titles[0] if titles else ""
    if not found_title:
        return CitationResult(
            cite_key="", title=expected_title,
            status=VerifyStatus.VERIFIED, confidence=0.85,
            method="doi", details=f"DOI {doi} resolves via CrossRef (no title comparison)",
        )
    sim = title_similarity(expected_title, found_title)
    status = VerifyStatus.VERIFIED if sim >= 0.80 else VerifyStatus.SUSPICIOUS
    return CitationResult(
        cite_key="", title=expected_title,
        status=status, confidence=sim, method="doi",
        details=f"CrossRef: '{found_title}' (sim={sim:.2f})",
    )


def _verify_doi_datacite(doi: str, expected_title: str) -> CitationResult | None:
    encoded = urllib.parse.quote(doi, safe="")
    url = f"{_DATACITE_API}/{encoded}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "CitationVerifier/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return CitationResult(
                cite_key="", title=expected_title,
                status=VerifyStatus.HALLUCINATED, confidence=0.9,
                method="doi", details=f"DOI {doi} not found via CrossRef or DataCite",
            )
        return None
    except Exception:
        return None

    attrs = body.get("data", {}).get("attributes", {})
    dc_titles = attrs.get("titles", [])
    found_title = dc_titles[0].get("title", "") if dc_titles else ""
    if not found_title:
        return CitationResult(
            cite_key="", title=expected_title,
            status=VerifyStatus.VERIFIED, confidence=0.85,
            method="doi", details=f"DOI {doi} resolves via DataCite",
        )
    sim = title_similarity(expected_title, found_title)
    status = VerifyStatus.VERIFIED if sim >= 0.80 else VerifyStatus.SUSPICIOUS
    return CitationResult(
        cite_key="", title=expected_title,
        status=status, confidence=sim, method="doi",
        details=f"DataCite: '{found_title}' (sim={sim:.2f})",
    )


# ---------------------------------------------------------------------------
# L3a: OpenAlex title search
# ---------------------------------------------------------------------------

_OPENALEX_API = "https://api.openalex.org/works"
_OPENALEX_EMAIL = "research@example.com"


def verify_by_openalex(title: str) -> CitationResult | None:
    """Verify a paper via OpenAlex title search (10K/day, no key needed)."""
    params = urllib.parse.urlencode({
        "filter": f"title.search:{title}",
        "per_page": "5",
        "mailto": _OPENALEX_EMAIL,
    })
    url = f"{_OPENALEX_API}?{params}"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": f"CitationVerifier/1.0 (mailto:{_OPENALEX_EMAIL})",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.debug("OpenAlex search failed for %r: %s", title, exc)
        return None

    results = body.get("results", [])
    if not results:
        return CitationResult(
            cite_key="", title=title,
            status=VerifyStatus.HALLUCINATED, confidence=0.7,
            method="openalex", details="No results found via OpenAlex",
        )

    best_sim = 0.0
    best_title = ""
    for r in results:
        found = r.get("title", "")
        if found:
            sim = title_similarity(title, found)
            if sim > best_sim:
                best_sim = sim
                best_title = found

    if best_sim >= 0.80:
        return CitationResult(
            cite_key="", title=title,
            status=VerifyStatus.VERIFIED, confidence=best_sim,
            method="openalex", details=f"OpenAlex: '{best_title}'",
        )
    elif best_sim >= 0.50:
        return CitationResult(
            cite_key="", title=title,
            status=VerifyStatus.SUSPICIOUS, confidence=best_sim,
            method="openalex", details=f"Partial match via OpenAlex (sim={best_sim:.2f}): '{best_title}'",
        )
    else:
        return CitationResult(
            cite_key="", title=title,
            status=VerifyStatus.HALLUCINATED, confidence=0.7,
            method="openalex", details="No close match found via OpenAlex",
        )


# ---------------------------------------------------------------------------
# L1: arXiv ID verification
# ---------------------------------------------------------------------------

_ARXIV_API = "https://export.arxiv.org/api/query"
_ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}


def verify_by_arxiv_id(arxiv_id: str, expected_title: str) -> CitationResult | None:
    """Look up a paper by arXiv ID and compare titles."""
    params = urllib.parse.urlencode({"id_list": arxiv_id, "max_results": "1"})
    url = f"{_ARXIV_API}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CitationVerifier/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read().decode("utf-8")
    except Exception as exc:
        logger.debug("arXiv ID verification failed for %s: %s", arxiv_id, exc)
        return None

    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None

    entries = root.findall("atom:entry", _ARXIV_NS)
    if not entries:
        return CitationResult(
            cite_key="", title=expected_title,
            status=VerifyStatus.HALLUCINATED, confidence=0.9,
            method="arxiv_id", details=f"arXiv ID {arxiv_id} not found",
        )

    entry = entries[0]
    found_title_el = entry.find("atom:title", _ARXIV_NS)
    found_title = re.sub(r"\s+", " ", (found_title_el.text or "").strip()) if found_title_el is not None else ""
    entry_id = entry.findtext("atom:id", "", _ARXIV_NS)

    if "api/errors" in entry_id or not found_title or found_title.lower() == "error":
        return CitationResult(
            cite_key="", title=expected_title,
            status=VerifyStatus.HALLUCINATED, confidence=0.9,
            method="arxiv_id", details=f"arXiv ID {arxiv_id} returned error",
        )

    sim = title_similarity(expected_title, found_title)
    status = VerifyStatus.VERIFIED if sim >= 0.80 else VerifyStatus.SUSPICIOUS
    return CitationResult(
        cite_key="", title=expected_title,
        status=status, confidence=sim, method="arxiv_id",
        details=f"arXiv: '{found_title}' (sim={sim:.2f})",
    )


# ---------------------------------------------------------------------------
# L3b: Title search via Semantic Scholar + arXiv (last resort)
# ---------------------------------------------------------------------------


def verify_by_title_search(title: str, *, s2_api_key: str = "") -> CitationResult | None:
    """Search for a paper by title across S2 + arXiv."""
    # Inline minimal search to avoid circular imports
    from .arxiv_client import search_arxiv
    from .semantic_scholar import search_semantic_scholar

    results: list[Paper] = []
    try:
        results.extend(search_semantic_scholar(title, limit=5, api_key=s2_api_key))
    except Exception:
        pass
    try:
        results.extend(search_arxiv(title, limit=5))
    except Exception:
        pass

    if not results:
        return CitationResult(
            cite_key="", title=title,
            status=VerifyStatus.HALLUCINATED, confidence=0.7,
            method="title_search", details="No results found via S2 + arXiv",
        )

    best_sim = 0.0
    best_paper: Paper | None = None
    for paper in results:
        sim = title_similarity(title, paper.title)
        if sim > best_sim:
            best_sim = sim
            best_paper = paper

    if best_sim >= 0.80:
        return CitationResult(
            cite_key="", title=title,
            status=VerifyStatus.VERIFIED, confidence=best_sim,
            method="title_search",
            details=f"Found: '{best_paper.title}'" if best_paper else "",
            matched_paper=best_paper,
        )
    elif best_sim >= 0.50:
        return CitationResult(
            cite_key="", title=title,
            status=VerifyStatus.SUSPICIOUS, confidence=best_sim,
            method="title_search",
            details=f"Partial match (sim={best_sim:.2f}): '{best_paper.title}'" if best_paper else "",
            matched_paper=best_paper,
        )
    else:
        return CitationResult(
            cite_key="", title=title,
            status=VerifyStatus.HALLUCINATED, confidence=1.0 - best_sim,
            method="title_search",
            details=f"Best match too weak (sim={best_sim:.2f})" + (f": '{best_paper.title}'" if best_paper else ""),
        )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def verify_citations(
    bib_text: str,
    *,
    s2_api_key: str = "",
    inter_verify_delay: float = 1.5,
) -> VerificationReport:
    """Verify all BibTeX entries against real academic APIs.

    Verification order (optimised to minimise arXiv API pressure):
      1. CrossRef DOI (fast, 50 req/s)
      2. OpenAlex title search (10K/day)
      3. arXiv ID (only if DOI + OpenAlex both fail, 1.5s/req)
      4. Semantic Scholar title search (last resort)

    Parameters
    ----------
    bib_text : str
        Raw BibTeX string.
    s2_api_key : str
        Optional Semantic Scholar API key for faster L3b search.
    inter_verify_delay : float
        Seconds between API calls for arXiv (rate limiting).
    """
    entries = parse_bibtex_entries(bib_text)
    report = VerificationReport(total=len(entries))

    _DELAY_CROSSREF = 0.3
    _DELAY_OPENALEX = 0.2
    _DELAY_ARXIV = inter_verify_delay
    api_call_count = 0

    for i, entry in enumerate(entries):
        key = entry.get("key", f"unknown_{i}")
        title = entry.get("title", "")
        arxiv_id = entry.get("eprint", "")
        doi = entry.get("doi", "")

        if not title:
            result = CitationResult(
                cite_key=key, title="",
                status=VerifyStatus.SKIPPED, confidence=0.0,
                method="skipped", details="No title in BibTeX entry",
            )
            report.skipped += 1
            report.results.append(result)
            continue

        # Check cache first
        cached = _read_cache(title)
        if cached is not None:
            cached.cite_key = key
            report.results.append(cached)
            _tally(report, cached.status)
            logger.debug("[cache] HIT [%s] %r → %s", key, title[:50], cached.status.value)
            continue

        result: CitationResult | None = None

        # L2: DOI via CrossRef (fastest)
        if result is None and doi:
            if api_call_count > 0:
                time.sleep(_DELAY_CROSSREF)
            result = verify_by_doi(doi, title)
            api_call_count += 1
            if result:
                logger.info("L2 DOI [%s] %s → %s (%.2f)", key, doi, result.status.value, result.confidence)

        # L3a: OpenAlex title (high rate limit)
        if result is None:
            if api_call_count > 0:
                time.sleep(_DELAY_OPENALEX)
            result = verify_by_openalex(title)
            api_call_count += 1
            if result:
                logger.info("L3a OpenAlex [%s] %r → %s (%.2f)", key, title[:50], result.status.value, result.confidence)

        # L1: arXiv ID (only if above failed)
        if result is None and arxiv_id:
            if api_call_count > 0:
                time.sleep(_DELAY_ARXIV)
            result = verify_by_arxiv_id(arxiv_id, title)
            api_call_count += 1
            if result:
                logger.info("L1 arXiv [%s] %s → %s (%.2f)", key, arxiv_id, result.status.value, result.confidence)

        # L3b: S2 title search (last resort)
        if result is None:
            result = verify_by_title_search(title, s2_api_key=s2_api_key)
            api_call_count += 1
            if result:
                logger.info("L3b S2 [%s] %r → %s (%.2f)", key, title[:50], result.status.value, result.confidence)

        # All layers failed
        if result is None:
            result = CitationResult(
                cite_key=key, title=title,
                status=VerifyStatus.SKIPPED, confidence=0.0,
                method="skipped", details="All verification methods failed (network error?)",
            )

        result = CitationResult(
            cite_key=key, title=result.title,
            status=result.status, confidence=result.confidence,
            method=result.method, details=result.details,
            matched_paper=result.matched_paper,
        )

        if result.status != VerifyStatus.SKIPPED:
            _write_cache(title, result)

        _tally(report, result.status)
        report.results.append(result)

    return report


def _tally(report: VerificationReport, status: VerifyStatus) -> None:
    if status == VerifyStatus.VERIFIED:
        report.verified += 1
    elif status == VerifyStatus.SUSPICIOUS:
        report.suspicious += 1
    elif status == VerifyStatus.HALLUCINATED:
        report.hallucinated += 1
    else:
        report.skipped += 1


# ---------------------------------------------------------------------------
# Post-processing helpers
# ---------------------------------------------------------------------------


def filter_verified_bibtex(
    bib_text: str,
    report: VerificationReport,
    *,
    include_suspicious: bool = True,
) -> str:
    """Return a cleaned BibTeX string with only verified entries.

    Parameters
    ----------
    include_suspicious : bool
        If True (default), keep SUSPICIOUS entries alongside VERIFIED.
        If False, only keep VERIFIED entries.
    """
    keep_keys: set[str] = set()
    for r in report.results:
        if r.status == VerifyStatus.VERIFIED:
            keep_keys.add(r.cite_key)
        elif r.status == VerifyStatus.SUSPICIOUS and include_suspicious:
            keep_keys.add(r.cite_key)
        elif r.status == VerifyStatus.SKIPPED:
            keep_keys.add(r.cite_key)  # keep unverifiable entries

    kept: list[str] = []
    for m in _ENTRY_RE.finditer(bib_text):
        key = m.group(2).strip()
        if key in keep_keys:
            kept.append(m.group(0))

    return "\n\n".join(kept) + "\n" if kept else ""


def annotate_paper_hallucinations(
    paper_text: str,
    report: VerificationReport,
) -> str:
    """Remove hallucinated \\cite{} / [key] markers from paper text.

    HALLUCINATED citations are removed; SUSPICIOUS/VERIFIED/SKIPPED are kept.
    Works with both LaTeX (``\\cite{key}``) and Markdown (``[key]``) formats.
    """
    hallucinated_keys: set[str] = {
        r.cite_key for r in report.results if r.status == VerifyStatus.HALLUCINATED
    }
    if not hallucinated_keys:
        return paper_text

    result = paper_text

    def _replace_latex(m: re.Match[str]) -> str:
        keys = [k.strip() for k in m.group(1).split(",")]
        kept = [k for k in keys if k not in hallucinated_keys]
        return "\\cite{" + ", ".join(kept) + "}" if kept else ""

    result = re.sub(r"\\cite\{([^}]+)\}", _replace_latex, result)

    _CITE_KEY_PAT = r"[a-zA-Z]+\d{4}[a-zA-Z]*"

    def _replace_markdown_multi(m: re.Match[str]) -> str:
        keys = [k.strip() for k in re.split(r"[,;]\s*", m.group(1))]
        kept = [k for k in keys if k not in hallucinated_keys]
        return "[" + ", ".join(kept) + "]" if kept else ""

    result = re.sub(
        rf"\[({_CITE_KEY_PAT}(?:\s*[,;]\s*{_CITE_KEY_PAT})*)\]",
        _replace_markdown_multi,
        result,
    )

    result = re.sub(r"\s{2,}", " ", result)
    result = re.sub(r"\(\s*\)", "", result)
    result = re.sub(r"\[\s*\]", "", result)

    return result
