"""MCP-backed search adapters for CuriosityEngine.

Wraps MCP server tool calls to produce ``SearchResult`` objects compatible
with the curiosity engine pipeline.  All functions degrade gracefully when
the required MCP server is not connected.

Available adapters
------------------
- ``brave_web_search``  : Brave Search API (server ``brave_search``)
- ``mcp_fetch_results`` : Fetch full page content by URL (server ``fetch``)
"""

from __future__ import annotations

import json
import logging

from echo.curiosity.web_search import SearchResult

logger = logging.getLogger(__name__)


def _mcp() -> "MCPClientManager":  # type: ignore[name-defined]  # noqa: F821
    """Lazy import of the MCP manager singleton to avoid circular imports."""
    from echo.mcp import mcp_manager  # noqa: PLC0415
    return mcp_manager


def _is_connected(server_name: str) -> bool:
    """Return True when the named MCP server is currently connected."""
    mgr = _mcp()
    conn = mgr._connections.get(server_name)  # noqa: SLF001
    return conn is not None and conn.connected


# ---------------------------------------------------------------------------
# Brave Search
# ---------------------------------------------------------------------------

async def brave_web_search(query: str, max_results: int = 3) -> list[SearchResult]:
    """Web search via the Brave Search MCP server.

    Falls back silently if the ``brave_search`` server is not connected.
    """
    if not _is_connected("brave_search"):
        logger.debug("[MCP curiosity] brave_search not connected — skipping")
        return []

    try:
        raw = await _mcp().call_tool(
            "brave_search__brave_web_search",
            {"query": query, "count": max_results},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[MCP curiosity] brave_web_search call failed (%r): %s", query, exc)
        return []

    if raw.startswith("[MCP ERROR]"):
        logger.warning("[MCP curiosity] brave_web_search error for %r: %s", query, raw)
        return []

    # The Brave MCP server returns a plain-text representation or JSON.
    # Try JSON first; fall back to plain-text parsing.
    results: list[SearchResult] = []
    try:
        data = json.loads(raw)
        web_items = data.get("web", {}).get("results", [])
        for item in web_items[:max_results]:
            title = item.get("title", "").strip()
            if not title:
                continue
            results.append(
                SearchResult(
                    title=title,
                    snippet=(item.get("description") or "")[:500],
                    url=(item.get("url") or ""),
                    source="brave",
                    extra={
                        "age": item.get("age", ""),
                        "extra_snippets": item.get("extra_snippets", []),
                    },
                )
            )
    except (json.JSONDecodeError, AttributeError):
        # Plain-text fallback: treat the whole text as a single summary result
        if raw.strip():
            results.append(
                SearchResult(
                    title=f"Brave search: {query}",
                    snippet=raw[:500],
                    url="",
                    source="brave",
                )
            )

    logger.debug("[MCP curiosity] brave_web_search(%r): %d results", query, len(results))
    return results


# ---------------------------------------------------------------------------
# Fetch (URL content retrieval)
# ---------------------------------------------------------------------------

async def mcp_fetch_results(urls: list[str], topic: str, max_per_url: int = 800) -> list[SearchResult]:
    """Fetch the content of the given URLs via the MCP ``fetch`` server.

    Returns at most one ``SearchResult`` per URL.  Silently skips when the
    ``fetch`` server is not connected.
    """
    if not urls:
        return []
    if not _is_connected("fetch"):
        logger.debug("[MCP curiosity] fetch server not connected — skipping URL enrichment")
        return []

    results: list[SearchResult] = []
    for url in urls[:3]:  # cap at 3 URLs per call to keep cycles fast
        try:
            content = await _mcp().call_tool(
                "fetch__fetch",
                {"url": url, "max_length": max_per_url},
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("[MCP curiosity] fetch %s failed: %s", url, exc)
            continue

        if not content or content.startswith("[MCP ERROR]"):
            continue

        # Use the first non-empty line as a title proxy
        first_line = next((ln.strip() for ln in content.splitlines() if ln.strip()), topic)
        results.append(
            SearchResult(
                title=first_line[:120],
                snippet=content[:max_per_url],
                url=url,
                source="fetch",
            )
        )

    logger.debug("[MCP curiosity] mcp_fetch_results: fetched %d/%d URL(s)", len(results), len(urls))
    return results
