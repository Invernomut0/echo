"""StimulusQueue — ranked queue of proactive knowledge stimuli for the user.

When the CuriosityEngine finds a finding that matches one of the user's
primary interests, it enqueues it here.  At each interaction, the pipeline
can dequeue one pending stimulus and inject it silently into the workspace so
ECHO can decide, in context, whether and how to surface it naturally.

Feedback loop
-------------
When a stimulus is presented (injected) and the following interaction produces
a memory with high ``self_relevance`` (> 0.7), the pipeline records *implicit
positive feedback* automatically.  The user can also rate findings explicitly
via the API.  Both paths call ``record_feedback()`` which propagates to
``UserInterestProfile.record_feedback()`` to reinforce the relevant topic.

Schema
------
``stimulus_queue`` table (persistent, SQLite):
  id               TEXT PK
  content          TEXT        — formatted finding text
  source_memory_id TEXT        — semantic memory id that originated this (can be None)
  topic            TEXT        — interest topic this finding was matched to
  affinity_score   REAL        — affinity at enqueue time (used for ranking)
  created_at       TEXT        — ISO-8601
  presented_at     TEXT NULL   — set when injected into workspace
  feedback_score   REAL NULL   — explicit user rating [0, 1]
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from echo.core.config import settings

logger = logging.getLogger(__name__)

_DB_PATH: Path = settings.sqlite_path


class StimulusQueue:
    """Persistent ranked queue of curiosity stimuli waiting to be shown to the user."""

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    async def _get_db(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(_DB_PATH)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await self._ensure_tables(db)
        return db

    @staticmethod
    async def _ensure_tables(db: aiosqlite.Connection) -> None:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stimulus_queue (
                id               TEXT PRIMARY KEY,
                content          TEXT NOT NULL,
                source_memory_id TEXT,
                topic            TEXT NOT NULL DEFAULT '',
                affinity_score   REAL NOT NULL DEFAULT 0.5,
                created_at       TEXT NOT NULL,
                presented_at     TEXT,
                feedback_score   REAL
            )
        """)
        await db.commit()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def enqueue(
        self,
        content: str,
        topic: str,
        affinity_score: float = 0.5,
        source_memory_id: str | None = None,
    ) -> str:
        """Add a finding to the queue.  Skips if identical source already pending.

        Returns the new stimulus id.
        """
        now = datetime.now(timezone.utc).isoformat()
        sid = str(uuid.uuid4())

        async with await self._get_db() as db:
            # Avoid double-enqueuing the same memory finding
            if source_memory_id:
                cursor = await db.execute(
                    "SELECT id FROM stimulus_queue WHERE source_memory_id = ? AND presented_at IS NULL",
                    (source_memory_id,),
                )
                if await cursor.fetchone():
                    logger.debug("Stimulus already pending for memory %s — skipping", source_memory_id[:16])
                    return ""

            await db.execute(
                """INSERT INTO stimulus_queue
                   (id, content, source_memory_id, topic, affinity_score, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (sid, content[:800], source_memory_id, topic, round(affinity_score, 4), now),
            )
            await db.commit()

        logger.debug("Stimulus enqueued: topic=%s affinity=%.2f", topic, affinity_score)
        return sid

    async def mark_presented(self, stimulus_id: str) -> None:
        """Record that a stimulus was injected into a pipeline context."""
        now = datetime.now(timezone.utc).isoformat()
        async with await self._get_db() as db:
            await db.execute(
                "UPDATE stimulus_queue SET presented_at = ? WHERE id = ?",
                (now, stimulus_id),
            )
            await db.commit()

    async def record_feedback(
        self,
        stimulus_id: str,
        score: float,
    ) -> None:
        """Store explicit feedback score and propagate topic affinity update."""
        score = max(0.0, min(1.0, score))
        async with await self._get_db() as db:
            cursor = await db.execute(
                "SELECT topic FROM stimulus_queue WHERE id = ?", (stimulus_id,)
            )
            row = await cursor.fetchone()
            if not row:
                logger.warning("Stimulus id %s not found", stimulus_id)
                return

            topic = row["topic"]
            await db.execute(
                "UPDATE stimulus_queue SET feedback_score = ? WHERE id = ?",
                (score, stimulus_id),
            )
            await db.commit()

        # Propagate to interest profile (delta centred on neutral 0.5)
        delta = (score - 0.5) * 0.2   # maps [0,1] → [-0.10, +0.10]
        try:
            from echo.curiosity.interest_profile import interest_profile  # noqa: PLC0415
            await interest_profile.record_feedback(topic, delta)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Feedback propagation failed: %s", exc)

    async def clear_stale(self, max_age_hours: int = 48) -> int:
        """Delete presented or old items; return count deleted."""
        from datetime import timedelta  # noqa: PLC0415
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
        async with await self._get_db() as db:
            cursor = await db.execute(
                """DELETE FROM stimulus_queue
                   WHERE presented_at IS NOT NULL
                      OR (presented_at IS NULL AND created_at < ?)""",
                (cutoff,),
            )
            await db.commit()
            return cursor.rowcount

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def pending(self, limit: int = 10) -> list[dict]:
        """Return pending stimuli ordered by affinity DESC."""
        async with await self._get_db() as db:
            cursor = await db.execute(
                """SELECT id, content, topic, affinity_score, created_at
                   FROM stimulus_queue
                   WHERE presented_at IS NULL
                   ORDER BY affinity_score DESC
                   LIMIT ?""",
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def pop_best(self) -> dict | None:
        """Return and mark-as-presented the highest-affinity pending stimulus."""
        items = await self.pending(limit=1)
        if not items:
            return None
        item = items[0]
        await self.mark_presented(item["id"])
        return item

    async def all_items(self, limit: int = 50) -> list[dict]:
        """Return all items (including presented) newest first."""
        async with await self._get_db() as db:
            cursor = await db.execute(
                """SELECT * FROM stimulus_queue ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


# Module-level singleton
stimulus_queue = StimulusQueue()
