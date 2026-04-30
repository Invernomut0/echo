"""Episodic memory store backed by ChromaDB (vectors) + SQLite (metadata)."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, Column, Float, Integer, String, Text, select, update
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
    is_dormant = Column(Boolean, default=False)   # set by light consolidation; cleared on access
    has_vector = Column(Boolean, default=False)   # True when vector is in ChromaDB


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
        is_dormant=bool(row.is_dormant),
        has_vector=bool(row.has_vector),
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

        # Chunk long texts so each segment gets its own embedding vector.
        # Short texts (≤ CHUNK_MIN_LEN chars) return a single-element list.
        from echo.memory.chunker import chunk_ids, chunk_text
        chunks = chunk_text(entry.content)
        vectors = await llm.embed(chunks)  # batch: one call regardless of chunk count

        ids_c = chunk_ids(entry.id, len(chunks))
        entry.embedding_id = ids_c[0]

        # Store in ChromaDB only when valid vectors are available
        has_vector = False
        if vectors and len(vectors) == len(chunks):
            try:
                self._collection.upsert(
                    ids=ids_c,
                    embeddings=vectors,
                    documents=chunks,
                    metadatas=[
                        {"memory_id": entry.id, "chunk_index": i, "salience": entry.salience}
                        for i in range(len(chunks))
                    ],
                )
                has_vector = True
            except Exception as exc:  # noqa: BLE001
                logger.warning("ChromaDB upsert skipped: %s", exc)
        entry.has_vector = has_vector

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
                is_dormant=False,
                has_vector=has_vector,
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
        query_vector: list[float] | None = None,
    ) -> list[MemoryEntry]:
        """Semantic search — returns top-k memories by cosine similarity.

        ``query_vector`` may be supplied by the caller to avoid a redundant
        embedding round-trip when the same query is already embedded elsewhere
        (e.g. pipeline.py pre-computes one vector shared by episodic + semantic).

        Returns [] gracefully when the embedding service (LM Studio) is offline.
        """
        loop = asyncio.get_event_loop()

        vector = query_vector if query_vector else await llm.embed_one(query)
        if not vector:
            # Embedding service unavailable — skip memory retrieval
            logger.debug("embed_one returned empty — skipping memory retrieval")
            return []
        try:
            col_count = await loop.run_in_executor(None, self._collection.count) or 1
            results = await loop.run_in_executor(
                None,
                lambda: self._collection.query(
                    query_embeddings=[vector],
                    # Request n*3 raw chunk results so dedup still yields n unique memories
                    n_results=min(n_results * 3, col_count),
                    include=["metadatas", "distances"],
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("ChromaDB query failed: %s", exc)
            return []
        if not results["ids"] or not results["ids"][0]:
            return []

        chunk_ids_raw = results["ids"][0]
        distances = results["distances"][0]
        # Filter by cosine distance — discard memories too dissimilar to the query.
        # ChromaDB cosine space: distance = 1 - cosine_similarity (0 = identical, 2 = opposite).
        # 0.5 → similarity ≥ 0.5, a reasonable relevance floor.
        _MAX_COSINE_DIST = 0.5

        # Deduplicate chunk results → best cosine distance per parent memory ID.
        # memory_id_from_chunk_id is backward-compatible: bare IDs pass through unchanged.
        from echo.memory.chunker import memory_id_from_chunk_id
        best_dist: dict[str, float] = {}
        for cid, dist in zip(chunk_ids_raw, distances):
            mem_id = memory_id_from_chunk_id(cid)
            if mem_id not in best_dist or dist < best_dist[mem_id]:
                best_dist[mem_id] = dist

        mem_ids = [mid for mid, dist in best_dist.items() if dist <= _MAX_COSINE_DIST]
        if not mem_ids:
            return []

        factory = get_session_factory()
        async with factory() as session:
            stmt = select(MemoryRow).where(MemoryRow.id.in_(mem_ids))
            rows = (await session.execute(stmt)).scalars().all()

        entries = [_row_to_entry(r) for r in rows if r.current_strength >= min_strength]

        # Bulk-update access stats — single statement replaces the old N+1 loop.
        if entries:
            from sqlalchemy import update as sa_update  # noqa: PLC0415
            now_iso = datetime.now(timezone.utc).isoformat()
            entry_ids = [e.id for e in entries]
            async with factory() as session:
                await session.execute(
                    sa_update(MemoryRow)
                    .where(MemoryRow.id.in_(entry_ids))
                    .values(
                        access_count=MemoryRow.access_count + 1,
                        last_accessed=now_iso,
                    )
                )
                await session.commit()

        return entries

    async def get_all(
        self,
        limit: int = 200,
        include_dormant: bool = False,
    ) -> list[MemoryEntry]:
        """Return memories from SQLite, newest first.  Dormant ones are excluded by default."""
        factory = get_session_factory()
        async with factory() as session:
            stmt = select(MemoryRow)
            if not include_dormant:
                stmt = stmt.where(MemoryRow.is_dormant.is_(False))
            stmt = stmt.order_by(MemoryRow.created_at.desc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
        return [_row_to_entry(r) for r in rows]

    async def get_dormant(self, limit: int = 200) -> list[MemoryEntry]:
        """Return only dormant (sub-threshold, awaiting pruning) memories."""
        factory = get_session_factory()
        async with factory() as session:
            stmt = select(MemoryRow).where(MemoryRow.is_dormant.is_(True)).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
        return [_row_to_entry(r) for r in rows]

    async def get_recent(self, n: int = 1) -> list[MemoryEntry]:
        """Return the *n* most recently stored active memories (newest first).

        Used by the pipeline to establish temporal causal links between memories.
        """
        factory = get_session_factory()
        async with factory() as session:
            stmt = (
                select(MemoryRow)
                .where(MemoryRow.is_dormant.is_(False))
                .order_by(MemoryRow.created_at.desc())
                .limit(n)
            )
            rows = (await session.execute(stmt)).scalars().all()
        return [_row_to_entry(r) for r in rows]

    async def add_causal_link(self, from_id: str, to_id: str) -> None:
        """Record that the memory *from_id* follows / was caused by *to_id*.

        A unidirectional temporal edge is added to `from_id.linked_ids`
        (JSON array). Duplicate links are silently ignored.
        """
        import json  # noqa: PLC0415

        factory = get_session_factory()
        async with factory() as session:
            row = await session.get(MemoryRow, from_id)
            if row is None:
                return
            current_links: list[str] = json.loads(row.linked_ids or "[]")
            if to_id not in current_links:
                current_links.append(to_id)
                row.linked_ids = json.dumps(current_links)
                await session.commit()

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

    async def mark_dormant(self, threshold: float = 0.01) -> int:
        """Mark sub-threshold memories as dormant (not deleted, not searchable).

        Called by the light consolidation cycle.  Returns the number newly
        marked dormant.
        """
        factory = get_session_factory()
        async with factory() as session:
            rows = (await session.execute(select(MemoryRow))).scalars().all()
            marked = 0
            for row in rows:
                if row.current_strength < threshold and not row.is_dormant:
                    row.is_dormant = True
                    marked += 1
                elif row.current_strength >= threshold and row.is_dormant:
                    # Reactivate if strength was bumped (e.g., accessed again)
                    row.is_dormant = False
            await session.commit()
        if marked:
            logger.info("Marked %d memories as dormant (strength < %.3f)", marked, threshold)
        return marked

    async def mark_dormant_by_ids(self, ids: list[str]) -> int:
        """Mark specific memories dormant by ID (used by dedup/synaptic pruning).

        Returns the number of memories successfully marked.
        """
        if not ids:
            return 0
        factory = get_session_factory()
        async with factory() as session:
            rows = (await session.execute(select(MemoryRow).where(MemoryRow.id.in_(ids)))).scalars().all()
            for row in rows:
                row.is_dormant = True
            await session.commit()
        return len(rows)

    async def delete_by_ids(self, ids: list[str]) -> int:
        """Permanently delete specific memories by ID (deep dedup pruning).

        Removes from both SQLite and ChromaDB. Returns count deleted.
        """
        if not ids:
            return 0
        factory = get_session_factory()
        async with factory() as session:
            rows = (await session.execute(select(MemoryRow).where(MemoryRow.id.in_(ids)))).scalars().all()
            chroma_ids = [r.embedding_id for r in rows if r.embedding_id]
            for row in rows:
                await session.delete(row)
            await session.commit()
        if chroma_ids:
            try:
                self._collection.delete(ids=chroma_ids)
            except Exception as exc:  # noqa: BLE001
                logger.warning("ChromaDB batch delete failed: %s", exc)
        return len(rows)

    async def prune_weak(self, threshold: float = 0.01) -> int:
        """Delete memories below strength threshold (both dormant and active). Returns count deleted."""
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

    async def re_embed_missing(self, limit: int = 50) -> int:
        """Embed memories that have no vector yet (embedding failed at store time).

        Uses the current embedding backend (LM Studio → HF fallback).
        Returns count of memories successfully re-embedded.
        """
        factory = get_session_factory()
        async with factory() as session:
            stmt = select(MemoryRow).where(MemoryRow.has_vector.is_(False)).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()

        if not rows:
            return 0

        succeeded = 0
        for row in rows:
            try:
                from echo.memory.chunker import chunk_ids, chunk_text
                chunks = chunk_text(row.content)
                vectors = await llm.embed(chunks)
                if not vectors or len(vectors) != len(chunks):
                    continue
                ids_c = chunk_ids(row.id, len(chunks))
                self._collection.upsert(
                    ids=ids_c,
                    embeddings=vectors,
                    documents=chunks,
                    metadatas=[
                        {"memory_id": row.id, "chunk_index": i, "salience": row.salience}
                        for i in range(len(chunks))
                    ],
                )
                async with factory() as session2:
                    stmt_u = select(MemoryRow).where(MemoryRow.id == row.id)
                    r = (await session2.execute(stmt_u)).scalar_one_or_none()
                    if r:
                        r.has_vector = True
                        r.embedding_id = ids_c[0]
                        await session2.commit()
                succeeded += 1
            except Exception as exc:  # noqa: BLE001
                logger.debug("re_embed_missing: skipping %s — %s", row.id[:8], exc)

        if succeeded:
            logger.info("Re-embedded %d/%d memories", succeeded, len(rows))
        return succeeded

    def count(self) -> int:
        """Best-effort sync count (uses ChromaDB; prefer acount() in async context)."""
        return self._collection.count()

    def _sqlite_count_sync(self) -> int:
        """Synchronous SQLite count via a new event loop."""
        import asyncio
        from sqlalchemy import func

        async def _count() -> int:
            factory = get_session_factory()
            async with factory() as session:
                result = await session.execute(select(func.count()).select_from(MemoryRow))
                return result.scalar_one()

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_count())
        finally:
            loop.close()

    async def acount(self) -> int:
        """Async count from SQLite — use this in async routes."""
        from sqlalchemy import func
        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(select(func.count()).select_from(MemoryRow))
            return result.scalar_one()
