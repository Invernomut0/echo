# Module 06 — Global Workspace

**Source:** `src/echo/workspace/global_workspace.py`

The Global Workspace (GWT — Global Workspace Theory) is ECHO's short-term working memory and attention mechanism. It determines which information is made available to the agents during response generation.

---

## Theory Background

Bernard Baars' Global Workspace Theory models consciousness as a "blackboard" that competing cognitive modules broadcast information onto. Only the most salient content is globally available; the rest stays in specialized, local processing.

ECHO implements a simplified version: the workspace holds up to 7 items (slots). When all slots are full, new items compete for admission. The lowest-scoring item is evicted.

---

## GlobalWorkspace

```python
# src/echo/workspace/global_workspace.py
class GlobalWorkspace:
    MAX_SLOTS: int = 7   # configurable via max_workspace_slots
```

### WorkspaceItem

```python
class WorkspaceItem(BaseModel):
    content: str
    source: str             # which module or agent added this
    salience: float         # broadcast score (0–1)
    routing_weight: float   # agent routing weight at time of broadcast
    timestamp: datetime
```

---

## Core Operations

### `broadcast(content, source, salience, routing_weight=1.0)`

Adds an item to the workspace. The effective broadcast score is:

```python
broadcast_score = salience * (1 + routing_weight * 0.2)
```

If the workspace is full (≥ 7 items), the item with the lowest broadcast score is evicted before the new item is added.

### `load_memories(memories, agent_role)`

Pushes memory entries into the workspace as background context. Memory salience is discounted to avoid memories dominating fresh inputs:

```python
memory_salience = memory.salience * 0.7
```

The routing weight used is `meta_state.agent_weights.get(agent_role, 1.0)`.

### `clear()`

Removes all items from the workspace. Called at the beginning of each interaction.

### `get_items()` → `list[WorkspaceItem]`

Returns current workspace contents, sorted by broadcast score descending.

### `get_text()` → `str`

Returns a formatted string of workspace contents for inclusion in LLM prompts:

```
[Workspace Context]
[1] (salience=0.87, source=archivist) Last week we discussed neural networks and you mentioned...
[2] (salience=0.73, source=self_model) I believe I am most effective when analyzing structured problems.
[3] (salience=0.65, source=learning)  User prefers concise, technical explanations without hedging.
...
```

---

## Workspace Loading Sequence

At the start of each interaction, the workspace is populated in this order:

```python
# 1. Clear previous state
workspace.clear()

# 2. Load episodic + semantic memories (discounted salience × 0.7)
workspace.load_memories(episodic_memories, source="archivist")
workspace.load_memories(semantic_memories, source="archivist")

# 3. Broadcast self-prediction (moderate salience)
workspace.broadcast(self_prediction, source="self_model", salience=0.65)

# 4. Broadcast learning priors (personalization context)
for prior in learning.get_priors().items:
    workspace.broadcast(prior.content, source="learning", salience=prior.salience)

# 5. Broadcast personalization style hint (low salience)
style_hint = learning.personalization.style_hint()
if style_hint:
    workspace.broadcast(style_hint, source="personalization", salience=0.40)
```

After loading, the workspace contains the most salient mix of:
- Past experiences (episodic)
- Known facts (semantic)
- Self-prediction about the response
- User personalization notes
- Any other items agents may add dynamically

---

## Competition and Eviction

When more than 7 items compete for workspace access, the lowest-score item is evicted:

```
Items: [0.91, 0.87, 0.73, 0.65, 0.62, 0.59, 0.41]  ← 7 items, workspace full
New item arrives with score 0.55:
  → evicts 0.41, keeps the new item
Workspace: [0.91, 0.87, 0.73, 0.65, 0.62, 0.59, 0.55]
```

If the new item's score is lower than all existing items, it is not admitted:
```
New item arrives with score 0.38:
  → 0.38 < 0.41 → item rejected
Workspace unchanged
```

---

## Agent Access

During orchestration, each agent receives the full workspace content via `workspace.get_text()`. The content is injected into each agent's system prompt as background context.

The orchestrator's synthesis prompt also includes the workspace summary, giving the LLM the full picture of what information was considered.

---

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `max_workspace_slots` | `7` | Maximum concurrent workspace items |

Increasing this value allows more context but makes agent prompts longer and potentially noisier. The default of 7 is consistent with Miller's Law (7 ± 2 items in working memory).

---

## Integration Points

| Component | Interaction |
|-----------|-------------|
| `CognitivePipeline.stream_interact` | Clears and loads workspace before each turn |
| `Orchestrator` | Reads workspace via `get_text()`, passes to all agents |
| `LearningEngine` | Writes personalization priors to workspace |
| `EpisodicMemoryStore` | Source of memory items loaded into workspace |
| `SemanticMemoryStore` | Source of knowledge items loaded into workspace |
| `GET /api/state` | Reports `workspace_items` count |
