"""Memory router — /api/memory."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from echo.api.schemas import MemoriesResponse, MemoryListItem
from echo.core.pipeline import pipeline
from echo.core.types import MemoryEntry
from echo.memory.episodic import EpisodicMemoryStore

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("", response_model=MemoriesResponse)
async def list_memories(limit: int = 50) -> MemoriesResponse:
    memories = await pipeline.episodic.get_all(limit=limit)
    items = [
        MemoryListItem(
            id=m.id,
            content=m.content[:300],
            memory_type=m.memory_type.value,
            salience=m.salience,
            current_strength=m.current_strength,
            created_at=m.created_at,
            tags=m.tags,
        )
        for m in memories
    ]
    return MemoriesResponse(total=pipeline.episodic.count(), items=items)


@router.get("/{memory_id}", response_model=MemoryListItem)
async def get_memory(memory_id: str) -> MemoryListItem:
    mem = await pipeline.episodic.get_by_id(memory_id)
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found")
    return MemoryListItem(
        id=mem.id,
        content=mem.content,
        memory_type=mem.memory_type.value,
        salience=mem.salience,
        current_strength=mem.current_strength,
        created_at=mem.created_at,
        tags=mem.tags,
    )


@router.get("/search/{query}", response_model=MemoriesResponse)
async def search_memories(query: str, n: int = 5) -> MemoriesResponse:
    memories = await pipeline.episodic.retrieve_similar(query, n_results=n)
    items = [
        MemoryListItem(
            id=m.id,
            content=m.content[:300],
            memory_type=m.memory_type.value,
            salience=m.salience,
            current_strength=m.current_strength,
            created_at=m.created_at,
            tags=m.tags,
        )
        for m in memories
    ]
    return MemoriesResponse(total=len(items), items=items)
