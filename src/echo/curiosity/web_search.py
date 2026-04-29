"""Light-weight web search adapters — zero API keys needed.

Sources
-------
- arXiv.org  :   academic papers, sorted by most recent submission date.
- HN Algolia :   Hacker News stories with > 30 points (tech / science news).
- Wikipedia  :   encyclopaedic summaries via MediaWiki search API.
- DuckDuckGo :   instant-answer API (abstracts + related topics).
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(20.0)


@dataclass
class SearchResult:
    """A single search result from any source."""

    title: str
    snippet: str
    url: str
    source: str           # "arxiv" | "hn"
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# arXiv
# ---------------------------------------------------------------------------

async def arxiv_search(query: str, max_results: int = 3) -> list[SearchResult]:
    """Return recent arXiv papers matching *query* (sorted by submission date)."""
    params = {
        "search_query": f"all:{query}",
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get("https://export.arxiv.org/api/query", params=params)
        r.raise_for_status()

        ns = {"a": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(r.text)

        results: list[SearchResult] = []
        for entry in root.findall("a:entry", ns):
            title_el = entry.find("a:title", ns)
            summary_el = entry.find("a:summary", ns)
            id_el = entry.find("a:id", ns)
            if title_el is None or summary_el is None:
                continue
            published_el = entry.find("a:published", ns)
            results.append(
                SearchResult(
                    title=title_el.text.strip().replace("\n", " "),
                    snippet=summary_el.text.strip()[:500].replace("\n", " "),
                    url=(id_el.text or "").strip(),
                    source="arxiv",
                    extra={"published": (published_el.text or "")[:10] if published_el is not None else ""},
                )
            )

        logger.debug("arXiv(%r): %d results", query, len(results))
        return results

    except Exception as exc:  # noqa: BLE001
        logger.warning("arXiv search failed for %r: %s", query, exc)
        return []


# ---------------------------------------------------------------------------
# Hacker News (via Algolia API)
# ---------------------------------------------------------------------------

async def hn_search(query: str, max_results: int = 4) -> list[SearchResult]:
    """Return Hacker News stories matching *query* with > 30 upvotes."""
    params = {
        "query": query,
        "tags": "story",
        "numericFilters": "points>30",
        "hitsPerPage": max_results,
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get("https://hn.algolia.com/api/v1/search", params=params)
        r.raise_for_status()

        results: list[SearchResult] = []
        for hit in r.json().get("hits", []):
            snippet = (hit.get("story_text") or "")[:400].replace("\n", " ")
            results.append(
                SearchResult(
                    title=hit.get("title", ""),
                    snippet=snippet,
                    url=(
                        hit.get("url")
                        or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
                    ),
                    source="hn",
                    extra={"points": hit.get("points", 0)},
                )
            )

        logger.debug("HN(%r): %d results", query, len(results))
        return results

    except Exception as exc:  # noqa: BLE001
        logger.warning("HN search failed for %r: %s", query, exc)
        return []


# ---------------------------------------------------------------------------
# Wikipedia  (MediaWiki API — no authentication required)
# ---------------------------------------------------------------------------

async def wikipedia_search(query: str, max_results: int = 2) -> list[SearchResult]:
    """Return Wikipedia article summaries matching *query*.

    Uses the MediaWiki ``action=query&list=search`` endpoint followed by a
    ``action=query&prop=extracts`` call to grab short lead-section extracts.
    Both calls are unauthenticated and rate-limit friendly.
    """
    params_search: dict[str, str | int] = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": max_results,
        "srprop": "snippet",
        "format": "json",
        "utf8": "1",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get("https://en.wikipedia.org/w/api.php", params=params_search)
        r.raise_for_status()

        hits = r.json().get("query", {}).get("search", [])
        results: list[SearchResult] = []
        for item in hits:
            title: str = item.get("title", "")
            # Strip HTML highlight tags from snippet
            snippet: str = (
                item.get("snippet", "")
                .replace('<span class="searchmatch">', "")
                .replace("</span>", "")
            )[:400]
            url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
            results.append(
                SearchResult(
                    title=title,
                    snippet=snippet,
                    url=url,
                    source="wikipedia",
                )
            )

        logger.debug("Wikipedia(%r): %d results", query, len(results))
        return results

    except Exception as exc:  # noqa: BLE001
        logger.warning("Wikipedia search failed for %r: %s", query, exc)
        return []


# ---------------------------------------------------------------------------
# DuckDuckGo Instant Answer API  (no authentication required)
# ---------------------------------------------------------------------------

async def duckduckgo_search(query: str, max_results: int = 2) -> list[SearchResult]:
    """Return results from the DuckDuckGo Instant Answer API.

    The API returns a JSON object with ``Abstract``, ``AbstractText``, and
    ``RelatedTopics``.  We surface the main abstract (if present) plus the
    first *max_results - 1* related topics.
    """
    params: dict[str, str | int] = {
        "q": query,
        "format": "json",
        "no_html": "1",
        "skip_disambig": "1",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get("https://api.duckduckgo.com/", params=params)
        r.raise_for_status()
        data = r.json()

        results: list[SearchResult] = []

        # Main abstract (usually sourced from Wikipedia / Wikidata)
        abstract = (data.get("AbstractText") or "").strip()
        abstract_url = (data.get("AbstractURL") or "").strip()
        abstract_title = (data.get("Heading") or query).strip()
        if abstract and abstract_url:
            results.append(
                SearchResult(
                    title=abstract_title,
                    snippet=abstract[:500],
                    url=abstract_url,
                    source="duckduckgo",
                )
            )

        # Related topics
        for topic in data.get("RelatedTopics", []):
            if len(results) >= max_results:
                break
            # RelatedTopics entries may be nested dicts or dicts without Text
            if not isinstance(topic, dict):
                continue
            text = (topic.get("Text") or "").strip()
            url = (topic.get("FirstURL") or "").strip()
            if text and url:
                results.append(
                    SearchResult(
                        title=text[:80],
                        snippet=text[:400],
                        url=url,
                        source="duckduckgo",
                    )
                )

        logger.debug("DuckDuckGo(%r): %d results", query, len(results))
        return results

    except Exception as exc:  # noqa: BLE001
        logger.warning("DuckDuckGo search failed for %r: %s", query, exc)
        return []
