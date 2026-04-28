"""Episodic memory store backed by ChromaDB (vectors) + SQLite (metadata)."""

from __future__ import annotations

import json
import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, Float, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession

from echo.core.db import Base, get_or_create_collection, get_session_factory
from echo.core.llm_client import llm
from echo.core.types import MemoryEntry, MemoryType

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "episodic_memory"


# ---------------------------------------------------------------------------
# SQLAlchemy ORM model
# ---------------------------------------------------------------------------

class MemoryRow(Base):
    __tablename__ = "episodic_memories"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    content = Column(Text, nullable=False)
    memory_type = Column(String, default=MemoryType.EPISODIC.value)
    importance = Column(Float, default=0.5)
    novelty = Column(Float, default=0.5)
    self_relevance = Column(Float, default=0.5)
    emotional_weight = Column(Float, default=0.0)
    salience = Column(Float, default=0.5)
    decay_lambda = Column(Float, default=0.5)
    current_strength = Column(Float, default=1.0)
    embedding_id = Column(String, nullable=True)
    created_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    last_accessed = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    access_count = Column(Integer, default=0)
    linked_ids = Column(Text, default="[]")  # JSON list
    tags = Column(Text, default="[]")  # JSON list
    source_agent = Column(String, default="system")


def _row_to_entry(row: MemoryRow) -> MemoryEntry:
    return MemoryEntry(
        id=row.id,
        content=row.content,
        memory_type=MemoryType(row.memory_type),
        importance=row.importance,
        novelty=row.novelty,
        self_relevance=row.self_relevance,
        emotional_weight=row.emotional_weight,
        salience=row.salience,
        decay_lambda=row.decay_lambda,
        current_strength=row.current_strength,
        embedding_id=row.embedding_id,
        created_at=datetime.fromisoformat(row.created_at),
        last_accessed=datetime.fromisoformat(row.last_accessed),
        access_count=row.access_count,
        linked_ids=json.loads(row.linked_ids or "[]"),
        tags=json.loads(row.tags or "[]"),
        source_agent=row.source_agent,
    )


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class EpisodicMemoryStore:
    """Store + retrieve episodic memories using semantic similarity."""

    def __init__(self) -> None:
        self._collection = get_or_create_collection(_COLLECTION_NAME)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def store(self, entry: MemoryEntry) -> MemoryEntry:
        """Persist a memory entry (embedding + metadata)."""
        entry.compute_salience()

        # Embed the content
        vector = await llm.embed_one(entry.content)
        entry.embedding_id = entry.id

        # Store in ChromaDB
        self._collection.upsert(
            ids=[entry.embedding_id],
            embeddings=[vector],
            documents=[entry.content],
            metadatas=[{"memory_id": entry.id, "salience": entry.salience}],
        )

        # Store metadata in SQLite
        factory = get_session_factory()
        async with factory() as session:
            row = MemoryRow(
                id=entry.id,
                content=entry.content,
                memory_type=entry.memory_type.value,
                importance=entry.importance,
                novelty=entry.novelty,
                self_relevance=entry.self_relevance,
                emotional_weight=entry.emotional_weight,
                salience=entry.salience,
                decay_lambda=entry.decay_lambda,
                current_strength=entry.current_strength,
                embedding_id=entry.embedding_id,
                created_at=entry.created_at.isoformat(),
                last_accessed=entry.last_accessed.isoformat(),
                access_count=entry.access_count,
                linked_ids=json.dumps(entry.linked_ids),
                tags=json.dumps(entry.tags),
                source_agent=entry.source_agent,
            )
            session.add(row)
            await session.commit()

        logger.debug("Stored episodic memory %s (salience=%.2f)", entry.id, entry.salience)
        return entry

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------

    async def retrieve_similar(
        self,
        query: str,
        n_results: int = 5,
        min_strength: float = 0.1,
    ) -> list[MemoryEntry]:
        """Semantic search — returns top-k memories by cosine similarity."""
        vector = await llm.embed_one(query)
        results = self._collection.query(
            query_embeddings=[vector],
            n_results=min(n_results, self._collection.count() or 1),
            include=["metadatas", "distances"],
        )
        if not results["ids"] or not results["ids"][0]:
            return []

        ids = results["ids"][0]
        factory = get_session_factory()
        async with factory() as session:
            stmt = select(MemoryRow).where(MemoryRow.id.in_(ids))
            rows = (await session.execute(stmt)).scalars().all()

        entries = [_row_to_entry(r) for r in rows if r.current_strength >= min_strength]

        # Touch access stats
        now_iso = datetime.now(timezone.utc).isoformat()
        async with factory() as session:
            for e in entries:
                stmt_u = (
                    select(MemoryRow).where(MemoryRow.id == e.id)
                )
                row = (await session.execute(stmt_u)).scalar_one_or_none()
                if row:
                    row.access_count = row.access_count + 1
                    row.last_accessed = now_iso
            await session.commit()

        return entries

    async def get_all(self, limit: int = 200) -> list[MemoryEntry]:
        factory = get_session_factory()
        async with factory() as session:
            stmt = select(MemoryRow).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
        return [_row_to_entry(r) for r in rows]

    async def get_by_id(self, memory_id: str) -> MemoryEntry | None:
        factory = get_session_factory()
        async with factory() as session:
            row = (
                await session.execute(select(MemoryRow).where(MemoryRow.id == memory_id))
            ).scalar_one_or_none()
        return _row_to_entry(row) if row else None

    # ------------------------------------------------------------------
    # Decay
    # ------------------------------------------------------------------

    async def apply_decay(self, elapsed_seconds: float) -> int:
        """Apply exponential decay I(t) = I₀·e^(−λ·Δt) to all memories.

        Returns count of memories below 0.01 strength (prunable).
        """
        elapsed_hours = elapsed_seconds / 3600.0
        factory = get_session_factory()
        prunable = 0
        async with factory() as session:
            rows = (await session.execute(select(MemoryRow))).scalars().all()
            for row in rows:
                new_strength = row.current_strength * math.exp(
                    -row.decay_lambda * elapsed_hours
                )
                row.current_strength = max(0.0, round(new_strength, 6))
                if row.current_strength < 0.01:
                    prunable += 1
            await session.commit()
        logger.debug("Decay applied to %d memories (%d prunable)", len(rows), prunable)
        return prunable

    async def prune_weak(self, threshold: float = 0.01) -> int:
        """Delete memories below strength threshold. Returns count deleted."""
        factory = get_session_factory()
        async with factory() as session:
            rows = (await session.execute(select(MemoryRow))).scalars().all()
            to_delete = [r for r in rows if r.current_strength < threshold]
            ids_to_delete = [r.id for r in to_delete]
            for row in to_delete:
                await session.delete(row)
            await session.commit()

        if ids_to_delete:
            self._collection.delete(ids=ids_to_delete)
            logger.info("Pruned %d weak memories", len(ids_to_delete))

        return len(ids_to_delete)

    def count(self) -> int:
        return self._collection.count()
