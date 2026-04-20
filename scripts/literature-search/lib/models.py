"""Data models for literature search results.

Paper and Author are frozen dataclasses — immutable after creation.
``Paper.to_bibtex()`` generates a valid BibTeX entry from metadata,
and ``Paper.cite_key`` returns a normalised citation key.

Zero external dependencies — stdlib only.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Author:
    """A paper author."""

    name: str
    affiliation: str = ""

    def last_name(self) -> str:
        """Return ASCII-folded last name for citation keys."""
        parts = self.name.strip().split()
        raw = parts[-1] if parts else "unknown"
        nfkd = unicodedata.normalize("NFKD", raw)
        ascii_name = nfkd.encode("ascii", "ignore").decode("ascii")
        return re.sub(r"[^a-zA-Z]", "", ascii_name).lower() or "unknown"


@dataclass(frozen=True)
class Paper:
    """A single paper from OpenAlex, Semantic Scholar, arXiv, or similar sources."""

    paper_id: str
    title: str
    authors: tuple[Author, ...] = ()
    year: int = 0
    abstract: str = ""
    venue: str = ""
    citation_count: int = 0
    doi: str = ""
    arxiv_id: str = ""
    url: str = ""
    source: str = ""  # "openalex" | "semantic_scholar" | "arxiv"
    _bibtex_override: str = field(default="", repr=False)

    @property
    def cite_key(self) -> str:
        """Normalised citation key: ``lastname<year><keyword>``.

        Example: ``smith2024transformer``
        """
        last = self.authors[0].last_name() if self.authors else "anon"
        yr = str(self.year) if self.year else "0000"
        kw = ""
        for word in self.title.split():
            cleaned = re.sub(r"[^a-zA-Z]", "", word).lower()
            if len(cleaned) > 3 and cleaned not in _STOPWORDS:
                kw = cleaned
                break

        # 如果 author 是 unknown/anon 且有 DOI 或 arXiv ID，用它们做 key
        if last in ("unknown", "anon") and self.doi:
            doi_part = self.doi.split("/")[-1].replace(".", "").replace("-", "")[:12]
            return f"doi{yr}{doi_part}"
        if last in ("unknown", "anon") and self.arxiv_id:
            aid = re.sub(r"[^a-zA-Z0-9]", "", self.arxiv_id)[:12]
            return f"arxiv{yr}{aid}"
        # 如果 kw 为空（标题太短或全是停用词），尝试用标题前几个词
        if not kw and self.title:
            for word in self.title.split()[:3]:
                cleaned = re.sub(r"[^a-zA-Z]", "", word).lower()
                if cleaned:
                    kw += cleaned
            kw = kw[:15] or "ref"

        return f"{last}{yr}{kw}"

    def to_bibtex(self) -> str:
        """Generate a BibTeX entry string."""
        if self._bibtex_override:
            return self._bibtex_override.strip()

        key = self.cite_key
        authors_str = " and ".join(a.name for a in self.authors) or "Unknown"

        if self.venue and any(
            kw in self.venue.lower()
            for kw in ("conference", "proc", "workshop", "neurips", "icml",
                       "iclr", "aaai", "cvpr", "acl")
        ):
            entry_type = "inproceedings"
            venue_field = f"  booktitle = {{{self.venue}}},"
        elif self.arxiv_id and not self.venue:
            entry_type = "article"
            venue_field = "  journal = {arXiv preprint},"
        else:
            entry_type = "article"
            venue_field = (
                f"  journal = {{{self.venue or 'Unknown'}}}," if self.venue else ""
            )

        lines = [f"@{entry_type}{{{key},"]
        lines.append(f"  title = {{{self.title}}},")
        lines.append(f"  author = {{{authors_str}}},")
        if self.year:
            lines.append(f"  year = {{{self.year}}},")
        if venue_field:
            lines.append(venue_field)
        if self.doi:
            lines.append(f"  doi = {{{self.doi}}},")
        if self.arxiv_id:
            lines.append(f"  eprint = {{{self.arxiv_id}}},")
            lines.append("  archiveprefix = {arXiv},")
        if self.url:
            lines.append(f"  url = {{{self.url}}},")
        lines.append("}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, object]:
        """Serialise to a plain dict for JSON output."""
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "authors": [{"name": a.name, "affiliation": a.affiliation} for a in self.authors],
            "year": self.year,
            "abstract": self.abstract,
            "venue": self.venue,
            "citation_count": self.citation_count,
            "doi": self.doi,
            "arxiv_id": self.arxiv_id,
            "url": self.url,
            "source": self.source,
            "cite_key": self.cite_key,
        }


_STOPWORDS = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "into", "over",
    "upon", "about", "through", "using", "based", "towards", "toward",
    "between", "under", "more", "than", "when", "what", "which", "where",
    "does", "have", "been", "some", "each", "also", "much", "very",
    "learning",  # too generic for ML papers
})
