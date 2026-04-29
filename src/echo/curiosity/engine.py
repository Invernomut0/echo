"""CuriosityEngine — ECHO's autonomous idle-time knowledge acquisition.

Workflow (one curiosity cycle)
-------------------------------
1. Fetch the most recent episodic memories.
2. Check idle guard: skip if a user interaction happened recently.
3. Ask the LLM to distil 1-3 focused search queries from those memories.
4. Search arXiv (academic papers), Hacker News (tech/science news),
   Wikipedia (encyclopaedic context), DuckDuckGo Instant Answers AND,
   when connected, Brave Search (via MCP) for every topic.
5. Optionally fetch the full content of interesting URLs via the MCP
   ``fetch`` server to enrich results that have a usable URL.
6. Deduplicate against existing semantic knowledge (word-overlap heuristic).
7. Store novel findings as semantic memories with tags
   ["curiosity", "source:<provider>", <topic>].

MCP servers used (optional — degrade gracefully when not connected)
-------------------------------------------------------------------
- ``brave_search``  : Brave Search API — broad web search.
- ``fetch``         : URL content retrieval — deeper reading of found links.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from echo.core.config import settings
from echo.core.llm_client import llm
from echo.core.types import MemoryEntry
from echo.curiosity.mcp_search import brave_web_search, mcp_fetch_results
from echo.curiosity.web_search import (
    SearchResult,
    arxiv_search,
    duckduckgo_search,
    hn_search,
    wikipedia_search,
)
from echo.memory.episodic import EpisodicMemoryStore
from echo.memory.semantic import SemanticMemoryStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level dedup cache
# Store recently-searched topics to avoid hammering the same query every cycle.
# Cleared automatically after CLEAR_AFTER_CYCLES light heartbeats.
# ---------------------------------------------------------------------------
_recently_searched: set[str] = set()
_cycle_counter: int = 0
_CLEAR_AFTER_CYCLES: int = 24     # ≈ 2 hours at 5-min heartbeat

# ---------------------------------------------------------------------------
# Prompt for topic extraction
# ---------------------------------------------------------------------------
_TOPIC_PROMPT = """\
You are reviewing recent memories of an AI assistant named ECHO. \
Your task is to identify 1-3 distinct topics that ECHO should research further \
to enrich its knowledge.

Each topic must be a short, precise search query (2-6 words) suitable for an \
academic search engine or tech news feed.

Recent memories (newest first):
{memories_text}

