# Module 08 — Consolidation & Dream Phase

**Source:** `src/echo/consolidation/`

Consolidation is ECHO's background maintenance process. It runs asynchronously on a schedule while ECHO is idle or active, compressing and integrating memories — analogous to the way biological memory consolidation occurs during sleep.

---

## ConsolidationScheduler

```python
# src/echo/consolidation/scheduler.py
class ConsolidationScheduler:
    async def start(self):
```

The scheduler runs two independent async loops:

| Loop | Interval | What it does |
|------|----------|--------------|
| **Light heartbeat** | 300 s (5 min) | `SleepPhase` — lightweight memory compression |
| **Deep/REM heartbeat** | 43,200 s (12 h) | Full `ConsolidationPhase` + `DreamPhase` |

Both loops use `asyncio.sleep()` and run concurrently via the event loop. They stop cleanly when the pipeline shuts down.

---

## SleepPhase (Light)

Runs every 5 minutes. Lightweight operations only:

1. **Decay trigger** — calls `DecayScheduler.tick()` to reduce salience of dormant memories
2. **Duplicate detection** — scans recent episodic memories for near-duplicates (by vector similarity > 0.95) and marks one as dormant
3. **Workspace flush** — removes items from GlobalWorkspace older than 30 minutes with salience < 0.2

---

## ConsolidationPhase (Deep)

Runs every 12 hours. Heavier memory integration:

1. **Semantic compression** — clusters related semantic chunks and merges those above a similarity threshold
2. **Autobiographical update** — generates or updates the autobiographical summary from recent episodic entries
3. **Identity belief pruning** — removes beliefs with `confidence < 0.1`
4. **Statistics update** — recalculates memory store statistics cached for `GET /api/memory/vectors`

---

## DreamPhase

```python
# src/echo/consolidation/dream_phase.py
class DreamPhase:
    async def run(self) -> DreamResult:
```

The DreamPhase is the creative and integrative component of deep consolidation. It runs concurrently with `ConsolidationPhase` every 12 hours.

### Input: Top Salient Memories

```python
memories = await episodic.get_top_salient(limit=15)
```

The 15 most salient episodic memories are selected as "dream material."

**Fallback:** If fewer than 3 memories exist, a default placeholder dream narrative is generated without LLM invocation.

### Three Parallel Sub-Processes

The DreamPhase runs these three processes concurrently via `asyncio.gather()`:

#### 1. WeightEvolution

Analyzes memory salience distribution and adjusts agent weights using heuristic rules:

```python
# If curiosity-tagged memories dominate → slightly boost explorer
# If analytical patterns dominate → slightly boost analyst
```

Deltas are small (`±0.02`) and applied via `meta_tracker.update_agent_weight()`.

#### 2. CreativeSynthesis

Uses the LLM to generate new semantic memories by synthesizing patterns across the top memories:

```python
prompt = f"""
You are ECHO in deep processing mode.
Review these recent memories:
{memory_summaries}

Generate 2-3 new abstract insights or connections you notice.
Return JSON: {{"insights": ["...", ...]}}
"""
```

Generated insights are stored as semantic memories with tags `["dream", "synthesis"]`.

#### 3. SwarmDream

Simulates each cognitive agent independently "processing" the memories:

```python
for agent_role in [analyst, explorer, skeptic, archivist, planner]:
    agent_dream = await agent.dream(memories)
    # agent_dream → brief reflection from that agent's perspective
```

The 5 agent dreams are concatenated and passed to a final LLM call that synthesizes a unified "dream narrative" from the swarm:

```python
narrative = await llm.complete(
    f"Synthesize these cognitive agent dreams into ECHO's integrated dream:\n{agent_dreams}"
)
```

The final narrative is stored as a special episodic memory:
- `memory_type: "episodic"`
- `tags: ["dream", "consolidation", "narrative"]`
- `salience: 0.75` (high — dreams are important for identity)

### DreamResult

```python
class DreamResult(BaseModel):
    narrative: str
    new_semantic_memories: list[MemoryEntry]
    weight_deltas: dict[str, float]
    timestamp: datetime
```

### Fallback Behaviors

| Condition | Fallback |
|-----------|----------|
| LLM unavailable | Pre-defined dream template used |
| Fewer than 3 memories | Simple reflection dream with memory count |
| JSON parse failure | Narrative stored as plain text |

---

## Memory Decay (DecayScheduler)

```python
# src/echo/memory/decay.py
class DecayScheduler:
    async def tick(self):
```

Decays salience of memories that haven't been retrieved recently:

```python
I(t) = I₀ × e^(−λ × Δt)
λ = 1 − salience   # low-salience memories decay faster
```

A memory is marked `is_dormant = True` when its current salience drops below `0.05`. Dormant memories:
- Are excluded from retrieval by default
- Are excluded from dream processing
- Can be reactivated if directly referenced by the user

Decay runs automatically every `memory_decay_interval_seconds` (default: 300 s).

---

## Configuration

| Setting | Default | Env var |
|---------|---------|---------|
| `consolidation_interval_seconds` | `3600` | `ECHO_CONSOLIDATION_INTERVAL_SECONDS` |
| `memory_decay_interval_seconds` | `300` | `ECHO_MEMORY_DECAY_INTERVAL_SECONDS` |

Note: The `consolidation_interval_seconds` setting controls the light heartbeat. The deep heartbeat is hardcoded at 43,200 s (12 h).

---

## Integration Points

| Component | Interaction |
|-----------|-------------|
| `CognitivePipeline.startup` | Starts the ConsolidationScheduler |
| `EpisodicMemoryStore` | Source of memories for DreamPhase |
| `SemanticMemoryStore` | Receives dream synthesis insights |
| `IdentityGraph` | Pruned during deep consolidation |
| `MetaStateTracker` | Receives weight deltas from WeightEvolution |
| `DecayScheduler` | Manages memory salience decay |
