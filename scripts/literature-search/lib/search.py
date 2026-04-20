"""Unified literature search with deduplication.

Combines results from OpenAlex, Semantic Scholar, and arXiv,
deduplicates by DOI → arXiv ID → fuzzy title match, and returns
a merged list sorted by citation count (descending).

Source priority: OpenAlex (10K/day) → Semantic Scholar (1K/5min) → arXiv (1/3s)

Public API
----------
- ``search_papers(query, limit, sources, year_min, deduplicate)`` → ``list[Paper]``
- ``search_papers_multi_query(queries, ...)`` → ``list[Paper]``
- ``papers_to_bibtex(papers)`` → ``str``

Zero external dependencies — stdlib only.
"""

from __future__ import annotations

import logging
import re
import time
import urllib.error
from collections.abc import Sequence
from dataclasses import asdict
from typing import cast

from .arxiv_client import search_arxiv
from .cache import get_cached, put_cache
from .models import Author, Paper
from .openalex_client import search_openalex
from .semantic_scholar import search_semantic_scholar

logger = logging.getLogger(__name__)

_DEFAULT_SOURCES = ("openalex", "semantic_scholar", "arxiv")


def _papers_to_dicts(papers: list[Paper]) -> list[dict[str, object]]:
    return [asdict(p) for p in papers]


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _dicts_to_papers(dicts: list[dict[str, object]]) -> list[Paper]:
    papers: list[Paper] = []
    for d in dicts:
        try:
            authors_raw = d.get("authors", ())
            if not isinstance(authors_raw, list):
                authors_raw = []
            authors = tuple(
                Author(
                    name=str(cast(dict[str, object], a).get("name", "")),
                    affiliation=str(cast(dict[str, object], a).get("affiliation", "")),
                )
                for a in authors_raw
                if isinstance(a, dict)
            )
            papers.append(Paper(
                paper_id=cast(str, d["paper_id"]),
                title=cast(str, d["title"]),
                authors=authors,
                year=_as_int(d.get("year", 0)),
                abstract=str(d.get("abstract", "")),
                venue=str(d.get("venue", "")),
                citation_count=_as_int(d.get("citation_count", 0)),
                doi=str(d.get("doi", "")),
                arxiv_id=str(d.get("arxiv_id", "")),
                url=str(d.get("url", "")),
                source=str(d.get("source", "")),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return papers


def search_papers(
    query: str,
    *,
    limit: int = 20,
    sources: Sequence[str] = _DEFAULT_SOURCES,
    year_min: int = 0,
    deduplicate: bool = True,
    s2_api_key: str = "",
    openalex_email: str = "",
) -> list[Paper]:
    """Search multiple academic sources and return deduplicated results.

    Parameters
    ----------
    query : str
        Free-text search query.
    limit : int
        Maximum results *per source*. Total before dedup = limit × len(sources).
    sources : sequence of str
        Which backends to query. Options: "openalex", "semantic_scholar", "arxiv".
        Default: all three.
    year_min : int
        If >0, restrict to papers published in this year or later.
    deduplicate : bool
        Whether to remove duplicates across sources (default True).
    s2_api_key : str
        Optional Semantic Scholar API key (raises rate limit to 10 req/s).
    openalex_email : str
        Optional email for OpenAlex polite pool (higher rate limits).

    Returns
    -------
    list[Paper]
        Merged results, sorted by (citation_count, year) descending.
    """
    all_papers: list[Paper] = []
    source_stats: dict[str, int] = {}
    cache_hits = 0

    for src in sources:
        src_lower = src.lower().replace("-", "_").replace(" ", "_")
        cache_source = "semantic_scholar" if src_lower in ("semantic_scholar", "s2") else src_lower

        try:
            if src_lower == "openalex":
                kwargs = {}
                if openalex_email:
                    kwargs["email"] = openalex_email
                papers = search_openalex(query, limit=limit, year_min=year_min, **kwargs)
                all_papers.extend(papers)
                put_cache(query, "openalex", limit, _papers_to_dicts(papers))
                source_stats["openalex"] = len(papers)
                logger.info("OpenAlex returned %d papers for %r", len(papers), query)
                time.sleep(0.5)

            elif src_lower in ("semantic_scholar", "s2"):
                papers = search_semantic_scholar(
                    query, limit=limit, year_min=year_min, api_key=s2_api_key
                )
                all_papers.extend(papers)
                put_cache(query, "semantic_scholar", limit, _papers_to_dicts(papers))
                source_stats["semantic_scholar"] = len(papers)
                logger.info("Semantic Scholar returned %d papers for %r", len(papers), query)
                time.sleep(1.0)

            elif src_lower == "arxiv":
                papers = search_arxiv(query, limit=limit)
                all_papers.extend(papers)
                put_cache(query, "arxiv", limit, _papers_to_dicts(papers))
                source_stats["arxiv"] = len(papers)
                logger.info("arXiv returned %d papers for %r", len(papers), query)

            else:
                logger.warning("Unknown literature source: %s (skipped)", src)

        except (OSError, RuntimeError, TypeError, ValueError,
                urllib.error.HTTPError, urllib.error.URLError):
            logger.warning("[rate-limit] Source %s failed for %r — trying cache", src, query)
            cached = get_cached(query, cache_source, limit)
            if cached:
                papers = _dicts_to_papers(cached)
                all_papers.extend(papers)
                cache_hits += len(papers)
                logger.info("[cache] HIT: %d papers for %s/%r", len(papers), src, query)
            else:
                logger.warning("No cache available for %s/%r — skipping", src, query)

    total = len(all_papers)
    parts = [f"{src}: {n}" for src, n in source_stats.items()]
    if cache_hits:
        parts.append(f"cache: {cache_hits}")
    logger.info("[literature] Found %d papers (%s) for %r",
                total, ", ".join(parts) if parts else "none", query)

    if deduplicate:
        all_papers = _deduplicate(all_papers)

    all_papers.sort(key=lambda p: (p.citation_count, p.year), reverse=True)
    return all_papers


def search_papers_multi_query(
    queries: list[str],
    *,
    limit_per_query: int = 20,
    sources: Sequence[str] = _DEFAULT_SOURCES,
    year_min: int = 0,
    s2_api_key: str = "",
    openalex_email: str = "",
    inter_query_delay: float = 1.5,
) -> list[Paper]:
    """Run multiple queries and return deduplicated union.

    Parameters
    ----------
    queries : list[str]
        List of search queries to run.
    limit_per_query : int
        Max results per source per query.
    inter_query_delay : float
        Seconds to wait between queries (respects rate limits).

    Returns
    -------
    list[Paper]
        Deduplicated union of all query results, sorted by citations.
    """
    all_papers: list[Paper] = []
    for i, q in enumerate(queries):
        if i > 0:
            time.sleep(inter_query_delay)
        results = search_papers(
            q,
            limit=limit_per_query,
            sources=sources,
            year_min=year_min,
            s2_api_key=s2_api_key,
            openalex_email=openalex_email,
            deduplicate=False,
        )
        all_papers.extend(results)
        logger.info("Query %d/%d %r → %d papers", i + 1, len(queries), q, len(results))

    deduped = _deduplicate(all_papers)
    deduped.sort(key=lambda p: (p.citation_count, p.year), reverse=True)
    return deduped


def papers_to_bibtex(papers: Sequence[Paper]) -> str:
    """Generate a combined BibTeX string from a list of papers."""
    entries = [p.to_bibtex() for p in papers]
    return "\n\n".join(entries) + "\n"


def _normalise_title(title: str) -> str:
    t = title.lower()
    t = re.sub(r"[^a-z0-9\s]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def _deduplicate(papers: list[Paper]) -> list[Paper]:
    """Remove duplicates. Priority: DOI > arXiv ID > fuzzy title.

    When a duplicate is found, the entry with higher citation_count wins.
    """
    seen_doi: dict[str, int] = {}
    seen_arxiv: dict[str, int] = {}
    seen_title: dict[str, int] = {}
    result: list[Paper] = []

    for paper in papers:
        if paper.doi:
            doi_key = paper.doi.lower().strip()
            if doi_key in seen_doi:
                idx = seen_doi[doi_key]
                if paper.citation_count > result[idx].citation_count:
                    result[idx] = paper
                continue
            seen_doi[doi_key] = len(result)

        if paper.arxiv_id:
            ax_key = paper.arxiv_id.strip()
            if ax_key in seen_arxiv:
                idx = seen_arxiv[ax_key]
                if paper.citation_count > result[idx].citation_count:
                    result[idx] = paper
                continue
            seen_arxiv[ax_key] = len(result)

        norm = _normalise_title(paper.title)
        if norm and norm in seen_title:
            idx = seen_title[norm]
            if paper.citation_count > result[idx].citation_count:
                result[idx] = paper
            continue
        if norm:
            seen_title[norm] = len(result)

        result.append(paper)

    return result
