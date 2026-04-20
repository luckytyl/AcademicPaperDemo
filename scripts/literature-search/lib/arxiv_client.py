"""arXiv API client.

Uses stdlib ``urllib`` + ``xml.etree`` — zero extra dependencies.

Public API
----------
- ``search_arxiv(query, limit)`` → ``list[Paper]``

Rate limit: arXiv requests 3-second gaps between calls.
Circuit breaker: CLOSED → OPEN (3 consecutive 429s) → HALF_OPEN → CLOSED
"""

from __future__ import annotations

import logging
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .models import Author, Paper

logger = logging.getLogger(__name__)

_BASE_URL = "https://export.arxiv.org/api/query"
_MAX_RESULTS = 50
_RATE_LIMIT_SEC = 3.1
_RATE_LIMIT_ELEVATED = 5.0
_MAX_RETRIES = 3
_MAX_WAIT_SEC = 60
_TIMEOUT_SEC = 30

_CB_THRESHOLD = 3
_CB_INITIAL_COOLDOWN = 180
_CB_MAX_COOLDOWN = 600
_CB_CLOSED = "closed"
_CB_OPEN = "open"
_CB_HALF_OPEN = "half_open"

_cb_state: str = _CB_CLOSED
_cb_consecutive_429s: int = 0
_cb_cooldown_sec: float = _CB_INITIAL_COOLDOWN
_cb_open_since: float = 0.0
_cb_trip_count: int = 0
_rate_elevated: bool = False
_last_request_time: float = 0.0

_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


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
    global _cb_state, _cb_consecutive_429s, _cb_cooldown_sec, _rate_elevated  # noqa: PLW0603
    _cb_consecutive_429s = 0
    if _cb_state != _CB_CLOSED:
        _cb_state = _CB_CLOSED
        _cb_cooldown_sec = _CB_INITIAL_COOLDOWN
    _rate_elevated = False


def _cb_on_429() -> bool:
    global _cb_state, _cb_consecutive_429s, _cb_cooldown_sec  # noqa: PLW0603
    global _cb_open_since, _cb_trip_count, _rate_elevated  # noqa: PLW0603
    _cb_consecutive_429s += 1
    _rate_elevated = True
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
        logger.warning("arXiv circuit breaker TRIPPED. Cooldown: %.0fs", _cb_cooldown_sec)
        return True
    return False


def search_arxiv(query: str, *, limit: int = 20) -> list[Paper]:
    """Search arXiv for papers matching *query*.

    Parameters
    ----------
    query : str
        Free-text search query.
    limit : int
        Maximum number of results (capped at 50).
    """
    global _last_request_time  # noqa: PLW0603

    now = time.monotonic()
    rate = _RATE_LIMIT_ELEVATED if _rate_elevated else _RATE_LIMIT_SEC
    elapsed = now - _last_request_time
    if elapsed < rate:
        time.sleep(rate - elapsed)

    limit = min(limit, _MAX_RESULTS)
    params = {
        "search_query": f"all:{query}",
        "start": "0",
        "max_results": str(limit),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    url = f"{_BASE_URL}?{urllib.parse.urlencode(params)}"
    _last_request_time = time.monotonic()

    xml_text = _fetch_with_retry(url)
    if xml_text is None:
        return []
    return _parse_atom_feed(xml_text)


def _fetch_with_retry(url: str) -> str | None:
    if not _cb_should_allow():
        return None

    for attempt in range(_MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/atom+xml"})
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
                body = resp.read().decode("utf-8")
                _cb_on_success()
                return body
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    wait = float(retry_after) if retry_after else _RATE_LIMIT_ELEVATED * (2 ** attempt)
                except (ValueError, TypeError):
                    wait = _RATE_LIMIT_ELEVATED * (2 ** attempt)
                wait = min(wait, _MAX_WAIT_SEC)
                if _cb_on_429():
                    return None
                time.sleep(wait + random.uniform(0, wait * 0.2))
                continue
            if exc.code == 503:
                wait = _RATE_LIMIT_SEC * (2 ** attempt)
                time.sleep(wait + random.uniform(0, wait * 0.2))
                continue
            logger.warning("arXiv HTTP %d for %s", exc.code, url)
            return None
        except (urllib.error.URLError, OSError) as exc:
            wait = min(_RATE_LIMIT_SEC * (2 ** attempt), _MAX_WAIT_SEC)
            logger.warning("arXiv request failed (%s). Retry %d/%d", exc, attempt + 1, _MAX_RETRIES)
            time.sleep(wait + random.uniform(0, wait * 0.2))

    logger.error("arXiv request exhausted retries for: %s", url)
    return None


def _parse_atom_feed(xml_text: str) -> list[Paper]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.error("Failed to parse arXiv Atom XML")
        return []
    papers: list[Paper] = []
    for entry in root.findall("atom:entry", _NS):
        try:
            papers.append(_parse_entry(entry))
        except Exception:  # noqa: BLE001
            pass
    return papers


def _text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return (element.text or "").strip()


def _parse_entry(entry: ET.Element) -> Paper:
    title = re.sub(r"\s+", " ", _text(entry.find("atom:title", _NS)))
    abstract = re.sub(r"\s+", " ", _text(entry.find("atom:summary", _NS)))
    authors = tuple(
        Author(name=_text(a.find("atom:name", _NS)))
        for a in entry.findall("atom:author", _NS)
    )
    raw_id = _text(entry.find("atom:id", _NS))
    arxiv_id = ""
    m = re.search(r"(\d{4}\.\d{4,5})(v\d+)?$", raw_id)
    if m:
        arxiv_id = m.group(1)
    published = _text(entry.find("atom:published", _NS))
    year = 0
    if published:
        ym = re.match(r"(\d{4})", published)
        if ym:
            year = int(ym.group(1))
    doi_el = entry.find("arxiv:doi", _NS)
    doi = _text(doi_el) if doi_el is not None else ""
    primary = entry.find("arxiv:primary_category", _NS)
    venue = primary.get("term", "") if primary is not None else ""
    url = ""
    for link in entry.findall("atom:link", _NS):
        if link.get("type") == "text/html":
            url = link.get("href", "")
            break
    if not url:
        url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else raw_id
    return Paper(
        paper_id=f"arxiv-{arxiv_id}" if arxiv_id else f"arxiv-{raw_id}",
        title=title,
        authors=authors,
        year=year,
        abstract=abstract,
        venue=venue,
        citation_count=0,
        doi=doi,
        arxiv_id=arxiv_id,
        url=url,
        source="arxiv",
    )
