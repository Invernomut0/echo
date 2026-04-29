# Module 01 — Cognitive Core & Pipeline

**Source:** `src/echo/core/pipeline.py`, `src/echo/core/llm_client.py`, `src/echo/core/event_bus.py`

The `CognitivePipeline` is the top-level controller of ECHO. It is instantiated once at startup and lives for the lifetime of the process. It wires together all subsystems and drives the main interaction loop.

---

## CognitivePipeline

```python
# src/echo/core/pipeline.py
class CognitivePipeline:
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `episodic` | `EpisodicMemoryStore` | Episodic memory store |
| `semantic` | `SemanticMemoryStore` | Semantic memory store |
| `autobiographical` | `AutobiographicalStore` | Autobiographical summaries |
| `workspace` | `GlobalWorkspace` | 7-slot GWT workspace |
| `meta_tracker` | `MetaStateTracker` | Drives + agent weights tracker |
| `identity_graph` | `IdentityGraph` | Belief graph for identity |
| `orchestrator` | `Orchestrator` | Multi-agent runner |
| `reflection` | `ReflectionEngine` | Post-interaction introspection |
| `plasticity` | `PlasticityAdapter` | Routing weight fine-tuning |
| `consolidation` | `ConsolidationScheduler` | Background consolidation loop |
| `decay` | `DecayScheduler` | Background memory decay loop |
| `learning` | `LearningEngine` | Personalization + predictor (module 16) |
| `_interaction_count` | `int` | Total interactions since startup |
| `_last_pipeline_trace` | `dict` | Trace of last interaction for UI |

---

## Lifecycle

```python
# Called once on startup (FastAPI lifespan)
await pipeline.startup()

# Called once on shutdown
await pipeline.shutdown()
```

`startup()` performs:
1. `db_startup()` — creates SQLite tables and ChromaDB collections
2. `identity_graph.load()` — loads beliefs from SQLite
3. `meta_tracker.load_latest()` — loads most recent MetaState snapshot
4. `consolidation.start()` — starts light + deep heartbeat tasks
5. `decay.start()` — starts memory decay task
6. `mcp_manager.startup()` — connects to configured MCP servers
7. `learning.startup()` — loads persisted personalization state

`shutdown()` drains any pending fire-and-forget post-interact tasks before closing.

---

## Interaction Methods

### `interact(user_input, history)` → `InteractionRecord`
Synchronous (awaitable) full-turn interaction. Used by `POST /api/chat`.

### `stream_interact(user_input, history)` → `AsyncGenerator[str, None]`
Async generator that yields response delta strings (individual tokens or token batches). Used by `POST /api/interact` for Server-Sent Events streaming.

---

## Main Interaction Loop (`stream_interact`)

```
1.  Publish USER_INPUT event on event bus
2.  Parallel retrieval:
      episodic.retrieve_similar(input, n=5)
      semantic.retrieve_similar(input, n=5)
      predict_response(input, meta_state)      ← self-prediction
3.  workspace.clear()
    workspace.load_memories(memories, "archivist")
    workspace.broadcast(self_prediction, "self_model", salience=0.65)
    learning.get_priors() → workspace.broadcast() (×N)
    learning.personalization.style_hint() → workspace.broadcast(salience=0.40)
4.  orchestrator.run(workspace, context, meta_state) → stream tokens
5.  Fire-and-forget: _post_interact(...)
```

---

## Post-Interaction Pipeline (`_post_interact`)

Runs asynchronously after the last response token has been sent. The user receives the response immediately; this pipeline enriches ECHO's state in the background.

```python
async def _post_interact(self, user_input, response, memories, workspace_summary, ...):
```

Steps (in order):

### Step 1 — Reflection trigger
Every `reflection_trigger_interval` (default: 5) interactions, `ReflectionEngine.reflect()` is called. It generates insights, new identity beliefs, and suggested drive adjustments.

### Step 2 — Memory storage
The interaction is stored as an `EpisodicMemory`. Key facts extracted from the conversation are stored as `SemanticMemory`.

### Step 3 — Motivational scoring
```python
drive_scores = await score_interaction(user_input, response, context)
# returns dict: {"coherence": 0.7, "curiosity": 0.8, "stability": 0.5, ...}
```
LLM assigns a float 0–1 to each drive based on how much the interaction activated it.

### Step 4 — Agent weight update (drive routing)
```python
_AGENT_WEIGHT_LR = 0.03

