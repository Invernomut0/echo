# Module 12 — Co-Evolutionary Cognitive Partner

**Source:** `src/echo/curiosity/interest_profile.py`, `src/echo/curiosity/stimulus_queue.py`  
**Added in:** v0.4.0

The Co-Evolutionary Cognitive Partner gives ECHO the ability to model the user's intellectual interests over time and proactively inject relevant findings into the conversation pipeline. ECHO and the user co-evolve together: the user's interests shape what ECHO researches; ECHO's findings shape the user's curiosity.

---

## Overview

```
conversation ──► interest_profile.infer_from_memories()
                         │
                         ▼
                 interest_profile (EMA affinity per topic)
                         │
                 ┌───────┴────────┐
                 │                │
           curiosity engine   ZPD expansion
           query blending     (every 4 cycles)
                 │
                 ▼
          StimulusQueue.enqueue(top-3 findings)
                 │
                 ▼
          pipeline: pop_best() → workspace.broadcast()
                 │
                 ▼
          user sees stimulus in ECHO's response
                 │
                 ▼
          feedback (explicit star rating OR implicit self_relevance > 0.7)
                 │
                 ▼
          interest_profile.record_feedback() ─► affinity update (EMA)
```

---

## UserInterestProfile

**File:** `src/echo/curiosity/interest_profile.py`  
**Storage:** SQLite table `interest_profile` (raw `aiosqlite`, not ORM)

```python
class UserInterestProfile:
    _EMA_ALPHA: float = 0.10
    _MAX_TOPICS: int  = 100
```

### Schema

```sql
CREATE TABLE interest_profile (
    topic            TEXT PRIMARY KEY,
    affinity_score   REAL NOT NULL DEFAULT 0.5,
    interaction_count INTEGER NOT NULL DEFAULT 0,
    last_seen        TEXT NOT NULL,
    is_excluded      INTEGER NOT NULL DEFAULT 0,   -- boolean
    is_preferred     INTEGER NOT NULL DEFAULT 0    -- boolean
)
```

### Key Methods

| Method | Description |
|--------|-------------|
| `primary_interests(n=5)` | Top-N topics by affinity DESC, excluding blocked topics |
| `all_topics()` | All tracked topics |
| `excluded_topics()` | Topics marked as excluded |
| `zpd_topics(n=3)` | LLM call: "given these interests, suggest adjacent unexplored topics" |
| `record_feedback(topic, delta)` | EMA update: `affinity ← 0.9·affinity + 0.1·delta` |
| `mark_excluded(topic)` | Sets `is_excluded=True`; zeroes affinity score |
| `mark_preferred(topic)` | Sets `is_preferred=True`; adds +0.25 boost to affinity |
| `infer_from_memories(user_input, response)` | LLM topic extraction → upsert into table |

### EMA Affinity Update

```python
new_affinity = (1 - alpha) * current + alpha * delta
```

`delta` values:
- Explicit positive feedback → `1.0`
- Implicit feedback (stimulus → self_relevance > 0.7) → `0.8`
- Explicit negative feedback → `0.0`
- `mark_preferred` boost → `+0.25` additive (clamped to 1.0)

### ZPD Topic Generation

```python
async def zpd_topics(self, n: int = 3) -> list[str]:
```

Prompts the LLM with the user's primary interests and asks for adjacent, not-yet-seen topics. Results are filtered by word-overlap to avoid returning topics already tracked with high affinity.

This implements **Vygotsky's Zone of Proximal Development** — topics just beyond the user's current focus, achievable with a little exploration.

### Topic Inference from Memories

```python
async def infer_from_memories(self, user_input: str, response: str) -> list[str]:
```

After each interaction, the LLM extracts 1–5 topic keywords from the combined user input + ECHO response. Each extracted topic is upserted into `interest_profile` with a small positive delta (`+0.3`).

The module-level singleton `interest_profile` is imported wherever needed:

```python
from echo.curiosity.interest_profile import interest_profile
```

---

## StimulusQueue

**File:** `src/echo/curiosity/stimulus_queue.py`  
**Storage:** SQLite table `stimulus_queue` (raw `aiosqlite`)

```python
class StimulusQueue:
    pass   # all methods are async
```

### Schema

```sql
CREATE TABLE stimulus_queue (
    id               TEXT PRIMARY KEY,
    content          TEXT NOT NULL,
    source_memory_id TEXT,
    topic            TEXT NOT NULL,
    affinity_score   REAL NOT NULL DEFAULT 0.5,
    created_at       TEXT NOT NULL,
    presented_at     TEXT,           -- NULL until pop_best() selects it
    feedback_score   REAL            -- NULL until rated
)
```

### Key Methods

