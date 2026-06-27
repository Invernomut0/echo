"""UserInterestProfile — tracks the user's evolving curiosity map.

How it works
------------
After each interaction, ``infer_from_memories()`` scans recent episodic
memories that were created by the pipeline (not by the curiosity engine) and
extracts topic keywords via a lightweight LLM call.  Each topic receives an
*affinity score* in [0, 1] that is updated with an Exponential Moving Average
(α = 0.1) so the profile drifts slowly toward genuinely recurring interests.

Topics explicitly marked as "excluded" by the user are stored with a flag and
never surfaced as seeds or ZPD candidates.

The profile is persisted to the ``interest_profile`` table in the same SQLite
database as the rest of ECHO's memory.

ZPD (Zone of Proximal Development) topics
------------------------------------------
``zpd_topics()`` returns topics that are *close* to the user's primary
interests but not yet well-covered in semantic memory.  "Close" is measured
via ChromaDB vector-space cosine similarity: a topic is a good ZPD candidate
if its embedding is within a certain distance from a primary-interest
embedding but has fewer than N existing semantic memories covering it.

This requires zero extra LLM calls — the vector computation reuses the same
Ollama embedding endpoint already used by the memory stores.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import json
import logging
import time as _time
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from echo.core.config import settings
from echo.core.llm_client import llm

logger = logging.getLogger(__name__)

_DB_PATH: Path = settings.sqlite_path
_EMA_ALPHA: float = 0.10          # slow drift — don't over-react to single interactions
_PREFERRED_BOOST: float = 0.25    # boost when user explicitly marks as preferred
_MAX_TOPICS: int = 100            # cap the table size

# TTL caches — prevent repeated LLM calls from API polling
_ZPD_CACHE_TTL: float = 600.0    # 10 min — ZPD topics change slowly
_PRIMARY_CACHE_TTL: float = 300.0  # 5 min — profile updates after interactions

_TOPIC_EXTRACT_PROMPT = """\
Extract the main intellectual topics from the following AI-user conversation.
Focus on subjects the USER is interested in or asked about — not the AI's own interests.

Conversation:
{conversation_text}

