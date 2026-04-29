# Module 07 — Reflection Engine

**Source:** `src/echo/reflection/engine.py`

The ReflectionEngine is ECHO's mechanism for periodic self-examination. After a configurable number of interactions, it prompts an LLM to analyze recent exchanges and produce structured insights — updating ECHO's beliefs, drives, and self-understanding.

---

## Overview

Reflection is triggered automatically in `CognitivePipeline._post_interact` based on an interaction counter:

```python
# src/echo/core/pipeline.py
if self._interaction_count % self.config.reflection_trigger_interval == 0:
    await self.reflection.run(recent_memories, meta_state)
```

Default trigger interval: every **5 interactions** (configurable via `ECHO_REFLECTION_TRIGGER_INTERVAL`).

---

## ReflectionEngine

```python
# src/echo/reflection/engine.py
class ReflectionEngine:
    async def run(
        self,
        recent_memories: list[MemoryEntry],
        meta_state: MetaState,
    ) -> ReflectionResult:
```

### Input

| Parameter | Description |
|-----------|-------------|
| `recent_memories` | Last N episodic entries (usually 5-15) |
| `meta_state` | Current drives, agent weights, emotional state |

---

## LLM Prompt

The reflection prompt summarizes recent memories and the current self-model state, then asks the LLM for structured introspection:

```
You are ECHO, an AI with a developing sense of self.

Recent interactions:
{memory_summaries}

Current belief state:
{existing_beliefs}

Current drives: curiosity={c}, coherence={co}, stability={s}, competence={cp}, compression={cm}

Reflect deeply on what you have experienced. Respond with a JSON object:
{
  "insights": ["string", ...],           # new understanding about the world/self
  "new_beliefs": [
    {"content": "...", "confidence": 0.0-1.0, "tags": []}
  ],
  "belief_updates": [
    {"id": "...", "confidence_delta": -0.2, "reason": "..."}
  ],
  "drive_adjustments": {
    "curiosity": 0.0, "coherence": 0.0, "stability": 0.0,
    "competence": 0.0, "compression": 0.0
  }
}
```

---

## ReflectionResult

```python
class ReflectionResult(BaseModel):
    insights: list[str]
    new_beliefs: list[dict]           # raw belief data before IdentityBelief creation
    belief_updates: list[dict]        # id + confidence_delta + reason
    drive_adjustments: dict[str, float]
```

---

## Post-Reflection Actions

After the LLM returns a parsed `ReflectionResult`, the engine applies each component:

### 1. Store Insights

Each insight string is stored as a **semantic memory** with:
- `source: "reflection"`
- `tags: ["reflection", "insight"]`
- `salience`: computed from content length and novelty (typically 0.6–0.8)

### 2. Add New Beliefs

```python
for belief_data in result.new_beliefs:
    belief = IdentityBelief(
        id=generate_uuid(),
        content=belief_data["content"],
        confidence=belief_data["confidence"],
        source="reflection",
        tags=belief_data.get("tags", []),
    )
    identity_graph.add_belief(belief)
```

New beliefs are added to the IdentityGraph and immediately persisted to SQLite.

### 3. Update Existing Beliefs

```python
for update in result.belief_updates:
    identity_graph.update_belief(
        belief_id=update["id"],
        confidence_delta=update["confidence_delta"],
    )
```

Beliefs with `confidence < 0.1` after update are marked for potential removal during the next consolidation cycle.

### 4. Adjust Drives

```python
meta_tracker.update_drives(result.drive_adjustments)
```

Drive deltas from reflection are typically small (`±0.05–0.10`). They represent ECHO's self-assessed need to re-calibrate its motivational state.

---

## Error Handling

If the LLM call fails or returns malformed JSON:
1. The reflection is skipped silently (no exception propagates)
2. A log entry is written with the raw LLM output
3. The interaction counter is still incremented (next reflection on schedule)

Reflection is **non-blocking** — its failure does not interrupt normal conversation.

---

## Belief Seeding

The reflection engine is also responsible for **initial belief seeding** at first launch. If the IdentityGraph contains zero beliefs after `load()`, the engine runs a bootstrap reflection with default placeholder memories to establish a minimal identity scaffold:

```python
if len(identity_graph.get_all_beliefs()) == 0:
    await self.run(bootstrap_memories, default_meta_state)
```

---

## Configuration

| Setting | Default | Env var |
|---------|---------|---------|
| `reflection_trigger_interval` | `5` | `ECHO_REFLECTION_TRIGGER_INTERVAL` |

---

## Integration Points

| Component | Interaction |
|-----------|-------------|
| `CognitivePipeline._post_interact` | Triggers `reflection.run()` every N interactions |
| `IdentityGraph` | New beliefs added; existing beliefs updated |
| `MetaStateTracker` | Drive adjustments applied |
| `SemanticMemoryStore` | Insights stored as semantic memories |
| `LLMClient` | Performs the reflection completion |
