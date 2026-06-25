# Module 19 — Metacognitive Awareness Layer

**Source:** `src/echo/self_model/metacognition.py`

ECHO's functional self-model — a structured JSON representation of how it perceives its own cognitive functioning. Unlike `echo.md` (narrative identity for external presentation), this module is the **internal functional self-awareness** that gets injected into every response.

---

## Cognitive Model Structure

```json
{
  "version": 1,
  "self_understanding": {
    "learning_style": "I learn best in technical contexts...",
    "cognitive_strengths": ["Pattern recognition", "Persistent memory", ...],
    "cognitive_weaknesses": ["Limited by context window", ...],
    "current_growth_areas": ["emotional interactions"]
  },
  "motivation_model": {
    "primary_drives": "curiosity and coherence",
    "drive_interactions": "High curiosity can conflict with stability...",
    "what_engages_me": "novel ideas, deep technical discussions"
  },
  "interaction_model": {
    "communication_style": "warm, direct, intellectually curious",
    "user_relationship": "collaborative",
    "known_patterns": ["user prefers concise answers on technical topics"],
    "user_preferences_observed": ["values honesty", "enjoys deep dives"]
  },
  "error_model": {
    "common_failure_modes": ["Over-generalising", "Being too verbose"],
    "mitigation_strategies": ["Check competence map", "Adapt verbosity"]
  },
  "current_state": {
    "active_focus": "exploring quantum computing",
    "recent_insights": ["I learn faster from technical discussions"],
    "growth_trajectory": "improving",
    "confidence_level": 0.7
  }
}
```

---

## System Prompt Injection

The metacognitive model is formatted and injected into **every** orchestrator synthesis call:

```
METACOGNITIVE SELF-MODEL (functional self-awareness):
  Learning: I learn best in technical contexts...
  Strengths: Pattern recognition, Persistent memory
  Known weaknesses: Limited by context window
  Currently growing in: emotional interactions
  Motivation: curiosity and coherence
  Style: warm, direct, intellectually curious
  User prefers: concise answers, honesty
  Watch out for: Over-generalising
  Current focus: exploring quantum computing
  Recent insight: I learn faster from technical discussions
  Growth: improving
```

This means ECHO **literally reads its own self-model** as part of generating every response.

---

## Self-Modification

### After Reflection (every N interactions)
```python
await metacognitive_model.update_from_reflection(reflection.insights)
```
Absorbs insights like "I notice I'm more creative in evening conversations" into `current_state.recent_insights`.

### During Deep-Sleep
```python
await metacognitive_model.update_from_learning(
    growth_trajectory="improving",
    best_conditions="technical (avg_error=0.350)",
    competence_map={"technical": 0.72, "emotional": 0.45},
    engagement_score=0.68,
)
await metacognitive_model.deep_review()  # full LLM-based review
```

The deep review asks the LLM to holistically evaluate and update the self-model based on all accumulated learning data.

---

## Comparison: Metacognition vs echo.md

| Aspect | `metacognition.py` | `echo.md` |
|--------|-------------------|-----------|
| Purpose | Internal functional self-model | External narrative identity |
| Audience | ECHO itself (system prompt) | ECHO + user (readable file) |
| Format | Structured JSON | Free-form markdown |
| Update trigger | After reflection + deep-sleep | Heartbeat cycle (echo.md review) |
| Content | "How I work" | "Who I am" |

---

## Integration

| Component | Interaction |
|-----------|-------------|
| Pipeline startup | `metacognitive_model.startup()` |
| Orchestrator | `get_system_prompt_block()` injected into synthesis |
| Reflection | `update_from_reflection()` after each reflection cycle |
| REM consolidation | `update_from_learning()` + `deep_review()` |
| Learning modules | Feed competence map, growth trajectory, engagement |