Return ONLY a JSON array of 1-5 short topic strings (2-6 words each). Example:
["machine learning interpretability", "Stoic philosophy", "climate science"]
If no clear user interests are discernible, return [].
"""


class UserInterestProfile:
    """Persistent, incrementally-updated model of the user's topic interests."""

    # ------------------------------------------------------------------
    # DB init
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def _get_db(self):
        """Yield a configured SQLite connection and always close it safely."""
        db = await aiosqlite.connect(_DB_PATH)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await self._ensure_tables(db)
        try:
            yield db
        finally:
            await db.close()

    @staticmethod
    async def _ensure_tables(db: aiosqlite.Connection) -> None:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS interest_profile (
                topic            TEXT PRIMARY KEY,
                affinity_score   REAL NOT NULL DEFAULT 0.5,
                interaction_count INTEGER NOT NULL DEFAULT 1,
                last_seen        TEXT NOT NULL,
                is_excluded      INTEGER NOT NULL DEFAULT 0,
                is_preferred     INTEGER NOT NULL DEFAULT 0
            )
        """)
        await db.commit()

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    async def primary_interests(self, n: int = 5) -> list[dict]:
        """Return top-N active (non-excluded) topics sorted by affinity DESC."""
        async with self._get_db() as db:
            cursor = await db.execute(
                """
                SELECT topic, affinity_score, interaction_count, last_seen
                FROM interest_profile
                WHERE is_excluded = 0
                ORDER BY affinity_score DESC
                LIMIT ?
                """,
                (n,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def all_topics(self) -> list[dict]:
        """Return all tracked topics including excluded ones."""
        async with self._get_db() as db:
            cursor = await db.execute(
                "SELECT * FROM interest_profile ORDER BY affinity_score DESC"
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def excluded_topics(self) -> list[str]:
        async with self._get_db() as db:
            cursor = await db.execute(
                "SELECT topic FROM interest_profile WHERE is_excluded = 1"
            )
            rows = await cursor.fetchall()
            return [r["topic"] for r in rows]

    # ------------------------------------------------------------------
    # ZPD topics (vector-space, zero extra LLM calls)
    # ------------------------------------------------------------------

    # TTL cache for zpd_topics — avoids LLM call on every API poll
    _zpd_cache: tuple[float, list[str]] | None = None

    async def zpd_topics(self, n: int = 3) -> list[str]:
        """Return *n* ZPD topics — adjacent to primary interests but under-explored.

        Strategy:
        1. Take up to 5 primary interests.
        2. Ask the LLM to suggest 6 adjacent but unexplored topics.
        3. Filter out topics already in profile.
        4. Return top-n.

        Result cached for _ZPD_CACHE_TTL seconds to prevent LLM spam from API polling.
        """
        # Return cached result if fresh
        if self._zpd_cache is not None:
            ts, cached = self._zpd_cache
            if _time.monotonic() - ts < _ZPD_CACHE_TTL:
                return cached[:n]

        # Never run ZPD when user is active — save LLM budget for interactions
        try:
            from echo.core.user_activity import is_active as _ua  # noqa: PLC0415
            if _ua():
                logger.debug("ZPD skipped — user active")
                return []
        except Exception:  # noqa: BLE001
            pass

        primaries = await self.primary_interests(5)
        if not primaries:
            return []

        primary_labels = [p["topic"] for p in primaries]
        _ZPD_PROMPT = (
            "Given these topics a user is interested in:\n"
            + "\n".join(f"- {t}" for t in primary_labels)
            + "\n\nSuggest 6 short topics (2-5 words each) that are intellectually "
            "adjacent but likely not yet explored by the user. These should be "
            "genuinely novel connections or natural extensions.\n\n"
            'Return ONLY a JSON array of strings, e.g. ["topic a", "topic b", ...]'
        )

        try:
            raw = await llm.chat(
                [{
                    "role": "user",
                    "content": _ZPD_PROMPT,
                }],
                temperature=0.7,
                max_tokens=settings.llm_max_tokens_zpd_topics,
            )
            # Robust array extraction — handles markdown fences and thinking model output
            text = raw.strip()
            if text.startswith("```"):
                lines = text.splitlines()
                end_fence = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "```"), None)
                text = "\n".join(lines[1:end_fence] if end_fence else lines[1:]).strip()
            arr_start = text.find("[")
            arr_end = text.rfind("]")
            if arr_start == -1 or arr_end == -1:
                logger.warning("ZPD topic generation produced no JSON array (raw len=%d)", len(raw))
                return []
            candidates: list[str] = json.loads(text[arr_start : arr_end + 1])
            if not isinstance(candidates, list):
                return []
        except Exception as exc:  # noqa: BLE001
            logger.warning("ZPD topic generation failed: %s", exc)
            return []

        # Filter candidates: skip if too similar to existing profile topics
        excluded = set(await self.excluded_topics())
        existing = {p["topic"].lower() for p in await self.all_topics()}

        result: list[str] = []
        for cand in candidates:
            if not cand or not isinstance(cand, str):
                continue
            cand = cand.strip()
            if cand.lower() in excluded:
                continue
            # simple word-overlap check against existing profile
            cand_words = set(cand.lower().split())
            too_similar = any(
                len(cand_words & set(ex.split())) >= 2 for ex in existing
            )
            if not too_similar:
                result.append(cand)
            if len(result) >= n:
                break

        final = result[:n]
        # Cache result to avoid repeated LLM calls from API polling
        self._zpd_cache = (_time.monotonic(), final)
        return final

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    async def _upsert_topic(
        self,
        db: aiosqlite.Connection,
        topic: str,
        affinity_delta: float,
    ) -> None:
        """EMA update: new_score = old + α * delta (clamped to [0, 1])."""
        now = datetime.now(timezone.utc).isoformat()
        topic = topic.strip().lower()[:120]

        cursor = await db.execute(
            "SELECT affinity_score, interaction_count FROM interest_profile WHERE topic = ?",
            (topic,),
        )
        row = await cursor.fetchone()
        if row is None:
            # First time seeing this topic — start at 0.5 + delta
            new_score = max(0.0, min(1.0, 0.5 + affinity_delta))
            await db.execute(
                """INSERT INTO interest_profile (topic, affinity_score, interaction_count, last_seen)
                   VALUES (?, ?, 1, ?)""",
                (topic, round(new_score, 4), now),
            )
        else:
            old_score = row["affinity_score"]
            # Direct additive EMA: score drifts toward (old + delta) with momentum α
            new_score = old_score + _EMA_ALPHA * affinity_delta
            new_score = max(0.0, min(1.0, new_score))
            await db.execute(
                """UPDATE interest_profile
                   SET affinity_score = ?, interaction_count = interaction_count + 1, last_seen = ?
                   WHERE topic = ?""",
                (round(new_score, 4), now, topic),
            )
        await db.commit()

    async def record_feedback(self, topic: str, delta: float) -> None:
        """Adjust affinity for *topic* by *delta* (positive = more interested)."""
        async with self._get_db() as db:
            await self._upsert_topic(db, topic, delta)

    async def mark_excluded(self, topic: str) -> None:
        """Exclude *topic* from interest seeds and ZPD candidates."""
        topic = topic.strip().lower()
        async with self._get_db() as db:
            await db.execute(
                """INSERT INTO interest_profile (topic, affinity_score, interaction_count, last_seen, is_excluded)
                   VALUES (?, 0.0, 0, ?, 1)
                   ON CONFLICT(topic) DO UPDATE SET is_excluded = 1""",
                (topic, datetime.now(timezone.utc).isoformat()),
            )
            await db.commit()

    async def mark_preferred(self, topic: str) -> None:
        """Mark *topic* as explicitly preferred — boosts affinity."""
        topic = topic.strip().lower()
        now = datetime.now(timezone.utc).isoformat()
        async with self._get_db() as db:
            await db.execute(
                """INSERT INTO interest_profile (topic, affinity_score, interaction_count, last_seen, is_preferred)
                   VALUES (?, ?, 1, ?, 1)
                   ON CONFLICT(topic) DO UPDATE SET
                       is_preferred = 1,
                       is_excluded = 0,
                       affinity_score = MIN(1.0, affinity_score + ?),
                       last_seen = ?""",
                (topic, min(1.0, 0.5 + _PREFERRED_BOOST), now, _PREFERRED_BOOST, now),
            )
            await db.commit()

    # ------------------------------------------------------------------
    # Inference from memories (called post-interaction)
    # ------------------------------------------------------------------

    async def infer_from_memories(
        self,
        conversation_text: str | None = None,
        user_input: str | None = None,
        response: str | None = None,
    ) -> list[str]:
        """Extract user interest topics from a conversation and update the profile.

        Pass either ``conversation_text`` directly or ``user_input`` + ``response``
        to build it automatically.  Returns the list of extracted topics.
        """
        if conversation_text is None:
            if user_input is None:
                return []
            combined = f"User: {user_input}"
            if response:
                combined += f"\nECHO: {response}"
            conversation_text = combined

        if len(conversation_text.strip()) < 20:
            return []

        # Trim to keep prompt size reasonable
        conversation_text = conversation_text[:1500]

        try:
            raw = await llm.chat(
                [{"role": "user", "content": _TOPIC_EXTRACT_PROMPT.format(conversation_text=conversation_text)}],
                temperature=0.3,
                max_tokens=settings.llm_max_tokens_interest_infer,
            )
            _text = raw.strip()
            if _text.startswith("```"):
                _lines = _text.splitlines()
                _ef = next((i for i, l in enumerate(_lines[1:], 1) if l.strip() == "```"), None)
                _text = "\n".join(_lines[1:_ef] if _ef else _lines[1:]).strip()
            _as = _text.find("["); _ae = _text.rfind("]")
            topics: list[str] = json.loads(_text[_as:_ae+1]) if _as != -1 and _ae != -1 else []
            if not isinstance(topics, list):
                return []
            topics = [str(t).strip() for t in topics if t and isinstance(t, str)][:5]
        except Exception as exc:  # noqa: BLE001
            logger.debug("Interest inference LLM failed: %s", exc)
            return []

        if not topics:
            return []

        # Count current topics — if at cap, only update existing ones
        async with self._get_db() as db:
            cursor = await db.execute("SELECT COUNT(*) as cnt FROM interest_profile")
            row = await cursor.fetchone()
            at_cap = row["cnt"] >= _MAX_TOPICS if row else False

            for topic in topics:
                cursor2 = await db.execute(
                    "SELECT topic FROM interest_profile WHERE topic = ?",
                    (topic.lower().strip()[:120],),
                )
                exists = await cursor2.fetchone()
                if at_cap and not exists:
                    continue  # skip new topics when at cap
                # Use a positive delta to actually grow affinity on repeated mentions
                await self._upsert_topic(db, topic, affinity_delta=0.15)

        logger.debug("Interest profile updated: %s", topics)
        return topics


# Module-level singleton
interest_profile = UserInterestProfile()