| Method | Description |
|--------|-------------|
| `enqueue(content, topic, affinity_score, source_memory_id)` | Add finding; skips if same `source_memory_id` already pending |
| `mark_presented(stimulus_id)` | Sets `presented_at = now()` |
| `record_feedback(stimulus_id, score)` | Saves score; propagates delta to `interest_profile.record_feedback()` |
| `clear_stale(max_age_hours=48)` | Removes unrated, old items |
| `pending(limit=10)` | Items with `presented_at IS NULL`, ORDER BY `affinity_score DESC` |
| `pop_best()` | `pending(1)` + `mark_presented()` — returns the item or `None` |
| `all_items(limit=50)` | All items ordered by `affinity_score DESC` |

The module-level singleton `stimulus_queue` is imported wherever needed:

```python
from echo.curiosity.stimulus_queue import stimulus_queue
```

---

## Pipeline Integration

### Proactive Stimulus Nudge

In `CognitivePipeline.stream_interact()` and `_run_pipeline()`, after the workspace is loaded, a stimulus nudge is attempted:

```python
# Probability scales with arousal
_nudge_p = 0.2 + 0.3 * self.meta_tracker.current.arousal

if random.random() < _nudge_p:
    _stimulus = await stimulus_queue.pop_best()
    if _stimulus:
        self.workspace.broadcast(
            f"[Curiosity Stimulus | topic: {_stimulus['topic']}] {_stimulus['content']}",
            source_agent="curiosity_stimulus",
            salience=0.55,
        )
        await bus.publish(CognitiveEvent(
            topic=EventTopic.CURIOSITY_STIMULUS,
            payload={"stimulus_id": _stimulus["id"], "topic": _stimulus["topic"]},
        ))
```

The stimulus is broadcast into the Global Workspace as a regular item competing for the 7 available slots. If it wins a slot, it influences the agent deliberations — and ultimately ECHO's response will reference or engage with the finding.

**Nudge probability range:**
- When `arousal = 0.0` → p = 0.20
- When `arousal = 1.0` → p = 0.50

### Implicit Feedback Loop

In `_post_interact()`, after the interaction memory is stored:

```python
await interest_profile.infer_from_memories(user_input=user_input, response=response)

if injected_stimulus_id and mem.self_relevance > 0.7:
    await stimulus_queue.record_feedback(injected_stimulus_id, score=0.8)
```

If the response to a stimulus-influenced interaction is judged highly self-relevant (`> 0.7`), ECHO automatically records positive feedback — reinforcing the topic's affinity without requiring the user to rate anything.

---

## Frontend: CuriosityPanel

The `CuriosityPanel.tsx` component exposes three new sections:

### Interest Profile Section
Displays the top primary interests as horizontal affinity bars. Each topic shows:
- Topic name
- Interaction count
- Affinity bar (gradient from cyan to violet)
- ✕ exclude button

### ZPD Zone Section
Displays the LLM-suggested adjacent topics with an **Explore →** button. Clicking it:
1. Marks the topic as preferred (`guideTopics([topic], [])`)
2. Triggers an immediate curiosity cycle (`triggerCuriosityCycle()`)
3. Refreshes the profile

### Pending Findings Section
Lists stimuli waiting in the queue with:
- Topic tag
- Affinity match %
- Finding text
- 1–5 star rating widget (explicit feedback)

---

## API Endpoints Summary

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/curiosity/profile` | Interest profile + ZPD topics |
| GET | `/api/curiosity/findings` | Pending stimuli |
| GET | `/api/curiosity/findings/all` | All stimuli (history) |
| POST | `/api/curiosity/feedback` | Rate a finding `{stimulus_id, score}` |
| POST | `/api/curiosity/guide` | Mark preferred/excluded topics |

See [REST API Reference](../api/rest-api.md#curiosity) for full request/response schemas.

---

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `_EMA_ALPHA` | `0.10` | EMA smoothing factor for affinity updates |
| `_MAX_TOPICS` | `100` | Maximum tracked topics before oldest are pruned |
| `_ZPD_EVERY_N_CYCLES` | `4` | Curiosity cycles between ZPD expansions |
| `nudge_p_base` | `0.20` | Base probability of stimulus injection |
| `nudge_p_arousal_coeff` | `0.30` | Extra probability per unit of arousal |
| Implicit feedback threshold | `0.70` | Minimum `self_relevance` for automatic positive feedback |

---

## Integration Points

| Component | Interaction |
|-----------|-------------|
| `CuriosityEngine` | Enqueues top-3 findings; uses profile for query blending + ZPD |
| `CognitivePipeline.stream_interact` | Stimulus nudge before workspace broadcast |
| `CognitivePipeline._run_pipeline` | Same nudge for sync path |
| `CognitivePipeline._post_interact` | Topic inference + implicit feedback recording |
| `CuriosityRouter` (API) | Exposes profile, findings, feedback, guide endpoints |
| `CuriosityPanel.tsx` (Frontend) | Renders Interest Profile, ZPD Zone, Pending Findings UI |