Return ONLY a JSON array of strings. Example:
["large language model alignment", "neuroplasticity and memory consolidation", "climate tipping points"]"""

# How many chars of each memory to show the LLM
_MEMORY_SNIPPET_CHARS = 250

# Max chars of a result snippet to persist in semantic memory
_STORE_SNIPPET_CHARS = 600


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SOURCE_LABELS: dict[str, str] = {
    "arxiv": "arXiv paper",
    "hn": "HN article",
    "wikipedia": "Wikipedia",
    "duckduckgo": "DuckDuckGo",
    "brave": "Brave Web Search",
    "fetch": "Fetched web page",
}


def _format_finding(result: SearchResult, topic: str) -> str:
    """Convert a SearchResult into a storable semantic-memory string."""
    label = _SOURCE_LABELS.get(result.source, result.source)
    lines = [
        f"[Curiosity · {label}] Topic: {topic}",
        f"Title: {result.title}",
    ]
    if result.snippet:
        lines.append(f"Summary: {result.snippet[:_STORE_SNIPPET_CHARS]}")
    if result.url:
        lines.append(f"Source: {result.url}")
    if result.source == "arxiv" and result.extra.get("published"):
        lines.append(f"Published: {result.extra['published']}")
    if result.source == "brave" and result.extra.get("age"):
        lines.append(f"Age: {result.extra['age']}")
    return "\n".join(lines)


def _is_duplicate_text(new_content: str, existing: list[MemoryEntry]) -> bool:
    """Heuristic: new_content is a duplicate if it shares ≥ 5 words with
    the first 10 title-words of any existing memory."""
    new_words = set(new_content.lower().split()[2:12])   # skip "[Curiosity …]" prefix
    for mem in existing:
        stored_words = set(mem.content.lower().split()[2:12])
        if len(new_words & stored_words) >= 5:
            return True
    return False


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class CuriosityEngine:
    """Autonomous idle-time knowledge acquisition for ECHO."""

    def __init__(self) -> None:
        self._episodic = EpisodicMemoryStore()
        self._semantic = SemanticMemoryStore()

    # ------------------------------------------------------------------
    # Topic extraction
    # ------------------------------------------------------------------

    async def _extract_topics(self, memories: list[MemoryEntry]) -> list[str]:
        memories_text = "\n".join(
            f"- {m.content[:_MEMORY_SNIPPET_CHARS]}" for m in memories[:12]
        )
        try:
            raw = await llm.chat(
                messages=[
                    {
                        "role": "user",
                        "content": _TOPIC_PROMPT.format(memories_text=memories_text),
                    }
                ],
                temperature=0.35,
                max_tokens=150,
            )
            topics = json.loads(raw.strip())
            if isinstance(topics, list):
                return [str(t).strip() for t in topics[:settings.curiosity_max_topics] if t]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Topic extraction failed (%s) — using fallback", exc)

        # Fallback: use the first few words of the most recent memory
        if memories:
            words = memories[0].content.split()[:5]
            return [" ".join(words)]
        return []

    # ------------------------------------------------------------------
    # Novelty check
    # ------------------------------------------------------------------

    async def _is_novel(self, content: str) -> bool:
        """Return True when *content* is not already in semantic memory."""
        similar = await self._semantic.retrieve_similar(content, n_results=3)
        return not _is_duplicate_text(content, similar)

    # ------------------------------------------------------------------
    # Main cycle
    # ------------------------------------------------------------------

    async def run_cycle(self) -> int:
        """Run one curiosity cycle; return the number of new memories stored."""
        global _cycle_counter, _recently_searched  # noqa: PLW0603

        if not settings.curiosity_enabled:
            return 0

        # 1. Load recent episodic memories
        recent_memories = await self._episodic.get_all(limit=20)
        if not recent_memories:
            logger.debug("Curiosity skipped — no episodic memories yet")
            return 0

        # 2. Idle guard — skip if the user was active within the threshold
        most_recent = recent_memories[0]       # sorted DESC by created_at
        last_at: datetime = most_recent.created_at
        if last_at.tzinfo is None:
            last_at = last_at.replace(tzinfo=timezone.utc)
        idle_seconds = (datetime.now(timezone.utc) - last_at).total_seconds()
        threshold = settings.curiosity_idle_threshold_seconds

        if idle_seconds < threshold:
            logger.debug(
                "Curiosity skipped — last interaction %.0fs ago (threshold %ds)",
                idle_seconds,
                threshold,
            )
            return 0

        # 3. Extract topics
        topics = await self._extract_topics(recent_memories)
        if not topics:
            logger.debug("Curiosity skipped — no topics extracted")
            return 0

        # Filter already-searched topics for this window
        fresh_topics = [t for t in topics if t not in _recently_searched]
        if not fresh_topics:
            logger.debug("Curiosity skipped — all topics recently searched: %s", topics)
            return 0

        logger.info("Curiosity cycle: searching topics %s", fresh_topics)

        # 4. Search every topic concurrently (standard + MCP sources)
        stored = 0
        for topic in fresh_topics:
            _recently_searched.add(topic)

            (
                arxiv_results,
                hn_results,
                wiki_results,
                ddg_results,
                brave_results,
            ) = await asyncio.gather(
                arxiv_search(topic, max_results=settings.curiosity_max_arxiv_results),
                hn_search(topic, max_results=settings.curiosity_max_hn_results),
                wikipedia_search(topic, max_results=2),
                duckduckgo_search(topic, max_results=2),
                brave_web_search(topic, max_results=settings.curiosity_max_brave_results),
            )

            # 4b. Enrich top URLs from Brave / HN with full page content via MCP fetch
            urls_to_fetch = [
                r.url for r in [*brave_results[:2], *hn_results[:2]] if r.url
            ]
            fetch_results = await mcp_fetch_results(urls_to_fetch, topic)

            all_results = [
                *arxiv_results, *hn_results, *wiki_results,
                *ddg_results, *brave_results, *fetch_results,
            ]
            logger.info(
                "Curiosity [%s]: arxiv=%d hn=%d wiki=%d ddg=%d brave=%d fetch=%d",
                topic, len(arxiv_results), len(hn_results),
                len(wiki_results), len(ddg_results),
                len(brave_results), len(fetch_results),
            )

            for result in all_results:
                if not result.title:
                    continue

                content = _format_finding(result, topic)

                # 5. Deduplicate
                if not await self._is_novel(content):
                    logger.debug("Curiosity dedup skip: %s", result.title[:70])
                    continue

                # 6. Store
                # Salience by source quality (MCP sources rank higher — richer content)
                _SALIENCE = {
                    "arxiv": 0.65,
                    "wikipedia": 0.60,
                    "brave": 0.70,
                    "fetch": 0.55,
                    "hn": 0.50,
                    "duckduckgo": 0.45,
                }
                salience = _SALIENCE.get(result.source, 0.50)
                await self._semantic.store(
                    content=content,
                    tags=["curiosity", f"source:{result.source}", topic],
                    salience=salience,
                )
                stored += 1
                logger.info(
                    "Curiosity stored [%s] %s",
                    result.source,
                    result.title[:80],
                )

        # 7. Periodically flush the recently-searched cache
        _cycle_counter += 1
        if _cycle_counter >= _CLEAR_AFTER_CYCLES:
            _recently_searched.clear()
            _cycle_counter = 0
            logger.debug("Curiosity search cache cleared")

        logger.info(
            "Curiosity cycle done: %d new memories (topics: %s)",
            stored,
            fresh_topics,
        )
        return stored
