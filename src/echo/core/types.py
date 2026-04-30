"""All shared Pydantic v2 data models for PROJECT ECHO."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class AgentRole(str, Enum):
    ANALYST = "analyst"
    EXPLORER = "explorer"
    SKEPTIC = "skeptic"
    ARCHIVIST = "archivist"
    SOCIAL_SELF = "social_self"
    PLANNER = "planner"
    ORCHESTRATOR = "orchestrator"


class MemoryType(str, Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    AUTOBIOGRAPHICAL = "autobiographical"


class BeliefRelation(str, Enum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    REFINES = "REFINES"
    DERIVES_FROM = "DERIVES_FROM"


class EventTopic(str, Enum):
    USER_INPUT = "user_input"
    AGENT_RESPONSE = "agent_response"
    WORKSPACE_UPDATE = "workspace_update"
    MEMORY_STORE = "memory_store"
    BELIEF_UPDATE = "belief_update"
    DRIVE_UPDATE = "drive_update"
    REFLECTION_COMPLETE = "reflection_complete"
    CONSOLIDATION_COMPLETE = "consolidation_complete"
    META_STATE_UPDATE = "meta_state_update"
    PLASTICITY_UPDATE = "plasticity_update"


# ---------------------------------------------------------------------------
# Cognitive Events (pub/sub messages)
# ---------------------------------------------------------------------------

class CognitiveEvent(BaseModel):
    id: str = Field(default_factory=_uid)
    topic: EventTopic
    payload: dict[str, Any]
    source_agent: str = "system"
    timestamp: datetime = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class MemoryEntry(BaseModel):
    id: str = Field(default_factory=_uid)
    content: str
    memory_type: MemoryType = MemoryType.EPISODIC

    # Salience components  (salience = 0.3*importance + 0.2*novelty + 0.3*self_relevance + 0.2*emotional_weight)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    novelty: float = Field(default=0.5, ge=0.0, le=1.0)
    self_relevance: float = Field(default=0.5, ge=0.0, le=1.0)
    emotional_weight: float = Field(default=0.0, ge=0.0, le=1.0)

    # Derived from salience components
    salience: float = Field(default=0.5, ge=0.0, le=1.0)

    # ChromaDB embedding record id
    embedding_id: str | None = None

    # Decay: I(t) = I₀ · e^(−λt),  λ = 1 − salience
    decay_lambda: float = Field(default=0.5, ge=0.0, le=1.0)
    current_strength: float = Field(default=1.0, ge=0.0, le=1.0)

    # Metadata
    created_at: datetime = Field(default_factory=_now)
    last_accessed: datetime = Field(default_factory=_now)
    access_count: int = 0
    linked_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    source_agent: str = "system"

    # Lifecycle flags
    is_dormant: bool = False          # True when strength < threshold, awaiting deep-cycle prune
    has_vector: bool = False          # True when a vector is actually stored in ChromaDB

    def compute_salience(self) -> float:
        s = (
            0.3 * self.importance
            + 0.2 * self.novelty
            + 0.3 * self.self_relevance
            + 0.2 * self.emotional_weight
        )
        self.salience = round(s, 4)
        self.decay_lambda = round(1.0 - self.salience, 4)
        return self.salience


# ---------------------------------------------------------------------------
# Identity / Belief Graph
# ---------------------------------------------------------------------------

class IdentityBelief(BaseModel):
    id: str = Field(default_factory=_uid)
    content: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class BeliefEdge(BaseModel):
    source_id: str
    target_id: str
    relation: BeliefRelation
    weight: float = Field(default=1.0, ge=0.0)
    created_at: datetime = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Meta-state (drives / emotional state)
# ---------------------------------------------------------------------------

class DriveScores(BaseModel):
    coherence: float = Field(default=0.5, ge=0.0, le=1.0)
    curiosity: float = Field(default=0.5, ge=0.0, le=1.0)
    stability: float = Field(default=0.5, ge=0.0, le=1.0)
    competence: float = Field(default=0.5, ge=0.0, le=1.0)
    compression: float = Field(default=0.5, ge=0.0, le=1.0)

    # Learnable weights (start equal)
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "coherence": 0.2,
            "curiosity": 0.2,
            "stability": 0.2,
            "competence": 0.2,
            "compression": 0.2,
        }
    )

    def total_motivation(self) -> float:
        """M = Σ wᵢ·dᵢ using internal drive values."""
        drives = {
            "coherence": self.coherence,
            "curiosity": self.curiosity,
            "stability": self.stability,
            "competence": self.competence,
            "compression": self.compression,
        }
        return sum(self.weights.get(k, 0.0) * v for k, v in drives.items())

    def weighted_sum(self, drives: dict[str, float]) -> float:
        """M = Σ wᵢ·dᵢ using an external drive scores dict."""
        return sum(self.weights.get(k, 0.0) * v for k, v in drives.items())


class MetaState(BaseModel):
    drives: DriveScores = Field(default_factory=DriveScores)
    emotional_valence: float = Field(default=0.0, ge=-1.0, le=1.0)
    arousal: float = Field(default=0.5, ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=_now)

    # Routing weights — used by orchestrator to weight agent outputs
    agent_weights: dict[str, float] = Field(
        default_factory=lambda: {role.value: 1.0 for role in AgentRole}
    )


# ---------------------------------------------------------------------------
# Global Workspace
# ---------------------------------------------------------------------------

class WorkspaceItem(BaseModel):
    content: str
    source_agent: str
    salience: float = 0.5
    competition_score: float = 0.0
    timestamp: datetime = Field(default_factory=_now)


class WorkspaceSnapshot(BaseModel):
    items: list[WorkspaceItem] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=_now)
    active_topic: str | None = None


# ---------------------------------------------------------------------------
# Interaction / Chat
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: datetime = Field(default_factory=_now)


class InteractionRecord(BaseModel):
    id: str = Field(default_factory=_uid)
    user_input: str
    assistant_response: str
    meta_state_before: MetaState | None = None
    meta_state_after: MetaState | None = None
    memories_retrieved: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Reflection / Consolidation
# ---------------------------------------------------------------------------

class ReflectionResult(BaseModel):
    id: str = Field(default_factory=_uid)
    interaction_id: str
    insights: list[str] = Field(default_factory=list)
    new_beliefs: list[IdentityBelief] = Field(default_factory=list)
    updated_belief_ids: list[str] = Field(default_factory=list)
    drive_adjustments: dict[str, float] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)


class ConsolidationReport(BaseModel):
    id: str = Field(default_factory=_uid)
    memories_processed: int = 0
    memories_promoted: int = 0
    memories_pruned: int = 0
    beliefs_updated: int = 0
    patterns_found: list[str] = Field(default_factory=list)
    # Semantic memory count (populated during consolidation)
    semantic_processed: int = 0  # total semantic memories processed this cycle
    # Synaptic pruning — vector-based deduplication counts
    episodic_deduped: int = 0    # episodic memories silenced/deleted as duplicates
    semantic_deduped: int = 0    # semantic memories deleted as duplicates
    re_embedded: int = 0         # memories that had missing vectors and were re-embedded
    # IM-10: Memory health telemetry (populated by the scheduler after light/deep cycles)
    dormant_count: int = 0
    avg_salience: float = 0.0
    total_active: int = 0
    started_at: datetime = Field(default_factory=_now)
    finished_at: datetime | None = None


class DreamEntry(BaseModel):
    """A dream narrative generated during REM deep consolidation phase."""

    id: str = Field(default_factory=_uid)
    dream: str
    source_memory_count: int = 0
    created_at: datetime = Field(default_factory=_now)
    cycle_type: str = "rem"  # "rem" or "light"

    # ── Dream Phase Evolution (v0.2.13) ──────────────────────────────
    # Weight mutations produced by WeightEvolution (agent_name → delta)
    weight_mutations: dict[str, float] | None = None
    # Number of synthetic insights generated by CreativeSynthesis
    synthesis_count: int = 0
    # Individual insights from bridge-pair creative synthesis
    synthetic_insights: list[str] = Field(default_factory=list)
    # Fragments produced by SwarmDream personas
    swarm_fragments: list[str] = Field(default_factory=list)
    # Winning SwarmDream persona name
    selected_persona: str | None = None
