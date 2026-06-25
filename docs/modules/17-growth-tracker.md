# Module 17 — Growth Tracker

**Source:** `src/echo/learning/growth_tracker.py`

Measures ECHO's long-term improvement trajectory and triggers self-correction when growth stagnates.

---

## Metrics (Rolling Window = 100)

| Metric | Source | Interpretation |
|--------|--------|---------------|
| `prediction_error_avg` | Meta-learning | Lower = better self-prediction |
| `prediction_error_trend` | Linear regression slope | Negative = improving |
| `engagement_avg` | Self-evaluation | Higher = user more engaged |
| `engagement_trend` | Linear regression slope | Positive = more engaged over time |
| `drive_stability` | 1 − mean(drive_variance) | Higher = more stable cognitive state |

---

## Growth Score Formula

```python
growth_score = (
    -error_trend * 20          # error improvement (dominant factor)
    + engagement_trend * 10     # engagement improvement
    + (drive_stability - 0.5) * 0.5  # stability bonus
)
# Clamped to [-1.0, +1.0]
```

- **Positive** → ECHO is genuinely improving
- **Zero** → stable (neither growing nor degrading)
- **Negative** → performance degrading

---

## Stagnation Detection & Shake-Up

**Stagnation condition:** no improvement in best prediction error average for 200+ interactions.

**Shake-up actions:**
1. Boost curiosity drive by +0.2
2. Reduce stability by −0.1 (encourage exploration)
3. Create self-improvement goal: "Break out of learning stagnation"
4. Store shake-up event as semantic memory
5. Reset stagnation counter

---

## Growth Reports (Deep-Sleep)

Every 100 interactions during deep-sleep consolidation:
- Generate a structured report summarizing trajectory
- Persist to `growth_reports` SQLite table
- Store as semantic memory (tag: `growth_report`)

---

## Integration

| Component | Interaction |
|-----------|-------------|
| `LearningEngine.observe()` | Calls `growth.observe()` every turn |
| Auto shake-up | Triggered when `metrics.shake_up_needed` is True |
| Deep-sleep consolidation | `growth.generate_report()` |
| Metacognitive model | Growth trajectory feeds self-model updates |
