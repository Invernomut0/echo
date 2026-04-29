# Module 04 — Motivational System

**Source:** `src/echo/motivation/`

The motivational system assigns a numeric intensity to each of ECHO's five drives after every interaction. These scores directly drive the agent weight update mechanism, shaping how ECHO responds over time.

---

## Overview

ECHO is governed by five intrinsic motivational drives:

| Drive | Description | Example trigger |
|-------|-------------|-----------------|
| `coherence` | Desire for internal consistency and logical clarity | Contradictions, inconsistencies in conversation |
| `curiosity` | Drive to explore, discover, and learn new things | Novel topics, open questions |
| `stability` | Preference for predictability and familiar patterns | Routine topics, emotional grounding |
| `competence` | Drive to perform tasks well and demonstrate mastery | Technical problems, skill demonstrations |
| `compression` | Drive to simplify, abstract, and find patterns | Complex data, repetitive information |

Drives are continuous values in `[0, 1]`, representing current activation level. They do not represent emotional states directly — rather, they are the motivational forces that shape which cognitive agents are emphasized.

---

## Motivational Scorer

```python
# src/echo/motivation/motivational_scorer.py
async def score_interaction(
    user_input: str,
    response: str,
    context: str,
    meta_state: MetaState,
) -> dict[str, float]:
```

This function uses the LLM to analyze the interaction and assign a salience score to each drive.

### Prompt Structure

The scorer sends a structured prompt asking the LLM to evaluate how much each drive was activated by the exchange:

```
Given this interaction:
  User: {user_input}
  ECHO: {response}

Rate how much each drive was activated on a scale of 0.0 to 1.0:
- coherence: (logical consistency, structured thinking)
- curiosity: (exploration, questions, new information)
- stability: (reassurance, routine, familiar territory)
- competence: (task completion, skill, effectiveness)
- compression: (simplification, abstraction, pattern-finding)

Return JSON only: {"coherence": 0.0-1.0, "curiosity": 0.0-1.0, ...}
```

### Return Value

```python
{
    "coherence": 0.72,
    "curiosity": 0.85,
    "stability": 0.30,
    "competence": 0.60,
    "compression": 0.45,
}
```

If the LLM call fails or returns unparseable output, the scorer returns a dict of neutral `0.5` values for all drives.

---

## Drive → Agent Mapping

After scoring, the pipeline updates agent routing weights based on which drives are activated. The mapping is defined in `src/echo/core/pipeline.py`:

```python
_AGENT_WEIGHT_LR = 0.03

_DRIVE_AGENT_MAP: list[tuple[str, str, float]] = [
    # (drive, agent, polarity)
    ("curiosity",   "explorer",  +1.0),   # curiosity → explorer more active
    ("curiosity",   "archivist", -0.4),   # curiosity → archivist less active
    ("coherence",   "analyst",   +1.0),   # coherence → analyst more active
    ("coherence",   "skeptic",   +0.6),   # coherence → skeptic more active
    ("coherence",   "explorer",  -0.3),   # coherence → explorer less active
    ("stability",   "archivist", +1.0),   # stability → archivist more active
    ("stability",   "explorer",  -0.5),   # stability → explorer less active
    ("competence",  "planner",   +1.0),   # competence → planner more active
    ("competence",  "analyst",   +0.4),   # competence → analyst more active
    ("compression", "analyst",   +0.8),   # compression → analyst more active
    ("compression", "planner",   +0.4),   # compression → planner more active
]
```

### Update Formula

For each `(drive, agent, polarity)` tuple:

```python
score = drive_scores.get(drive, 0.5)       # 0.0–1.0 from scorer
delta = (score - 0.5) * polarity * LR     # centered at 0.5; LR = 0.03
meta_tracker.update_agent_weight(agent, delta)
```

A drive score of 0.5 produces zero delta (neutral). A score of 1.0 with polarity `+1.0` produces `delta = +0.015` per interaction. Since weights are clamped to `[0.1, 2.0]`, sustained activation is required to meaningfully shift behavior.

### Social Self Special Case

The `social_self` agent weight scales with the current emotional valence:

```python
valence = meta_state.emotional_valence   # [-1, 1]
meta_tracker.update_agent_weight("social_self", valence * 0.5 * LR)
```

When ECHO is in a positive emotional state (valence > 0), the social self agent is slightly amplified, making responses warmer and more relationally engaged.

---

## Drive Persistence

Drive scores are persisted in each `MetaState` snapshot appended to the `meta_states` SQLite table. This enables:
- Retrospective analysis of which drives dominated specific conversation periods
- Trend visualization in the frontend (`GET /api/state/history`)
- Consolidation logic that can adjust beliefs based on drive history

---

## Emotional State Derivation

Emotional valence and arousal are derived from the drive pattern:

```python
# Approximate derivation (implemented in meta_state.py)
emotional_valence = coherence * 0.4 + competence * 0.3 - (1 - stability) * 0.3
emotional_arousal = curiosity * 0.5 + compression * 0.3 + competence * 0.2
```

These are continuous, not discrete "emotions" — they represent the aggregate affective tone of the current cognitive state.

---

## Integration Points

| Component | Interaction |
|-----------|-------------|
| `CognitivePipeline._post_interact` | Calls `score_interaction()`, then applies drive→agent map |
| `MetaStateTracker.update_drives` | Receives final drive deltas |
| `MetaStateTracker.update_agent_weight` | Updated for each affected agent |
| `ReflectionEngine` | Can also submit drive adjustments via structured LLM output |
| `PlasticityAdapter` | Reads drive context to modulate additional weight deltas |
| `GET /api/state` | Exposes current drive values |
| `GET /api/state/history` | Exposes drive time series |
