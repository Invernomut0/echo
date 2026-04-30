"""API request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from echo.core.types import ConsolidationReport, InteractionRecord, MetaState


# ---------------------------------------------------------------------------
# Chat / Interact
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    history: list[dict[str, str]] = Field(default_factory=list)


class ChatResponse(BaseModel):
    interaction_id: str
    response: str
    meta_state: MetaState
    memories_used: int
    timestamp: datetime


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class StateResponse(BaseModel):
    meta_state: MetaState
    workspace_items: int
    identity_beliefs: int
    episodic_memories: int
    interaction_count: int


class HistoryPoint(BaseModel):
    timestamp: datetime
    drives: dict[str, float]
    emotional_valence: float
    arousal: float = 0.5
    agent_weights: dict[str, float] = Field(default_factory=dict)
    drive_weights: dict[str, float] = Field(default_factory=dict)
    total_motivation: float = 0.5


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class MemoryListItem(BaseModel):
    id: str
    content: str
    memory_type: str
    salience: float
    current_strength: float
    created_at: datetime
    tags: list[str]
    is_dormant: bool = False
    has_vector: bool = False


class MemoriesResponse(BaseModel):
    total: int
    items: list[MemoryListItem]


class SemanticMemoriesResponse(BaseModel):
    total: int
    items: list[MemoryListItem]


class VectorStoreStatus(BaseModel):
    episodic_sqlite_count: int
    episodic_vector_count: int
    semantic_sqlite_count: int
    semantic_vector_count: int
    episodic_coverage_pct: float
    semantic_coverage_pct: float


# ---------------------------------------------------------------------------
# Conflict resolution
# ---------------------------------------------------------------------------

class ResolveConflictRequest(BaseModel):
    """User decision for a memory conflict that couldn't be auto-resolved.

    The caller specifies which memory to *delete* (the incorrect one) and
    which to *keep* (the correct one).  Both IDs must belong to the same
    conflict pair surfaced by ``detect_and_clean_conflicts``.
    """

    delete_id: str = Field(..., description="ID of the memory to delete (the incorrect fact)")
    keep_id: str = Field(..., description="ID of the memory to keep (the correct fact)")


class ResolveConflictResponse(BaseModel):
    deleted: bool
    delete_id: str
    keep_id: str


# ---------------------------------------------------------------------------
# Identity Graph
# ---------------------------------------------------------------------------

class GraphResponse(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    coherence_score: float


# ---------------------------------------------------------------------------
# Consolidation
# ---------------------------------------------------------------------------

class ConsolidationTriggerResponse(BaseModel):
    status: str
    report: ConsolidationReport | None = None


# ---------------------------------------------------------------------------
# Chunks (ChromaDB chunk viewer)
# ---------------------------------------------------------------------------

class ChunkItem(BaseModel):
    chunk_id: str
    chunk_index: int
    text: str
    char_count: int
    embedding_dim: int
    embedding_preview: list[float]  # first N dimensions for UI preview


class MemoryWithChunks(BaseModel):
    memory_id: str
    content: str
    salience: float
    created_at: datetime
    tags: list[str]
    chunk_count: int
    chunks: list[ChunkItem]


class ChunksResponse(BaseModel):
    total_memories: int
    total_chunks: int
    memories: list[MemoryWithChunks]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    lm_studio_available: bool
    version: str = "0.1.0"


# ---------------------------------------------------------------------------
# Wiki
# ---------------------------------------------------------------------------

class WikiIngestRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    source_text: str = Field(..., min_length=1, max_length=50_000)
    source_type: str = Field(default="text", max_length=50)
    file_back_synthesis: bool = True


class WikiIngestResponse(BaseModel):
    title: str
    slug: str
    pages_written: list[str]
    entities: int
    concepts: int
    summary: str


class WikiQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    file_back: bool = True


class WikiQueryResponse(BaseModel):
    question: str
    answer: str
    pages_consulted: list[str]
    synthesis_page: str | None = None


class WikiPageItem(BaseModel):
    title: str
    path: str
    category: str
    tags: str
    summary: str


class WikiSearchResponse(BaseModel):
    query: str
    results: list[WikiPageItem]


class WikiLintResponse(BaseModel):
    total_pages: int
    checked_pages: int
    issues: list[dict[str, Any]]


class WikiGraphNode(BaseModel):
    id: str
    title: str
    category: str
    tags: list[str]
    summary: str
    path: str
    degree: int


class WikiGraphLink(BaseModel):
    source: str
    target: str
    label: str


class WikiGraphResponse(BaseModel):
    nodes: list[WikiGraphNode]
    links: list[WikiGraphLink]
    stats: dict[str, Any]
