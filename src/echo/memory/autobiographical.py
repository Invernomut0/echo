"""Autobiographical memory — long-running narrative self-representation."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Float, String, Text, select

from echo.core.db import Base, get_or_create_collection, get_session_factory
from echo.core.llm_client import llm
from echo.core.types import MemoryEntry, MemoryType

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
        vector = await llm.embed_one(content)

        if vector:
            self._collection.upsert(
                ids=[entry_id],
                embeddings=[vector],
                documents=[content],
                metadatas=[{"chapter": chapter, "salience": salience}],
            )

        factory = get_session_factory()
        async with factory() as session:
            row = AutobioRow(
                id=entry_id,
                content=content,
                narrative_chapter=chapter,
                salience=salience,
                embedding_id=entry_id,
            )
            session.add(row)
            await session.commit()

        return MemoryEntry(
            id=entry_id,
            content=content,
            memory_type=MemoryType.AUTOBIOGRAPHICAL,
            salience=salience,
            self_relevance=1.0,
            embedding_id=entry_id,
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
        if self._collection.count() == 0:
            return []
        vector = await llm.embed_one(query)
        if not vector:
            return []
        results = self._collection.query(
            query_embeddings=[vector],
            n_results=min(n_results, self._collection.count()),
            include=["documents", "metadatas"],
        )
        return [
            MemoryEntry(
                content=doc,
                memory_type=MemoryType.AUTOBIOGRAPHICAL,
                salience=meta.get("salience", 0.8),
                self_relevance=1.0,
            )
            for doc, meta in zip(
                results.get("documents", [[]])[0],
                results.get("metadatas", [[]])[0],
            )
        ]
