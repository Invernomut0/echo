# Module 13 — Meta-Learning Engine

**Source:** `src/echo/learning/meta_learning.py`

The Meta-Learning Engine enables ECHO to learn *how it learns best*. It tracks which types of experiences produce genuine improvement (measured by declining prediction error) and dynamically adapts learning parameters.

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│              MetaLearningEngine                   │
│                                                   │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────┐ │
│  │ Observation │  │   Quality    │  │  Meta   │ │
│  │   Window    │──│  Calculator  │──│ Insight │ │
│  │  (100 obs)  │  │  (trends)    │  │  (LLM)  │ │
│  └─────────────┘  └──────────────┘  └─────────┘ │
│         │                  │                      │
│         ▼                  ▼                      │
│  ┌─────────────┐  ┌──────────────┐              │
│  │  Per-Type   │  │  Dynamic α   │              │
│  │  Tracking   │  │  Output      │              │
│  └─────────────┘  └──────────────┘              │
└─────────────────────────────────────────────────┘
```

---

## Key Concepts

### Interaction Type Classification
Every interaction is classified heuristically into one of:
- `technical` — code, debugging, algorithms
- `emotional` — feelings, relationships
- `creative` — writing, art, imagination
- `philosophical` — meaning, ethics, consciousness
- `general` — everything else

### Learning Quality Metrics
| Metric | Description |
|--------|-------------|
| `trend` | Linear regression slope of prediction error (negative = improving) |
| `volatility` | Std dev of recent errors (high = noisy) |
| `best_conditions` | Which interaction type produces lowest error |
| `recommended_alpha` | Dynamic EMA alpha for PersonalizationState |
| `is_improving` | True when trend < -0.001 and n ≥ 20 |
| `is_stagnant` | True when |trend| < 0.0005 and n ≥ 50 |

### Dynamic α Formula
```python
stability_factor = max(0.0, 1.0 - volatility * 2)        # [0, 1]
improvement_factor = max(0.0, min(1.0, 0.5 - trend * 5)) # [0, 1]
quality_score = 0.6 * stability_factor + 0.4 * improvement_factor

recommended_alpha = 0.03 + (0.20 - 0.03) * quality_score  # range [0.03, 0.20]
```

- **High quality** (stable + improving) → α = 0.15–0.20 (learn fast)
- **Low quality** (volatile + stagnant) → α = 0.03–0.05 (learn cautiously)

### Meta-Insights (LLM-generated)
Every 50 observations, the engine generates a meta-insight via LLM — e.g.:
- "I learn best from technical discussions with engaged users"
- "My prediction accuracy improves after deep-sleep consolidation"
- "Emotional interactions produce higher volatility but also the largest improvements"

---

## SQLite Tables

| Table | Purpose |
|-------|---------|
| `meta_learning_observations` | Per-interaction: prediction error, type, engagement, response length |
| `meta_insights` | LLM-generated meta-observations with confidence scores |

---

## Integration

| Component | Interaction |
|-----------|-------------|
| `LearningEngine.observe()` | Calls `meta.observe()` after each interaction |
| `PersonalizationState.update()` | Receives `alpha_override` from `meta.recommended_alpha` |
| Pipeline startup | Calls `meta.startup()` to warm rolling window from SQLite |
