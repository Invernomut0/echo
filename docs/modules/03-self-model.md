# Module 03 — Self-Model

**Source:** `src/echo/self_model/`

ECHO's self-model is its internal representation of its own identity, values, and cognitive state. It comprises two cooperating components: the **IdentityGraph** (what ECHO believes about itself) and the **MetaStateTracker** (ECHO's current drives, agent weights, and emotional state).

---

## IdentityGraph

```python
# src/echo/self_model/identity_graph.py
class IdentityGraph:
```

**Backend:** NetworkX `DiGraph`, persisted to SQLite tables `identity_beliefs` + `belief_edges`

The IdentityGraph is ECHO's belief network about itself. Nodes are `IdentityBelief` objects; directed edges represent logical/evidential relationships between beliefs.

### IdentityBelief

```python
class IdentityBelief(BaseModel):
    id: str
    content: str                    # e.g. "I am curious about mathematics"
    confidence: float = 0.7         # [0, 1]
    evidence_count: int = 0         # number of supporting interactions
    created_at: datetime
    last_updated: datetime
    tags: list[str] = []
```

### BeliefEdge

```python
class BeliefEdge(BaseModel):
    source_id: str
    target_id: str
    relation: BeliefRelation        # SUPPORTS | CONTRADICTS | REFINES | DERIVES_FROM
    weight: float = 1.0
```

### BeliefRelation Enum

| Value | Meaning |
|-------|---------|
| `SUPPORTS` | Source provides evidence for target |
| `CONTRADICTS` | Source conflicts with target |
| `REFINES` | Source narrows or specifies target |
| `DERIVES_FROM` | Target was inferred from source |

### Key Methods

| Method | Description |
|--------|-------------|
| `load()` | Load all beliefs and edges from SQLite into the in-memory DiGraph |
| `save()` | Persist current graph state to SQLite |
| `add_belief(belief)` | Add node; persist immediately |
| `add_edge(source_id, target_id, relation, weight)` | Add directed edge |
| `update_belief(id, confidence_delta, content=None)` | Update confidence + evidence count |
| `get_all_beliefs()` | Return all `IdentityBelief` objects |
| `get_edges()` | Return all `BeliefEdge` objects |
| `coherence_score()` → `float` | Structural graph coherence (see below) |
| `get_contradictions()` | Return pairs of beliefs with `CONTRADICTS` edges |

### Coherence Score

The coherence score estimates how internally consistent ECHO's belief system is:

```python
def coherence_score(self) -> float:
    n_nodes = self.graph.number_of_nodes()
    if n_nodes == 0:
        return 1.0
    n_contradictions = sum(
        1 for u, v, d in self.graph.edges(data=True)
        if d.get("relation") == BeliefRelation.CONTRADICTS
    )
    contradiction_ratio = n_contradictions / max(n_nodes, 1)
    return max(0.0, 1.0 - contradiction_ratio * 2)
```

A score of 1.0 means no contradictions. A score of 0.0 means every node has a contradicting edge. The coherence score is included in `MetaState` and exposed via `GET /api/state`.

### Contradiction Resolution

When the reflection engine or user explicitly calls `POST /api/memory/resolve-conflict`, ECHO:
1. Evaluates evidence count and confidence of both conflicting beliefs
2. Weakens the less-supported belief's confidence
3. Optionally merges them into a `REFINES` relationship
4. Updates the graph in SQLite

---

## MetaStateTracker

```python
# src/echo/self_model/meta_state.py
class MetaStateTracker:
```

**SQLite table:** `meta_states` (append-only time series)

The MetaStateTracker maintains ECHO's current affective and motivational state, persisting it as a time series to allow trend analysis.

### MetaState

```python
class MetaState(BaseModel):
    id: str
    timestamp: datetime
    drives: DriveScores             # Five motivational drives
    emotional_valence: float        # [-1, 1] — positive/negative affect
    emotional_arousal: float        # [0, 1] — activation level
    agent_weights: dict[str, float] # agent_name → routing weight [0.1, 2.0]
    drive_weights: dict[str, float] # drive_name → influence scalar
    total_motivation: float         # sum of active drives
```

### DriveScores

```python
class DriveScores(BaseModel):
    coherence: float = 0.5      # desire for internal consistency
    curiosity: float = 0.5      # drive to explore and learn
    stability: float = 0.5      # desire for predictable environment
    competence: float = 0.5     # drive to perform well
    compression: float = 0.5    # drive to simplify and abstract
```

All drive values are clamped to `[0, 1]`.

### Key Methods

| Method | Description |
|--------|-------------|
| `load_latest()` | Load most recent MetaState snapshot from SQLite |
| `persist()` | Append current state as a new row to `meta_states` |
| `update_drives(adjustments: dict[str, float])` | Add deltas, clamp to [0,1] |
| `update_agent_weight(agent: str, delta: float)` | Add delta, clamp to [0.1, 2.0] |
| `get_history(limit=50)` → `list[MetaState]` | Time-series history for charts |
| `current` → `MetaState` | Current in-memory state |

### Drive Update (Hebbian-style)

```python
def update_drives(self, adjustments: dict[str, float]):
    for drive, delta in adjustments.items():
        current = getattr(self.current.drives, drive)
        new_val = max(0.0, min(1.0, current + delta))
        setattr(self.current.drives, drive, new_val)
    self.current.total_motivation = sum(
        getattr(self.current.drives, d) for d in DriveScores.__fields__
    )
```

### Agent Weight Update

```python
def update_agent_weight(self, agent: str, delta: float):
    current = self.current.agent_weights.get(agent, 1.0)
    self.current.agent_weights[agent] = max(0.1, min(2.0, current + delta))
```

Agent weights in `[0.1, 2.0]`:
- `1.0` = neutral (default)
- `2.0` = maximum influence (voice doubled)
- `0.1` = near-silent (almost excluded from synthesis)

---

## Emotional State

Emotional state is not directly controlled by ECHO — it emerges from the motivational drives and interaction patterns.

| Dimension | Range | Description |
|-----------|-------|-------------|
| `emotional_valence` | `[-1, 1]` | How positive or negative ECHO currently feels |
| `emotional_arousal` | `[0, 1]` | Level of activation (high = engaged/excited, low = calm) |

These values are updated by the motivational scorer after each interaction and used by the orchestrator to modulate response tone.

---

## State History

The `meta_states` table stores a time series of MetaState snapshots, one per interaction. This enables the frontend to render trend charts for:
- Drive evolution over time
- Emotional valence trajectory
- Per-agent weight drift
- Total motivation trajectory

Available via `GET /api/state/history?limit=N`.

---

## Integration Points

| Component | How it uses the Self-Model |
|-----------|---------------------------|
| `Orchestrator` | Reads `meta_state.agent_weights` to modulate agent voices |
| `CognitivePipeline._post_interact` | Updates drives and agent weights after scoring |
| `ReflectionEngine` | Reads and writes beliefs to IdentityGraph |
| `GlobalWorkspace` | Uses agent weights in broadcast scoring |
| `PlasticityAdapter` | Reads and writes agent weights |
| `ConsolidationScheduler` | Uses coherence score to prioritize belief consolidation |
| `API /api/state` | Exposes current MetaState and belief count |
