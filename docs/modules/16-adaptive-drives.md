# Module 16 — Adaptive Drive Dynamics

**Source:** `src/echo/motivation/adaptive_drives.py`

Enhances the basic 5-drive system with momentum, conflict resolution, drive-to-behavior mapping, and autonomous goal creation.

---

## Components

### 1. Drive Momentum
Drives that stay high/low for multiple consecutive turns build momentum:

```python
if consecutive_high >= 3 and momentum > 0:
    boost = 0.015 * min(consecutive_high / 5, 2.0)
```

This creates an **inertia effect** — trends amplify until the drive resolves.

### 2. Drive Conflict Resolution
When competing drives are both above 0.65:

| Conflict Pair | Resolution |
|---------------|------------|
| curiosity ↔ stability | Higher-momentum drive wins |
| curiosity ↔ coherence | Higher-momentum drive wins |
| compression ↔ curiosity | Higher-momentum drive wins |

The loser is suppressed by `min(0.05, (value - 0.5) * 0.1)`.

### 3. Drive → Behavior Mapping
When drives reach extreme values, behavior directives are injected into the workspace:

| Drive | Condition | Behavior |
|-------|-----------|----------|
| curiosity | > 0.75 | "Ask follow-up questions. Explore tangents." |
| curiosity | < 0.25 | "Stay focused. Avoid digressions." |
| coherence | > 0.75 | "Cross-reference past context. Ensure consistency." |
| coherence | < 0.25 | "Check for contradictions. Flag inconsistencies." |
| competence | > 0.75 | "Demonstrate expertise. Provide detailed solutions." |
| competence | < 0.25 | "Acknowledge limitations. Seek to learn." |

### 4. Drive-to-Goal Bridge
When a drive stays above 0.75 for 5+ consecutive turns:
- Auto-creates a goal via `GoalStore`
- Priority scales with drive value
- 50-turn cooldown between auto-goals for same drive
- Also triggers for low coherence/competence/stability (below 0.25)

Goal templates per drive:
| Drive | Auto-Goal Title |
|-------|----------------|
| curiosity | "Explore emerging topic of interest" |
| coherence (low) | "Resolve internal belief contradictions" |
| stability (low) | "Consolidate identity and communication patterns" |
| competence (low) | "Improve capability in weak domain" |
| compression (high) | "Synthesise accumulated knowledge" |

---

## Integration

| Component | Interaction |
|-----------|-------------|
| `_post_interact` | Called after drive scoring; momentum deltas applied to MetaState |
| `GlobalWorkspace` | Behavior directives injected for next interaction |
| `GoalStore` | Auto-goals created when thresholds met |
