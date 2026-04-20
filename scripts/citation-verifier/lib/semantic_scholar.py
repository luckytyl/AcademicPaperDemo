"""Semantic Scholar API client.

Uses only stdlib ``urllib`` — zero extra dependencies.

Public API
----------
- ``search_semantic_scholar(query, limit, year_min, api_key)`` → ``list[Paper]``
- ``batch_fetch_papers(paper_ids, api_key)`` → ``list[Paper]``

Rate limit: 1 req/s (free, no API key); 10 req/s (with API key).
Circuit breaker: CLOSED → OPEN (3 consecutive 429s) → HALF_OPEN → CLOSED
"""

from __future__ import annotations

import json
import logging
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .models import Author, Paper

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_FIELDS = "paperId,title,abstract,year,venue,citationCount,authors,externalIds,url"
_MAX_PER_REQUEST = 100
_RATE_LIMIT_SEC = 1.5
_MAX_RETRIES = 3
_MAX_WAIT_SEC = 60
_TIMEOUT_SEC = 30

_CB_THRESHOLD = 3
_CB_INITIAL_COOLDOWN = 120
_CB_MAX_COOLDOWN = 600
_CB_CLOSED = "closed"
_CB_OPEN = "open"
_CB_HALF_OPEN = "half_open"

_cb_state: str = _CB_CLOSED
_cb_consecutive_429s: int = 0
_cb_cooldown_sec: float = _CB_INITIAL_COOLDOWN
_cb_open_since: float = 0.0
_cb_trip_count: int = 0
_last_request_time: float = 0.0


def _cb_should_allow() -> bool:
    global _cb_state  # noqa: PLW0603
    if _cb_state == _CB_CLOSED:
        return True
    if _cb_state == _CB_OPEN:
        elapsed = time.monotonic() - _cb_open_since
        if elapsed >= _cb_cooldown_sec:
            _cb_state = _CB_HALF_OPEN
            return True
        return False
    return True


def _cb_on_success() -> None:
    global _cb_state, _cb_consecutive_429s, _cb_cooldown_sec  # noqa: PLW0603
    _cb_consecutive_429s = 0
    if _cb_state != _CB_CLOSED:
        _cb_state = _CB_CLOSED
        _cb_cooldown_sec = _CB_INITIAL_COOLDOWN


def _cb_on_429() -> bool:
    global _cb_state, _cb_consecutive_429s, _cb_cooldown_sec  # noqa: PLW0603
    global _cb_open_since, _cb_trip_count  # noqa: PLW0603
    _cb_consecutive_429s += 1
    if _cb_state == _CB_HALF_OPEN:
        _cb_cooldown_sec = min(_cb_cooldown_sec * 2, _CB_MAX_COOLDOWN)
        _cb_state = _CB_OPEN
        _cb_open_since = time.monotonic()
        _cb_trip_count += 1
        return True
    if _cb_consecutive_429s >= _CB_THRESHOLD:
        _cb_state = _CB_OPEN
        _cb_open_since = time.monotonic()
        _cb_trip_count += 1
        logger.warning("S2 circuit breaker TRIPPED. Cooldown: %.0fs", _cb_cooldown_sec)
        return True
    return False


