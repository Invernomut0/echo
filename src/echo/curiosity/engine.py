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
from typing import Any

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
from echo.memory.goals import goal_store, MAX_ACTIVE_GOALS

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
# Activity log — persists the last _MAX_LOG cycle records in memory
# ---------------------------------------------------------------------------
_activity_log: list[dict[str, Any]] = []
_MAX_LOG: int = 200
_is_running: bool = False

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

# ZPD cycle: every N cycles use zpd_topics() instead of normal topics
_ZPD_EVERY_N_CYCLES: int = 4

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
            memory_topics = json.loads(raw.strip())
            if not isinstance(memory_topics, list):
                memory_topics = []
        except Exception as exc:  # noqa: BLE001
            logger.warning("Topic extraction failed (%s) — using fallback", exc)
            memory_topics = []

        # Blend with user interest profile (50/50 when profile has data)
        interest_seeds: list[str] = []
        try:
            from echo.curiosity.interest_profile import interest_profile  # noqa: PLC0415
            primaries = await interest_profile.primary_interests(n=3)
            interest_seeds = [p["topic"] for p in primaries]
        except Exception as exc:  # noqa: BLE001
            logger.debug("Interest profile unavailable: %s", exc)

        combined = memory_topics + [s for s in interest_seeds if s not in memory_topics]
        topics = [str(t).strip() for t in combined[:settings.curiosity_max_topics] if t]

        if topics:
            return topics

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
    # Goal management cycle
    # ------------------------------------------------------------------

    _GOAL_REFLECT_PROMPT = """\
You are the autonomous reasoning core of ECHO, an AI assistant.

## Recent conversations (newest first):
{conversations}

## Internal state:
{meta_state}

## Current active goals ({active_count}/{max_goals}):
{active_goals}

Your task:
1. Review the recent conversations and internal state.
2. Decide whether any active goals have been ACHIEVED (respond naturally shows success) or should be ABANDONED.
3. Propose NEW goals if there is room (max {max_goals} total active). Goals must be concrete, achievable and meaningful for ECHO's development.
4. For each active goal that still needs work, plan the NEXT ACTION to take.

Respond ONLY with valid JSON:
{{
  "achieved_ids": ["<goal_id>", ...],
  "abandoned_ids": ["<goal_id>", ...],
  "new_goals": [
    {{"title": "...", "description": "...", "priority": 0.7}}
  ],
  "next_actions": [
    {{"goal_id": "<id>", "action": "...", "search_query": "..."}}
  ]
}}"""

    _GOAL_PURSUE_PROMPT = """\
You are working on the following goal for ECHO:

Goal: {goal_title}
Description: {goal_description}

You searched for: {search_query}

Search results:
{search_results}

Based on these results:
1. Summarise what you found that is relevant to the goal (2-4 sentences).
2. Decide if the goal is now ACHIEVED or needs more work.

Respond ONLY with valid JSON:
{{
  "summary": "...",
  "achieved": true | false,
  "next_step": "..." (if not achieved, what to do next)
}}"""

    @staticmethod
    def _extract_json(raw: str) -> dict:
        """Extract JSON from LLM output that may be wrapped in markdown code fences."""
        text = raw.strip()
        # Strip ```json ... ``` or ``` ... ``` fences
        if text.startswith("```"):
            lines = text.splitlines()
            # drop first line (```json or ```) and last line (```)
            inner = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            text = inner.strip()
        # Find first { and last }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start : end + 1]
        return json.loads(text)

    async def _run_goal_cycle(self, recent_memories: list[Any]) -> None:
        """Review state, update goals, and pursue active goals with searches."""
        try:
            # Build context
            conversations = "\n".join(
                f"- {m.content[:200]}" for m in recent_memories[:10]
            )
            active_goals = await goal_store.list_active()

            # Get meta state if available
            try:
                from echo.core.pipeline import pipeline  # noqa: PLC0415
                meta = pipeline.meta_state
                meta_state_text = (
                    f"Mood: {getattr(meta, 'mood', 'unknown')} | "
                    f"Energy: {getattr(meta, 'energy_level', 'unknown')} | "
                    f"Coherence: {getattr(meta, 'coherence_index', 'unknown')}"
                )
            except Exception:  # noqa: BLE001
                meta_state_text = "State unavailable"

            # Format active goals for prompt
            if active_goals:
                goals_text = "\n".join(
                    f"  [{g['id'][:8]}] {g['title']} — {g['description'][:100]}"
                    for g in active_goals
                )
            else:
                goals_text = "  (none)"

            # Step 1: Reflect and plan
            reflect_raw = await llm.chat(
                messages=[{
                    "role": "user",
                    "content": self._GOAL_REFLECT_PROMPT.format(
                        conversations=conversations or "(no recent conversations)",
                        meta_state=meta_state_text,
                        active_goals=goals_text,
                        active_count=len(active_goals),
                        max_goals=MAX_ACTIVE_GOALS,
                    ),
                }],
                temperature=0.4,
                max_tokens=600,
            )

            logger.debug("[Goals] reflect raw: %s", reflect_raw[:400])
            try:
                plan = self._extract_json(reflect_raw)
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("[Goals] reflection parse error (%s): %s", exc, reflect_raw[:300])
                return
            logger.info("[Goals] plan — new:%d achieved:%d abandoned:%d actions:%d",
                        len(plan.get('new_goals', [])),
                        len(plan.get('achieved_ids', [])),
                        len(plan.get('abandoned_ids', [])),
                        len(plan.get('next_actions', [])))

            # Step 2: Mark achieved goals
            for gid in plan.get("achieved_ids", []):
                # find full id (might be truncated to 8 chars)
                matched = next((g for g in active_goals if g["id"].startswith(gid)), None)
                if matched:
                    await goal_store.update_status(matched["id"], "achieved")
                    await goal_store.add_action(
                        matched["id"],
                        description="Goal marked as achieved during reflection cycle",
                        result="Achieved",
                        status="done",
                    )
                    logger.info("[Goals] Achieved: %s", matched["title"])

            # Step 3: Abandon goals
            for gid in plan.get("abandoned_ids", []):
                matched = next((g for g in active_goals if g["id"].startswith(gid)), None)
                if matched:
                    await goal_store.update_status(matched["id"], "abandoned")
                    logger.info("[Goals] Abandoned: %s", matched["title"])

            # Step 4: Create new goals
            current_count = await goal_store.count_active()
            for ng in plan.get("new_goals", []):
                if current_count >= MAX_ACTIVE_GOALS:
                    break
                try:
                    created = await goal_store.create(
                        title=ng.get("title", "")[:200],
                        description=ng.get("description", "")[:500],
                        priority=float(ng.get("priority", 0.5)),
                    )
                    current_count += 1
                    logger.info("[Goals] New goal: %s", created["title"])
                    await goal_store.add_action(
                        created["id"],
                        description="Goal defined during curiosity reflection cycle",
                        result="Created",
                        status="done",
                    )
                except ValueError:
                    break

            # Step 5: Pursue active goals with search
            active_goals = await goal_store.list_active()  # refresh after updates
            for action_plan in plan.get("next_actions", [])[:2]:  # max 2 pursuits per cycle
                gid = action_plan.get("goal_id", "")
                goal = next((g for g in active_goals if g["id"].startswith(gid)), None)
                if not goal:
                    continue
                query = action_plan.get("search_query", action_plan.get("action", ""))
                if not query:
                    continue

                # Record the planned action
                await goal_store.add_action(
                    goal["id"],
                    description=f"Searching: {action_plan.get('action', query)}",
                    result="In progress…",
                    status="pending",
                )

                # Search
                try:
                    results = await asyncio.gather(
                        arxiv_search(query, max_results=2),
                        hn_search(query, max_results=2),
                        brave_web_search(query, max_results=2),
                    )
                    all_results = [r for sublist in results for r in sublist]
                    search_text = "\n".join(
                        f"- [{r.source}] {r.title}: {r.snippet[:200]}"
                        for r in all_results[:6]
                    ) or "(no results found)"
                except Exception as exc:  # noqa: BLE001
                    search_text = f"Search failed: {exc}"
                    all_results = []

                # Ask LLM to interpret results
                try:
                    pursue_raw = await llm.chat(
                        messages=[{
                            "role": "user",
                            "content": self._GOAL_PURSUE_PROMPT.format(
                                goal_title=goal["title"],
                                goal_description=goal["description"],
                                search_query=query,
                                search_results=search_text,
                            ),
                        }],
                        temperature=0.3,
                        max_tokens=300,
                    )
                    pursue = self._extract_json(pursue_raw)
                except Exception:  # noqa: BLE001
                    pursue = {"summary": search_text[:300], "achieved": False}

                summary = pursue.get("summary", "")[:400]
                achieved = pursue.get("achieved", False)

                # Update the action with results
                await goal_store.add_action(
                    goal["id"],
                    description=f"Result for: {action_plan.get('action', query)}",
                    result=summary,
                    status="done",
                )

                # Store as semantic memory
                if summary and await self._is_novel(summary):
                    await self._semantic.store(
                        content=f"[Goal research: {goal['title']}] {summary}",
                        source_agent="goals",
                        tags=["goals", f"goal:{goal['id'][:8]}"],
                        salience=0.6,
                    )

                if achieved:
                    await goal_store.update_status(goal["id"], "achieved")
                    await goal_store.add_action(
                        goal["id"],
                        description="Goal achieved through research",
                        result=summary,
                        status="done",
                    )
                    logger.info("[Goals] Goal achieved via research: %s", goal["title"])

        except Exception as exc:  # noqa: BLE001
            logger.error("[Goals] Goal cycle failed: %s", exc, exc_info=True)

    # ------------------------------------------------------------------
    # Main cycle
    # ------------------------------------------------------------------

    async def run_cycle(self) -> int:
        """Run one curiosity cycle; return the number of new memories stored."""
        global _cycle_counter, _recently_searched, _is_running  # noqa: PLW0603

        # ── Activity record ──────────────────────────────────────────────────
        started_at = datetime.now(timezone.utc)
        record: dict[str, Any] = {
            "id": str(int(started_at.timestamp() * 1000)),
            "started_at": started_at.isoformat(),
            "finished_at": None,
            "status": "running",
            "skip_reason": None,
            "idle_seconds": None,
            "topics_proposed": [],
            "topics_searched": [],
            "results_by_source": {},
            "total_found": 0,
            "total_stored": 0,
            "total_deduped": 0,
            "findings": [],
        }
        _activity_log.append(record)
        if len(_activity_log) > _MAX_LOG:
            _activity_log.pop(0)

        def _done(status: str, reason: str | None = None, stored: int = 0) -> int:
            record["status"] = status
            record["skip_reason"] = reason
            record["finished_at"] = datetime.now(timezone.utc).isoformat()
            return stored

        _is_running = True
        try:
            if not settings.curiosity_enabled:
                return _done("skipped", "disabled")

            # 1. Load recent episodic memories
            recent_memories = await self._episodic.get_all(limit=20)
            if not recent_memories:
                logger.debug("Curiosity skipped — no episodic memories yet")
                return _done("skipped", "no_episodic_memories")

            # 2. Idle guard — skip if the user was active within the threshold
            most_recent = recent_memories[0]       # sorted DESC by created_at
            last_at: datetime = most_recent.created_at
            if last_at.tzinfo is None:
                last_at = last_at.replace(tzinfo=timezone.utc)
            idle_seconds = (datetime.now(timezone.utc) - last_at).total_seconds()
            record["idle_seconds"] = round(idle_seconds, 1)
            threshold = settings.curiosity_idle_threshold_seconds

            if idle_seconds < threshold:
                logger.debug(
                    "Curiosity skipped — last interaction %.0fs ago (threshold %ds)",
                    idle_seconds,
                    threshold,
                )
                return _done("skipped", f"not_idle ({idle_seconds:.0f}s < {threshold}s)")

            # 2b. Goal management — always run when idle
            await self._run_goal_cycle(recent_memories)

            # 3. Extract topics (or use ZPD topics every N cycles)
            _is_zpd_cycle = (_cycle_counter % _ZPD_EVERY_N_CYCLES == (_ZPD_EVERY_N_CYCLES - 1))
            if _is_zpd_cycle:
                try:
                    from echo.curiosity.interest_profile import interest_profile as _ip  # noqa: PLC0415
                    zpd = await _ip.zpd_topics(n=3)
                    if zpd:
                        topics = zpd
                        logger.info("Curiosity ZPD cycle: topics %s", topics)
                    else:
                        topics = await self._extract_topics(recent_memories)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("ZPD cycle fallback: %s", exc)
                    topics = await self._extract_topics(recent_memories)
            else:
                topics = await self._extract_topics(recent_memories)
            record["topics_proposed"] = topics
            if not topics:
                logger.debug("Curiosity skipped — no topics extracted")
                return _done("skipped", "no_topics_extracted")

            # Filter already-searched topics for this window
            fresh_topics = [t for t in topics if t not in _recently_searched]
            record["topics_searched"] = fresh_topics
            if not fresh_topics:
                logger.debug("Curiosity skipped — all topics recently searched: %s", topics)
                return _done("skipped", "all_topics_recently_searched")

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

                # Track per-source result counts
                for src, res in [
                    ("arxiv", arxiv_results), ("hn", hn_results),
                    ("wikipedia", wiki_results), ("duckduckgo", ddg_results),
                    ("brave", brave_results), ("fetch", fetch_results),
                ]:
                    if res:
                        record["results_by_source"][src] = (
                            record["results_by_source"].get(src, 0) + len(res)
                        )

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

                    record["total_found"] += 1
                    content = _format_finding(result, topic)

                    # 5. Deduplicate
                    if not await self._is_novel(content):
                        logger.debug("Curiosity dedup skip: %s", result.title[:70])
                        record["total_deduped"] += 1
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
                    record["total_stored"] += 1
                    record["findings"].append({
                        "title": result.title[:120],
                        "source": result.source,
                        "topic": topic,
                        "url": result.url or None,
                    })
                    logger.info(
                        "Curiosity stored [%s] %s",
                        result.source,
                        result.title[:80],
                    )

            # 8b. Enqueue top-3 findings by affinity into StimulusQueue
            try:
                from echo.curiosity.interest_profile import interest_profile as _ip  # noqa: PLC0415
                from echo.curiosity.stimulus_queue import stimulus_queue as _sq  # noqa: PLC0415
                primaries = await _ip.primary_interests(n=10)
                affinity_map = {p["topic"]: p["affinity_score"] for p in primaries}

                # Score and sort findings for this topic by affinity match
                ranked_findings = sorted(
                    record["findings"],
                    key=lambda f: affinity_map.get(f["topic"], 0.0),
                    reverse=True,
                )
                enqueued = 0
                for finding in ranked_findings:
                    if enqueued >= 3:
                        break
                    aff = affinity_map.get(finding["topic"], 0.0)
                    if aff < 0.3:
                        continue  # only enqueue if topic has some affinity
                    # Build a compact stimulus text
                    stimulus_text = f"[{finding['source']}] {finding['title']}"
                    await _sq.enqueue(
                        content=stimulus_text,
                        topic=finding["topic"],
                        affinity_score=aff,
                    )
                    enqueued += 1
            except Exception as exc:  # noqa: BLE001
                logger.debug("Stimulus enqueue failed: %s", exc)

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
            return _done("completed", stored=stored)

        except Exception as exc:  # noqa: BLE001
            logger.exception("Curiosity cycle error")
            _done("error", str(exc)[:200])
            raise
        finally:
            _is_running = False
