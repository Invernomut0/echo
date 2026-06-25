# Module 14 — Self-Evaluation Loop

**Source:** `src/echo/learning/self_evaluation.py`

ECHO evaluates its own performance over time using implicit feedback signals and periodic LLM-based skill assessments.

---

## Components

### 1. Prediction Error Tracking
Rolling trend of prediction error over a 50-interaction window. Negative slope = ECHO is getting better at predicting its own behavior.

### 2. Engagement Detection (Heuristic)
Implicit feedback from user behavior — no explicit ratings needed:

| Signal | Effect |
|--------|--------|
| Long user messages | +engagement |
| Positive markers ("grazie", "perfect", "great") | +engagement |
| Negative markers ("no", "wrong", "sbagliato") | −engagement |
| Questions (?) | +engagement |
| Very short replies without questions | −engagement |

Running EMA (α=0.12) produces a continuous engagement score ∈ [0, 1].

### 3. Competence Map
Per-domain competence scores tracked with adaptive EMA:
```python
signal = (1.0 - prediction_error) * 0.6 + engagement * 0.4
alpha = min(0.3, 0.15 / (1 + count * 0.01))  # faster convergence for new domains
score = score + alpha * (signal - score)
score = score * 0.995 + 0.5 * 0.005  # slow decay toward neutral
```

Domains: `technical`, `emotional`, `creative`, `philosophical`, `general`

### 4. Skill Assessment (LLM, every 50 interactions)
Evaluates 6 dimensions:
- **Accuracy** — factual correctness
- **Helpfulness** — practical utility
- **Depth** — explanatory thoroughness
- **Empathy** — emotional awareness
- **Creativity** — novel thinking
- **Self-awareness** — metacognitive accuracy

Results are persisted to SQLite and strengths/weaknesses are stored as semantic memories.

---

## SQLite Tables

| Table | Purpose |
|-------|---------|
| `skill_assessments` | Periodic 6-dimension scores + insights |
| `competence_map` | Per-domain competence with sample count |

---

## Integration

| Component | Interaction |
|-----------|-------------|
| `LearningEngine.observe()` | Calls `evaluation.observe_interaction()` every turn |
| Semantic memory | Stores assessment strengths/weaknesses for future retrieval |
| Metacognitive model | Competence map feeds `update_from_learning()` |
