# Module 10 — Deep Real-Time Learning

**Source:** `src/echo/learning/`

The Learning module enables ECHO to adapt in real-time. It is the coordination layer for all learning sub-systems, maintaining personalization, predictive analytics, meta-learning, self-evaluation, and growth tracking.

---

## Architecture (v0.5.0)

```
┌─────────────────────────────────────────────────────────┐
│                    LearningEngine                         │
│                                                           │
│  ┌──────────────────┐  ┌─────────────────────────────┐  │
│  │ Personalization   │  │ PredictiveAnalyticsEngine    │  │
│  │ (adaptive EMA α)  │  │ (EWMA forecasting)          │  │
│  └──────────────────┘  └─────────────────────────────┘  │
│                                                           │
│  ┌──────────────────┐  ┌─────────────────────────────┐  │
│  │ MetaLearningEngine│  │ SelfEvaluationEngine        │  │
│  │ (how to learn)    │  │ (performance tracking)      │  │
│  └──────────────────┘  └─────────────────────────────┘  │
│                                                           │
│  ┌──────────────────────────────────────────────────┐   │
│  │              GrowthTracker                         │   │
│  │  (long-term trajectory + stagnation detection)    │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## LearningEngine (Coordinator)

```python
class LearningEngine:
    personalization: PersonalizationState
    predictor: PredictiveAnalyticsEngine
    meta: MetaLearningEngine
    evaluation: SelfEvaluationEngine
    growth: GrowthTracker
```

### `startup()`
Loads all persisted state from SQLite (personalization, meta-learning observations, competence map, last assessment).

### `observe(response, user_input, novelty_score, curiosity, coherence, ...)`
Called in `_post_interact`. Orchestrates all sub-systems:
1. Classify interaction type (technical, emotional, creative, etc.)
2. Meta-learning: record observation, compute adaptive α
3. Personalization: update style preferences with adaptive α
4. Predictor: update EWMA forecasts
5. Self-evaluation: track engagement, update competence map
6. Growth: record metrics, check for stagnation → trigger shake-up

### `get_priors()` → `PredictionPriors`
Returns prediction items for workspace injection (curiosity spike prob, drift risk, consolidation urgency).

---

## PersonalizationState

Tracks user preferences with **adaptive EMA** (α dynamically set by MetaLearning):

| Dimension | Range | Description |
|-----------|-------|-------------|
| `verbosity` | [0, 1] | Preferred response length |
| `topic_depth` | [0, 1] | Preferred explanatory depth |
| `recall_frequency` | [0, 1] | Proactive memory surfacing rate |
| `drive_baselines` | dict | Long-run average drive activations |

### `style_hint()` → `str`
Generates a prompt-ready hint:
- verbosity < 0.35 → "Be concise — this user prefers short answers."
- topic_depth > 0.65 → "Go deep — this user engages with technical content."
- recall_frequency > 0.65 → "Proactively surface relevant past context."

---

## PredictiveAnalyticsEngine

EWMA-based forecasting (α=0.20, window=20):

| Output | Description |
|--------|-------------|
| `emotional_valence_forecast` | Expected next valence [-1, 1] |
| `curiosity_spike_prob` | Probability of curiosity spike [0, 1] |
| `identity_drift_risk` | Risk of identity drift [0, 1] |
| `consolidation_urgency` | How urgently consolidation is needed [0, 1] |

Predictions above actionable thresholds are injected into the workspace as low-salience priors.

---

## Sub-Modules (New in v0.5.0)

| Module | Doc | Purpose |
|--------|-----|---------|
| Meta-Learning | [Module 13](13-meta-learning.md) | Tracks learning quality, adapts α |
| Self-Evaluation | [Module 14](14-self-evaluation.md) | Engagement, competence map, skill assessment |
| Growth Tracker | [Module 17](17-growth-tracker.md) | Trajectory, stagnation, shake-ups |

---

## Configuration

| Setting | Default | Source |
|---------|---------|--------|
| `_SAVE_INTERVAL` | 5 | Persist personalization every N interactions |
| Base EMA α | 0.08 | Overridden by MetaLearning's `recommended_alpha` |
| EWMA α (predictor) | 0.20 | Faster than personalization (detects trends sooner) |
| Assessment interval | 50 | Full skill assessment every 50 interactions |
| Stagnation threshold | 200 | Interactions without improvement before shake-up |

---

## Integration Points

| Component | Interaction |
|-----------|-------------|
| `CognitivePipeline.startup` | `learning.startup()` → loads all sub-systems |
| `CognitivePipeline._post_interact` | `learning.observe()` → full update cycle |
| `CognitivePipeline.stream_interact` | `learning.get_priors()` → workspace injection |
| `PlasticityAdapter` | Receives `prediction_error` for weight modulation |
| `MetacognitiveModel` | Receives competence map + growth trajectory |
| Deep-sleep consolidation | Growth report generation |
