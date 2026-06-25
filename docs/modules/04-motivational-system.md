# Module 04 — Motivational System

**Source:** `src/echo/motivation/`

The motivational system assigns activation intensity to each of ECHO's five drives after every interaction, then applies adaptive dynamics including momentum, conflict resolution, and autonomous goal creation.

---

## Overview

ECHO is governed by five intrinsic motivational drives:

| Drive | Description | Example trigger |
|-------|-------------|-----------------|
| `coherence` | Desire for internal consistency and logical clarity | Contradictions, inconsistencies |
| `curiosity` | Drive to explore, discover, and learn new things | Novel topics, open questions |
| `stability` | Preference for predictability and familiar patterns | Routine topics, grounding |
| `competence` | Drive to perform tasks well and demonstrate mastery | Technical problems, skill use |
| `compression` | Drive to simplify, abstract, and find patterns | Complex data, repetition |

Drives are continuous values in `[0, 1]`. They shape which cognitive agents are emphasized and, through the Adaptive Drive Dynamics module, directly influence behavior and goal creation.

---

## Motivational Scorer (LLM-based)

```python
async def score_interaction(user_input, response, meta_state) -> dict[str, float]
```

Uses the LLM to evaluate how much each drive was activated by the exchange. Returns scores in [0, 1] per drive.

---

## Drive → Agent Mapping

```python
_AGENT_WEIGHT_LR = 0.03

_DRIVE_AGENT_MAP = [
    ("curiosity",   "explorer",  +1.0),
    ("curiosity",   "archivist", -0.4),
    ("coherence",   "analyst",   +1.0),
    ("coherence",   "skeptic",   +0.6),
    ("coherence",   "explorer",  -0.3),
    ("stability",   "archivist", +1.0),
    ("stability",   "explorer",  -0.5),
    ("competence",  "planner",   +1.0),
    ("competence",  "analyst",   +0.4),
    ("compression", "analyst",   +0.8),
    ("compression", "planner",   +0.4),
]
```

Formula: `delta = (score - 0.5) * polarity * LR`

---

## Adaptive Drive Dynamics (v0.5.0)

After basic scoring, the **AdaptiveDriveEngine** applies:

### Momentum
Drives that stay above 0.6 for 3+ consecutive turns get an extra boost:
```
boost = 0.015 × min(consecutive_high / 5, 2.0)
```

### Conflict Resolution
When competing drives both exceed 0.65, the higher-momentum drive wins and the other is suppressed.

| Conflict Pair |
|---------------|
| curiosity ↔ stability |
| curiosity ↔ coherence |
| compression ↔ curiosity |

### Drive → Behavior
Extreme drives inject directives into the workspace (e.g., curiosity > 0.75 → "Ask follow-up questions").

### Drive → Goal Bridge
Sustained high/low drives (5+ turns) auto-create goals via GoalStore. See [Module 16](16-adaptive-drives.md) for details.

---

## Hebbian Weight Evolution

Drives active during competence improvements get their weights (`w_i` in `M = Σ w_i · d_i`) increased:

```python
if competence_delta > 0 and drive_val > 0.6:
    weight += 0.004
elif competence_delta < 0 and drive_val > 0.6:
    weight -= 0.002
# Weights re-normalised to sum = 1.0
```

---

## Emotional State Derivation

```python
valence_signal = (coherence + competence - stability * 0.3) / 2.0 - 0.5
arousal_target = 0.3 + 0.5 * prediction_error + 0.2 * mean_activation
```

Emotional valence and arousal are **derived** from drive patterns, not explicitly set.

---

## Integration Points

| Component | Interaction |
|-----------|-------------|
| `_post_interact` | `score_interaction()` → drive scoring |
| `_post_interact` | `adaptive_drives.update()` → momentum + conflicts + goals |
| `MetaStateTracker` | Receives drive deltas + momentum deltas |
| `GlobalWorkspace` | Receives drive behavior directives |
| `GoalStore` | Receives auto-goals from drive-to-goal bridge |
| `PlasticityAdapter` | Uses drives to compute agent weight adjustments |