def search_semantic_scholar(
    query: str,
    *,
    limit: int = 20,
    year_min: int = 0,
    api_key: str = "",
) -> list[Paper]:
    """Search Semantic Scholar for papers matching *query*.

    Parameters
    ----------
    query : str
        Free-text search query.
    limit : int
        Maximum number of results (capped at 100).
    year_min : int
        If >0, restrict to papers published in this year or later.
    api_key : str
        Optional S2 API key. Free to obtain at semanticscholar.org/product/api
        Raises rate limit from 1 req/s to 10 req/s.
    """
    global _last_request_time  # noqa: PLW0603

    now = time.monotonic()
    rate_limit = 0.3 if api_key else _RATE_LIMIT_SEC
    elapsed = now - _last_request_time
    if elapsed < rate_limit:
        time.sleep(rate_limit - elapsed)

    limit = min(limit, _MAX_PER_REQUEST)
    params: dict[str, str] = {
        "query": query,
        "limit": str(limit),
        "fields": _FIELDS,
    }
    if year_min > 0:
        params["year"] = f"{year_min}-"

    url = f"{_BASE_URL}?{urllib.parse.urlencode(params)}"
    headers: dict[str, str] = {"Accept": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key

    _last_request_time = time.monotonic()
    data = _request_with_retry(url, headers)
    if data is None:
        return []

    raw_papers = data.get("data", [])
    if not isinstance(raw_papers, list):
        return []

    papers: list[Paper] = []
    for item in raw_papers:
        try:
            papers.append(_parse_s2_paper(item))
        except Exception:  # noqa: BLE001
            pass
    return papers


def batch_fetch_papers(
    paper_ids: list[str],
    *,
    api_key: str = "",
    fields: str = _FIELDS,
) -> list[Paper]:
    """Batch fetch paper details by S2 IDs, arXiv IDs (prefixed ``ARXIV:``), or DOIs.

    Parameters
    ----------
    paper_ids : list[str]
        List of IDs. arXiv IDs must be prefixed with ``ARXIV:``,
        e.g. ``["ARXIV:2301.00001", "10.1145/3123456"]``.
    api_key : str
        Optional S2 API key for higher rate limits.
    """
    if not paper_ids:
        return []
    if not _cb_should_allow():
        return []

    global _last_request_time  # noqa: PLW0603
    _BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
    _BATCH_MAX = 500
    all_papers: list[Paper] = []
    rate = 0.3 if api_key else _RATE_LIMIT_SEC

    for i in range(0, len(paper_ids), _BATCH_MAX):
        chunk = paper_ids[i: i + _BATCH_MAX]
        url = f"{_BATCH_URL}?fields={fields}"
        headers: dict[str, str] = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if api_key:
            headers["x-api-key"] = api_key

        now = time.monotonic()
        if now - _last_request_time < rate:
            time.sleep(rate - (now - _last_request_time))

        body = json.dumps({"ids": chunk}).encode("utf-8")
        _last_request_time = time.monotonic()
        result = _post_with_retry(url, headers, body)
        if result is None:
            continue
        for item in result:
            if item is None:
                continue
            try:
                all_papers.append(_parse_s2_paper(item))
            except Exception:  # noqa: BLE001
                pass
        if i + _BATCH_MAX < len(paper_ids):
            time.sleep(rate)

    return all_papers


def _request_with_retry(url: str, headers: dict[str, str]) -> dict[str, Any] | None:
    if not _cb_should_allow():
        return None
    for attempt in range(_MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
                body = resp.read().decode("utf-8")
                _cb_on_success()
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                if _cb_on_429():
                    return None
                delay = min(2 ** (attempt + 1), _MAX_WAIT_SEC)
                time.sleep(delay + random.uniform(0, delay * 0.3))
                continue
            logger.warning("S2 HTTP %d for %s", exc.code, url)
            return None
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            wait = min(2 ** attempt, _MAX_WAIT_SEC)
            logger.warning("S2 request failed (%s). Retry %d/%d", exc, attempt + 1, _MAX_RETRIES)
            time.sleep(wait + random.uniform(0, wait * 0.2))
    logger.error("S2 request exhausted retries for: %s", url)
    return None


def _post_with_retry(url: str, headers: dict[str, str], body: bytes) -> list[dict[str, Any]] | None:
    if not _cb_should_allow():
        return None
    for attempt in range(_MAX_RETRIES):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                _cb_on_success()
                return data if isinstance(data, list) else None
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                if _cb_on_429():
                    return None
                delay = min(2 ** (attempt + 1), _MAX_WAIT_SEC)
                time.sleep(delay + random.uniform(0, delay * 0.3))
                continue
            return None
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            wait = min(2 ** attempt, _MAX_WAIT_SEC)
            time.sleep(wait + random.uniform(0, wait * 0.2))
    return None


def _parse_s2_paper(item: dict[str, Any]) -> Paper:
    ext_ids = item.get("externalIds") or {}
    authors_raw = item.get("authors") or []
    authors = tuple(
        Author(name=a.get("name", "Unknown"))
        for a in authors_raw
        if isinstance(a, dict)
    )
    return Paper(
        paper_id=f"s2-{item.get('paperId', '')}",
        title=str(item.get("title", "")).strip(),
        authors=authors,
        year=int(item.get("year") or 0),
        abstract=str(item.get("abstract") or "").strip(),
        venue=str(item.get("venue") or "").strip(),
        citation_count=int(item.get("citationCount") or 0),
        doi=str(ext_ids.get("DOI") or "").strip(),
        arxiv_id=str(ext_ids.get("ArXiv") or "").strip(),
        url=str(item.get("url") or "").strip(),
        source="semantic_scholar",
    )
