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


class MemoriesResponse(BaseModel):
    total: int
    items: list[MemoryListItem]


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
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    lm_studio_available: bool
    version: str = "0.1.0"