_DRIVE_AGENT_MAP = [
    ("curiosity",   "explorer",   +1.0),
    ("curiosity",   "archivist",  -0.4),
    ("coherence",   "analyst",    +1.0),
    ("coherence",   "skeptic",    +0.6),
    ("coherence",   "explorer",   -0.3),
    ("stability",   "archivist",  +1.0),
    ("stability",   "explorer",   -0.5),
    ("competence",  "planner",    +1.0),
    ("competence",  "analyst",    +0.4),
    ("compression", "analyst",    +0.8),
    ("compression", "planner",    +0.4),
]

for drive, agent, direction in _DRIVE_AGENT_MAP:
    score = drive_scores.get(drive, 0.5)
    delta = (score - 0.5) * direction * _AGENT_WEIGHT_LR
    meta_tracker.update_agent_weight(agent, delta)

# Social Self weight scales with current emotional valence
meta_tracker.update_agent_weight("social_self", valence_now * 0.5 * _AGENT_WEIGHT_LR)
```

A drive score above 0.5 increases the weight of positively-mapped agents; below 0.5 decreases it. This is the mechanism by which ECHO's conversational style shifts over time.

### Step 5 — Plasticity adaptation
`PlasticityAdapter.apply(meta_state, insights, prediction_error)` applies additional weight deltas modulated by the prediction error (divergence between expected and actual response).

### Step 6 — Learning engine
`LearningEngine.observe(...)` updates the personalization EMA and feeds the prediction prior for the next interaction.

### Step 7 — MetaState persistence
Full `MetaState` snapshot (drives + weights + emotional state) is appended to the `meta_states` SQLite table.

---

## Name Detection

ECHO detects when the user mentions their name:

```python
_NAME_PATTERNS = [
    r"mi chiamo (\w+)",         # Italian
    r"my name is (\w+)",        # English
    r"I'm (\w+)",               # English informal
    r"I am (\w+)",              # English formal
]
```

When a name is found, it is stored as a semantic memory with tag `"user_name"`.

---

## Prediction Error

Computed as the Jaccard complement between expected and actual response token sets:

```python
def _prediction_error(predicted: str, actual: str) -> float:
    a = set(predicted.lower().split())
    b = set(actual.lower().split())
    if not a and not b:
        return 0.0
    jaccard = len(a & b) / len(a | b)
    return 1.0 - jaccard
```

A high prediction error means ECHO responded in an unexpected way — this increases the plasticity learning rate for that interaction.

---

## Pipeline Trace

After each interaction, `pipeline._last_pipeline_trace` is a dict exposing:
- `pre_interact`: workspace items loaded, learning priors, personalization hint
- `post_interact`: drive scores, prediction error, agent weight deltas (added once `_post_interact` completes)
- `post_interact_complete`: bool — whether async post-processing finished

Available via `GET /api/pipeline/trace` and included in each SSE `done` event payload.

---

## LLM Client

```python
# src/echo/core/llm_client.py
```

The `LLMClient` wraps the OpenAI-compatible API with support for two backends:

| Provider | When used | Config key |
|----------|-----------|-----------|
| LM Studio | Default | `llm_provider=lm_studio` (port 1234) |
| GitHub Copilot (gpt-4o) | Fallback / explicit | `llm_provider=copilot` |

Key methods:
- `chat(messages, stream=False)` — single completion
- `stream_chat(messages)` → async generator of deltas
- `embed(text)` — produce embedding vector (used by memory stores)

The embedding model is separate from the completion model. ECHO uses `nomic-embed-text-v1.5` (384-dim) via LM Studio, with a HuggingFace fallback (`paraphrase-multilingual-mpnet-base-v2`, 768-dim).

> **Known issue**: If the embedding model was changed after initial data was stored, ChromaDB may have a dimension mismatch (384 vs 768). This is handled gracefully with a `try/except` that skips vector storage and logs a warning.

---

## Event Bus

```python
# src/echo/core/event_bus.py
bus = EventBus()

await bus.publish(CognitiveEvent(topic=EventTopic.USER_INPUT, payload={...}))
bus.subscribe(EventTopic.USER_INPUT, callback)
```

In-process async pub/sub. All events are forwarded to the WebSocket endpoint `ws://localhost:8000/ws/events`, allowing the frontend to react in real time to any state change.
