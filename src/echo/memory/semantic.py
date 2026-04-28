"""Semantic memory — facts and general knowledge nodes (ChromaDB + SQLite)."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Float, Integer, String, Text, select

from echo.core.db import Base, get_or_create_collection, get_session_factory
from echo.core.llm_client import llm
from echo.core.types import MemoryEntry, MemoryType

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "semantic_memory"


class SemanticRow(Base):
    __tablename__ = "semantic_memories"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    content = Column(Text, nullable=False)
    salience = Column(Float, default=0.5)
    current_strength = Column(Float, default=1.0)
    decay_lambda = Column(Float, default=0.3)
    embedding_id = Column(String, nullable=True)
    tags = Column(Text, default="[]")
    created_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    access_count = Column(Integer, default=0)
    source_agent = Column(String, default="system")


class SemanticMemoryStore:
    """Store general factual knowledge."""

    def __init__(self) -> None:
        self._collection = get_or_create_collection(_COLLECTION_NAME)

    async def store(self, content: str, tags: list[str] | None = None, salience: float = 0.7) -> MemoryEntry:
        entry_id = str(uuid.uuid4())
        vector = await llm.embed_one(content)

        decay_lambda = round(1.0 - salience, 4)
        self._collection.upsert(
            ids=[entry_id],
            embeddings=[vector],
            documents=[content],
            metadatas=[{"salience": salience}],
        )

        factory = get_session_factory()
        async with factory() as session:
            row = SemanticRow(
                id=entry_id,
                content=content,
                salience=salience,
                decay_lambda=decay_lambda,
                embedding_id=entry_id,
                tags=json.dumps(tags or []),
            )
            session.add(row)
            await session.commit()

        return MemoryEntry(
            id=entry_id,
            content=content,
            memory_type=MemoryType.SEMANTIC,
            salience=salience,
            decay_lambda=decay_lambda,
            tags=tags or [],
            embedding_id=entry_id,
        )

    async def retrieve_similar(self, query: str, n_results: int = 5) -> list[MemoryEntry]:
        if self._collection.count() == 0:
            return []
        vector = await llm.embed_one(query)
        results = self._collection.query(
            query_embeddings=[vector],
            n_results=min(n_results, self._collection.count()),
            include=["documents", "metadatas"],
        )
        entries: list[MemoryEntry] = []
        for doc, meta in zip(
            results.get("documents", [[]])[0],
            results.get("metadatas", [[]])[0],
        ):
            entries.append(
                MemoryEntry(
                    content=doc,
                    memory_type=MemoryType.SEMANTIC,
                    salience=meta.get("salience", 0.5),
                )
            )
        return entries

    def count(self) -> int:
        return self._collection.count()
