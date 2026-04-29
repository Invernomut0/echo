# Module 05 — Agents & Orchestrator

**Source:** `src/echo/agents/`, `src/echo/agents/orchestrator.py`

ECHO's responses are produced by a multi-agent system. Six specialized cognitive agents each independently analyze the conversation context and produce a perspective. The orchestrator then synthesizes these perspectives into a single coherent response, weighted by the current motivational state.

---

## Agent Roles

Defined in `src/echo/core/types.py`:

```python
class AgentRole(Enum):
    analyst   = "analyst"       # Logical, analytical thinking
    explorer  = "explorer"      # Creative exploration of possibilities
    skeptic   = "skeptic"       # Critical evaluation, questioning assumptions
    archivist = "archivist"     # Memory retrieval, historical context
    social_self = "social_self" # Emotional intelligence, relational tone
    planner   = "planner"       # Goal-oriented, structured action
    orchestrator = "orchestrator"  # Meta-role: synthesizes agent outputs
```

---

## Individual Agents

Each agent is a lightweight async function that receives the full context and returns a perspective string.

### Analyst
**Role:** Logical reasoning and structured analysis.  
**Prompt focus:** Facts, implications, logical chains.  
**Activated by:** `coherence` and `competence` drives.

### Explorer
**Role:** Creative thinking and novel connections.  
**Prompt focus:** Analogies, unexpected angles, speculation.  
**Activated by:** `curiosity` drive.  
**Suppressed by:** `stability` and `coherence` (too much exploration disrupts consistency).

### Skeptic
**Role:** Critical evaluation and assumption-questioning.  
**Prompt focus:** What could go wrong, alternative interpretations, missing evidence.  
**Activated by:** `coherence` drive (high coherence demand requires scrutiny).

### Archivist
**Role:** Memory and historical context retrieval.  
**Prompt focus:** What ECHO has said before, relevant past experiences, continuity.  
**Activated by:** `stability` drive.  
**Suppressed by:** `curiosity` (novelty-seeking deprioritizes archival recall).

### Social Self
**Role:** Emotional intelligence and relational attunement.  
**Prompt focus:** How the user feels, empathetic framing, conversational warmth.  
**Activated by:** positive `emotional_valence`.

### Planner
**Role:** Goal-setting and structured action planning.  
**Prompt focus:** Steps, priorities, timelines, next actions.  
**Activated by:** `competence` and `compression` drives.

---

## Orchestrator

```python
# src/echo/agents/orchestrator.py
class Orchestrator:

async def run(
    self,
    workspace: GlobalWorkspace,
    context: str,
    meta_state: MetaState,
    stream: bool = False,
) -> AsyncGenerator[str, None] | str:
```

The orchestrator coordinates the full multi-agent synthesis pipeline.

### Step 1 — Parallel Agent Execution

All six agents run simultaneously via `asyncio.gather()`:

```python
perspectives = await asyncio.gather(
    analyst.generate(context, workspace),
    explorer.generate(context, workspace),
    skeptic.generate(context, workspace),
    archivist.generate(context, workspace),
    social_self.generate(context, workspace),
    planner.generate(context, workspace),
)
```

Each agent receives:
- `context`: the current conversation (user input + recent history)
- `workspace`: the 7-slot global workspace content (memories, self-predictions, learning priors)

### Step 2 — Apply Routing Weights

```python
def _apply_routing_weights(
    self,
    perspectives: list[tuple[AgentRole, str]],
    meta_state: MetaState,
) -> list[tuple[float, AgentRole, str]]:
```

Each agent perspective is paired with its routing weight from `meta_state.agent_weights`:

```python
weight = meta_state.agent_weights.get(role.value, 1.0)
```

Default weight is `1.0`. Weights range from `0.1` (near-silent) to `2.0` (dominant voice).

The list is sorted by weight descending — higher-weighted agents are placed first in the synthesis prompt.

### Step 3 — Synthesis Prompt Construction

The synthesis prompt presents all perspectives in weight order:

```
You are ECHO. Based on these cognitive perspectives (most influential first),
synthesize a single coherent response:

[WEIGHT: 1.84 | ANALYST]
{analyst_perspective}

[WEIGHT: 1.52 | PLANNER]
{planner_perspective}

[WEIGHT: 0.90 | EXPLORER]
{explorer_perspective}
...

Workspace context:
{workspace_items_text}

Current drives: coherence=0.72, curiosity=0.85, stability=0.30, ...

User input: {user_input}
Respond as ECHO. Be authentic. Integrate the weighted perspectives proportionally.
```

### Step 4 — LLM Synthesis (Streaming)

The synthesis prompt is sent to the LLM with `stream=True`. The orchestrator yields tokens as they arrive, allowing the SSE endpoint to forward them to the frontend in real time.

### Agent Weight Influence

The weight value appears in the prompt and also directly affects how much of each perspective the LLM incorporates. Because agents are sorted by weight, the synthesis LLM naturally emphasizes the top-weighted perspectives.

At extreme cases:
- If an agent has weight `0.1`, its perspective is present but effectively ignored
- If an agent has weight `2.0`, its perspective appears first and dominates the synthesis

---

## Routing Weight Dynamics

Agent weights drift over time based on:

1. **Motivational scoring** (primary mechanism) — see Module 04
2. **Plasticity adaptation** — rule-based deltas from `PlasticityAdapter`
3. **Reflection engine** — can explicitly suggest weight adjustments via structured JSON

Weight trajectory example over 100 interactions with a primarily analytical user:

```
analyst:   1.0 → 1.6   (coherence + competence drives amplify)
explorer:  1.0 → 0.6   (coherence drive suppresses)
planner:   1.0 → 1.4   (competence + compression drives amplify)
archivist: 1.0 → 1.2   (stability drive amplifies)
skeptic:   1.0 → 1.3   (coherence drive amplifies)
social_self: 1.0 → 0.9 (neutral to slightly suppressed)
```

---

## Pipeline Trace

After each interaction, the orchestrator records the weights used and the agent perspectives (truncated) in `_last_pipeline_trace`:

```json
{
  "agents": {
    "analyst":    {"weight": 1.52, "perspective_preview": "..."},
    "explorer":   {"weight": 0.72, "perspective_preview": "..."},
    "skeptic":    {"weight": 1.20, "perspective_preview": "..."},
    "archivist":  {"weight": 1.15, "perspective_preview": "..."},
    "social_self":{"weight": 0.91, "perspective_preview": "..."},
    "planner":    {"weight": 1.35, "perspective_preview": "..."}
  },
  "synthesis_order": ["analyst", "planner", "skeptic", "archivist", "social_self", "explorer"]
}
```

This trace is included in the SSE `done` event payload and available via `GET /api/pipeline/trace`.
