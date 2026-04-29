# Module 09 — Plasticity Adapter

**Source:** `src/echo/plasticity/adapter.py`

The PlasticityAdapter implements rule-based synaptic-like weight adjustments for cognitive agents. It complements the motivation-driven updates with heuristic pattern detection — adjusting agent weights when observable interaction patterns suggest a particular agent is over- or under-performing.

---

## Overview

Biological neural plasticity refers to the brain's ability to strengthen or weaken synaptic connections based on activity. ECHO's PlasticityAdapter does the same for agent weights:

- Agents whose patterns consistently improve interactions get stronger
- Agents whose patterns produce poor outcomes get weaker
- All weights drift toward neutral (`1.0`) over time to prevent runaway specialization

---

## PlasticityAdapter

```python
# src/echo/plasticity/adapter.py
class PlasticityAdapter:
    LEARNING_RATE: float = 0.05
    DECAY_RATE: float = 0.005
    WEIGHT_MIN: float = 0.1
    WEIGHT_MAX: float = 2.0

    async def adapt(
        self,
        interaction: InteractionRecord,
        prediction_error: float,
        meta_state: MetaState,
    ):
```

Called in `CognitivePipeline._post_interact` after motivational scoring.

---

## Rule-Based Deltas

The adapter checks a set of pattern rules against the latest `InteractionRecord` and assigns raw deltas:

| Rule | Condition | Agent | Raw Delta |
|------|-----------|-------|-----------|
| Structured response | response contains ≥3 numbered/bulleted sections | `planner` | `+0.02` |
| Novel topic | semantic similarity to recent history < 0.3 | `explorer` | `+0.02` |
| User disagreement | user message contains negation + "you said" | `skeptic` | `+0.03` |
| Memory reference | response references explicit past event | `archivist` | `+0.02` |
| Short, warm response | response < 100 words AND positive valence | `social_self` | `+0.02` |
| Deep analysis | response > 300 words with logical connectors | `analyst` | `+0.02` |
| Question asked | user message ends in `?` AND response provides plan | `planner` | `+0.02` |
| Repetitive pattern | high similarity to 3+ recent responses | all agents | `-0.01` |

These rules are heuristic and intentionally conservative — small nudges only.

---

## Prediction Error Modulation

The raw deltas from rules are multiplied by the `prediction_error` scalar before application:

```python
effective_delta = raw_delta * prediction_error * LEARNING_RATE
```

`prediction_error` (from `CognitivePipeline`) represents how different the actual interaction was from what ECHO predicted:
- `prediction_error = 1.0` — maximum surprise → deltas applied at full strength
- `prediction_error = 0.0` — interaction matched prediction exactly → no plasticity update

This ensures that plasticity only fires when ECHO is genuinely surprised — high-confidence interactions do not cause weight drift.

---

## Weight Decay

After applying rule deltas, all weights decay toward `1.0`:

```python
for agent in meta_state.agent_weights:
    current = meta_state.agent_weights[agent]
    drift = (current - 1.0) * DECAY_RATE
    new = max(WEIGHT_MIN, min(WEIGHT_MAX, current - drift))
    meta_tracker.update_agent_weight(agent, new - current)
```

With `DECAY_RATE = 0.005`, a weight of `2.0` decays by `0.005 × 1.0 = 0.005` per interaction. Without new stimulation, weights return to neutral in roughly 200 interactions.

---

## Full Update Sequence

```python
# In _post_interact:
1. score_interaction() → drive scores
2. Apply _DRIVE_AGENT_MAP → agent weight deltas
3. plasticity.adapt(interaction, prediction_error, meta_state)
   a. Evaluate pattern rules → raw deltas
   b. Multiply by prediction_error × LR
   c. Apply deltas to agent weights
   d. Apply decay toward 1.0
4. meta_tracker.persist()
```

---

## Interaction Record

The `InteractionRecord` passed to `adapt()` contains all the information needed for rule evaluation:

```python
class InteractionRecord(BaseModel):
    user_input: str
    response: str
    agent_perspectives: dict[str, str]
    memory_sources: list[str]
    semantic_similarity_to_history: float   # cosine similarity
    response_word_count: int
    timestamp: datetime
```

---

## Configuration

PlasticityAdapter constants are currently hardcoded:

| Constant | Value | Description |
|----------|-------|-------------|
| `LEARNING_RATE` | `0.05` | Scales all deltas |
| `DECAY_RATE` | `0.005` | Rate of drift toward neutral per interaction |
| `WEIGHT_MIN` | `0.1` | Floor for agent weights |
| `WEIGHT_MAX` | `2.0` | Ceiling for agent weights |

---

## Integration Points

| Component | Interaction |
|-----------|-------------|
| `CognitivePipeline._post_interact` | Calls `plasticity.adapt()` after motivational scoring |
| `MetaStateTracker` | Receives final weight deltas |
| `Orchestrator` | Reads updated weights from MetaState on next interaction |
