"""Memory router — /api/memory."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from echo.api.schemas import (
    MemoriesResponse,
    MemoryListItem,
    ResolveConflictRequest,
    ResolveConflictResponse,
    SemanticMemoriesResponse,
    VectorStoreStatus,
)
from echo.core.pipeline import pipeline
from echo.core.types import MemoryEntry
from echo.memory.episodic import EpisodicMemoryStore
from echo.memory.semantic import SemanticMemoryStore

router = APIRouter(prefix="/api/memory", tags=["memory"])


def _to_item(m: MemoryEntry, *, truncate: bool = True) -> MemoryListItem:
    return MemoryListItem(
        id=m.id,
        content=m.content[:300] if truncate else m.content,
        memory_type=m.memory_type.value,
        salience=m.salience,
        current_strength=m.current_strength,
        created_at=m.created_at,
        tags=m.tags,
        is_dormant=m.is_dormant,
        has_vector=m.has_vector,
    )


# ── Static sub-paths FIRST (before /{memory_id} wildcard) ──────────────────

@router.get("/vectors", response_model=VectorStoreStatus)
async def vector_store_status() -> VectorStoreStatus:
    """ChromaDB vs SQLite coverage for episodic and semantic memories."""
    ep = EpisodicMemoryStore()
    sem = SemanticMemoryStore()

    ep_sqlite = await ep.acount()
    ep_vector = ep.count()          # ChromaDB sync count
    sem_sqlite = await sem.acount()
    sem_vector = sem.count()

    def pct(vec: int, sql: int) -> float:
        return round(vec / sql * 100, 1) if sql else 0.0

    return VectorStoreStatus(
        episodic_sqlite_count=ep_sqlite,
        episodic_vector_count=ep_vector,
        semantic_sqlite_count=sem_sqlite,
        semantic_vector_count=sem_vector,
        episodic_coverage_pct=pct(ep_vector, ep_sqlite),
        semantic_coverage_pct=pct(sem_vector, sem_sqlite),
    )


@router.get("/semantic", response_model=SemanticMemoriesResponse)
async def list_semantic_memories(limit: int = 50) -> SemanticMemoriesResponse:
    sem = SemanticMemoryStore()
    memories = await sem.get_all(limit=limit)
    items = [_to_item(m) for m in memories]
    return SemanticMemoriesResponse(total=await sem.acount(), items=items)


@router.get("/search/{query}", response_model=MemoriesResponse)
async def search_memories(query: str, n: int = 5) -> MemoriesResponse:
    memories = await pipeline.episodic.retrieve_similar(query, n_results=n)
    items = [_to_item(m) for m in memories]
    return MemoriesResponse(total=len(items), items=items)


@router.post("/resolve", response_model=ResolveConflictResponse)
async def resolve_conflict(body: ResolveConflictRequest) -> ResolveConflictResponse:
    """Resolve a memory conflict surfaced during consolidation.

    Called when the user decides which of two contradicting semantic memories
    is correct.  Deletes the ``delete_id`` memory from both ChromaDB and
    SQLite and keeps the ``keep_id`` memory untouched.

    The conflict candidates are provided by the ``memory_conflicts`` field in
    ``CONSOLIDATION_COMPLETE`` events (see the consolidation scheduler).
    """
    sem = SemanticMemoryStore()
    deleted = await sem.delete(body.delete_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Memory {body.delete_id!r} not found or already deleted.",
        )
    return ResolveConflictResponse(
        deleted=True,
        delete_id=body.delete_id,
        keep_id=body.keep_id,
    )


# ── Generic paths (wildcard must come after static) ─────────────────────────

@router.get("", response_model=MemoriesResponse)
async def list_memories(limit: int = 50) -> MemoriesResponse:
    memories = await pipeline.episodic.get_all(limit=limit)
    items = [_to_item(m) for m in memories]
    return MemoriesResponse(total=await pipeline.episodic.acount(), items=items)


@router.get("/{memory_id}", response_model=MemoryListItem)
async def get_memory(memory_id: str) -> MemoryListItem:
    mem = await pipeline.episodic.get_by_id(memory_id)
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found")
    return _to_item(mem, truncate=False)
