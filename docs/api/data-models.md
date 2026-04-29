# Data Models

All data models are Pydantic v2 classes defined in `src/echo/core/types.py`.

---

## Enumerations

### `MemoryType`

```python
class MemoryType(str, Enum):
    episodic        = "episodic"        # conversation events
    semantic        = "semantic"        # knowledge, facts, discoveries
    autobiographical = "autobiographical" # compressed life summary
```

### `AgentRole`

```python
class AgentRole(str, Enum):
    analyst      = "analyst"
    explorer     = "explorer"
    skeptic      = "skeptic"
    archivist    = "archivist"
    social_self  = "social_self"
    planner      = "planner"
    orchestrator = "orchestrator"  # internal; not a cognitive agent
```

### `BeliefRelation`

```python
class BeliefRelation(str, Enum):
    SUPPORTS       = "SUPPORTS"
    CONTRADICTS    = "CONTRADICTS"
    REFINES        = "REFINES"
    DERIVES_FROM   = "DERIVES_FROM"
```

### `EventTopic`

```python
class EventTopic(str, Enum):
    MEMORY_STORED        = "memory.stored"
    MEMORY_DORMANT       = "memory.dormant"
    WORKSPACE_BROADCAST  = "workspace.broadcast"
    REFLECTION_TRIGGERED = "reflection.triggered"
    REFLECTION_COMPLETE  = "reflection.complete"
    CONSOLIDATION_STARTED = "consolidation.started"
    DREAM_GENERATED      = "dream.generated"
    CURIOSITY_DISCOVERED = "curiosity.discovered"
    AGENT_WEIGHT_UPDATED = "agent.weight_updated"
    DRIVE_UPDATED        = "drive.updated"
```

---

## Core Models

### `MemoryEntry`

```python
class MemoryEntry(BaseModel):
    id: str                              # UUID
    content: str                         # text content
    source: str                          # "user", "echo", "curiosity", "reflection", ...
    memory_type: MemoryType
    tags: list[str] = []
    salience: float = 0.5               # [0.0, 1.0]
    importance: float = 0.5             # [0.0, 1.0]
    novelty: float = 0.5                # [0.0, 1.0]
    self_relevance: float = 0.5         # [0.0, 1.0]
    emotional_weight: float = 0.0       # [0.0, 1.0]
    timestamp: datetime
    is_dormant: bool = False
    has_vector: bool = False
    parent_id: str | None = None        # for chunk hierarchy
```

**Salience formula:**
```
salience = 0.3×importance + 0.2×novelty + 0.3×self_relevance + 0.2×emotional_weight
```

**Decay formula:**
```
I(t) = I₀ × e^(−λ × Δt)    where λ = 1 − salience
```

---

### `IdentityBelief`

```python
class IdentityBelief(BaseModel):
    id: str                    # UUID
    content: str               # "I value intellectual honesty"
    confidence: float          # [0.0, 1.0]
    source: str                # "reflection", "user", "bootstrap"
    tags: list[str] = []
    created_at: datetime
    updated_at: datetime
```

---

### `BeliefEdge`

```python
class BeliefEdge(BaseModel):
    source_id: str             # IdentityBelief.id
    target_id: str             # IdentityBelief.id
    relation: BeliefRelation
    weight: float = 1.0        # edge strength [0.0, 1.0]
    created_at: datetime
```

---

### `DriveScores`

```python
class DriveScores(BaseModel):
    coherence:   float = 0.5   # desire for consistent, non-contradictory understanding
    curiosity:   float = 0.5   # drive to explore and learn
    stability:   float = 0.5   # preference for familiar patterns
    competence:  float = 0.5   # drive to perform well and improve
    compression: float = 0.5   # desire for concise, efficient understanding
```

All values are in `[0.0, 1.0]`.

---

### `EmotionalState`

```python
class EmotionalState(BaseModel):
    valence: float   # [-1.0, 1.0] — negative to positive
    arousal: float   # [0.0, 1.0]  — calm to excited
    label: str       # "calm", "curious", "anxious", "enthusiastic", ...
```

**Derivation from drives:**
```
valence = (coherence + curiosity - stability) × 0.5
arousal = (curiosity + competence) × 0.5
```

**Label assignment:**
| Condition | Label |
|-----------|-------|
| `valence > 0.3 and arousal > 0.5` | `enthusiastic` |
| `valence > 0.3 and arousal ≤ 0.5` | `calm` |
| `valence ≤ -0.3 and arousal > 0.5` | `anxious` |
| `valence ≤ -0.3 and arousal ≤ 0.5` | `melancholy` |
| `curiosity > 0.7` | `curious` |
| `stability > 0.7` | `stable` |
| else | `neutral` |

---

### `MetaState`

```python
class MetaState(BaseModel):
    id: str
    timestamp: datetime
    drives: DriveScores
    agent_weights: dict[str, float]   # AgentRole.value → weight [0.1, 2.0]
    emotional_state: EmotionalState
    interaction_count: int
```

Persisted to SQLite `meta_states` table (append-only).

---

### `WorkspaceItem`

```python
class WorkspaceItem(BaseModel):
    id: str
    content: str
    source: str          # "memory", "prior", "tool_result"
    salience: float      # competition score for broadcast
    routing_weight: float
    timestamp: datetime
    ttl_seconds: int = 1800   # 30 minutes default
```

---

### `CognitiveEvent`

```python
class CognitiveEvent(BaseModel):
    id: str
    topic: EventTopic
    data: dict           # topic-specific payload
    timestamp: datetime
```

Broadcast to all WebSocket clients connected to `WS /ws/events`.

---

### `InteractionRecord`

```python
class InteractionRecord(BaseModel):
    id: str
    user_input: str
    response: str
    agent_perspectives: dict[str, str]   # AgentRole.value → agent response
    memory_sources: list[str]
    semantic_similarity_to_history: float
    response_word_count: int
    timestamp: datetime
```

---

### `PredictionPriors`

```python
class PredictionPriors(BaseModel):
    predicted_response_length: int
    predicted_formality_level: float    # [0, 1]
    predicted_topic_domain: str
    items: list[WorkspacePriorItem]
```

```python
class WorkspacePriorItem(BaseModel):
    content: str       # natural-language hint for workspace
    salience: float
```

---

## API Response Types

### `ChatResponse`

```json
{
  "response": "string",
  "meta_state": MetaState,
  "memory_sources": ["episodic", "semantic"],
  "timestamp": "ISO 8601"
}
```

### `StateResponse`

```json
{
  "meta_state": MetaState,
  "memory_counts": {
    "episodic": 142,
    "semantic": 38,
    "autobiographical": 7
  },
  "workspace_active_items": 3,
  "identity_beliefs_count": 24,
  "uptime_seconds": 3600
}
```

### `HealthResponse`

```json
{
  "status": "ok",
  "version": "0.4.0",
  "pipeline_ready": true,
  "memory_backend": "chromadb",
  "llm_provider": "lmstudio"
}
```

### `VectorStoreStatus`

```json
{
  "backend": "chromadb",
  "embedding_dim": 768,
  "total_vectors": 180,
  "active_vectors": 155,
  "dormant_vectors": 25,
  "avg_chunks_per_memory": 2.3,
  "collections": {"episodic": 120, "semantic": 38, "autobiographical": 22}
}
```
