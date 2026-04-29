"""Autobiographical memory — long-running narrative self-representation."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Float, String, Text, select

from echo.core.db import Base, get_or_create_collection, get_session_factory
from echo.core.llm_client import llm
from echo.core.types import MemoryEntry, MemoryType
from echo.memory.chunker import chunk_ids, chunk_text, memory_id_from_chunk_id

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "autobiographical_memory"


class AutobioRow(Base):
    __tablename__ = "autobiographical_memories"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    content = Column(Text, nullable=False)
    narrative_chapter = Column(String, default="general")
    salience = Column(Float, default=0.8)
    created_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    embedding_id = Column(String, nullable=True)
    source_agent = Column(String, default="system")


class AutobiographicalMemoryStore:
    """Store key life-narrative events for the system's self-model."""

    def __init__(self) -> None:
        self._collection = get_or_create_collection(_COLLECTION_NAME)

    async def store(
        self,
        content: str,
        chapter: str = "general",
        salience: float = 0.8,
    ) -> MemoryEntry:
        entry_id = str(uuid.uuid4())

        # Chunk long texts so each segment gets its own embedding vector.
        chunks = chunk_text(content)
        vectors = await llm.embed(chunks)  # batch: one call regardless of chunk count

        ids_c = chunk_ids(entry_id, len(chunks))
        if vectors and len(vectors) == len(chunks):
            try:
                self._collection.upsert(
                    ids=ids_c,
                    embeddings=vectors,
                    documents=chunks,
                    metadatas=[
                        {"memory_id": entry_id, "chunk_index": i, "chapter": chapter, "salience": salience}
                        for i in range(len(chunks))
                    ],
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("ChromaDB upsert skipped for autobiographical %s: %s", entry_id[:8], exc)

        factory = get_session_factory()
        async with factory() as session:
            row = AutobioRow(
                id=entry_id,
                content=content,
                narrative_chapter=chapter,
                salience=salience,
                embedding_id=ids_c[0],
            )
            session.add(row)
            await session.commit()

        return MemoryEntry(
            id=entry_id,
            content=content,
            memory_type=MemoryType.AUTOBIOGRAPHICAL,
            salience=salience,
            self_relevance=1.0,
            embedding_id=ids_c[0],
        )

    async def get_narrative(self, chapter: str | None = None) -> list[MemoryEntry]:
        factory = get_session_factory()
        async with factory() as session:
            stmt = select(AutobioRow)
            if chapter:
                stmt = stmt.where(AutobioRow.narrative_chapter == chapter)
            rows = (await session.execute(stmt)).scalars().all()

        return [
            MemoryEntry(
                id=r.id,
                content=r.content,
                memory_type=MemoryType.AUTOBIOGRAPHICAL,
                salience=r.salience,
                self_relevance=1.0,
                created_at=datetime.fromisoformat(r.created_at),
                embedding_id=r.embedding_id,
            )
            for r in rows
        ]

    async def retrieve_similar(self, query: str, n_results: int = 3) -> list[MemoryEntry]:
        col_count = self._collection.count()
        if col_count == 0:
            return []
        vector = await llm.embed_one(query)
        if not vector:
            return []
        results = self._collection.query(
            query_embeddings=[vector],
            # Request n*3 raw chunk results so dedup still yields n unique memories
            n_results=min(n_results * 3, col_count),
            include=["documents", "metadatas", "distances"],
        )
        ids_r = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]

        # Deduplicate chunk results → keep the best-matching chunk per memory.
        best_chunk: dict[str, tuple[str, dict, float]] = {}  # mem_id → (doc, meta, dist)
        for cid, doc, meta, dist in zip(ids_r, docs, metas, dists):
            mem_id = meta.get("memory_id") or memory_id_from_chunk_id(cid)
            if mem_id not in best_chunk or dist < best_chunk[mem_id][2]:
                best_chunk[mem_id] = (doc, meta, dist)

        return [
            MemoryEntry(
                content=doc,
                memory_type=MemoryType.AUTOBIOGRAPHICAL,
                salience=meta.get("salience", 0.8),
                self_relevance=1.0,
            )
            for doc, meta, _dist in best_chunk.values()
        ][:n_results]
