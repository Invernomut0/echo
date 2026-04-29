# Module 10 — Learning Engine

**Source:** `src/echo/learning/engine.py`

The LearningEngine enables ECHO to adapt to individual users over time. It maintains a **personalization model** that tracks communication style preferences, interaction patterns, and domain interests — then injects this context into the workspace before each response.

---

## Architecture

The LearningEngine coordinates two sub-components:

| Component | Purpose |
|-----------|---------|
| `PersonalizationState` | Tracks user communication style, vocabulary, and preferences using Exponential Moving Averages (EMA) |
| `PredictiveAnalyticsEngine` | Tracks interaction metrics using Exponentially Weighted Moving Averages (EWMA) for prediction |

---

## LearningEngine

```python
# src/echo/learning/engine.py
class LearningEngine:
    _SAVE_INTERVAL: int = 5   # persist every 5 interactions

    async def startup(self):
    async def observe(self, interaction: InteractionRecord, meta_state: MetaState):
    def get_priors(self) -> PredictionPriors:
```

### `startup()`

Loads persisted personalization data from SQLite (`personalization_state` table). If no data exists, initializes with neutral defaults.

### `observe(interaction, meta_state)`

Called in `_post_interact` after plasticity adaptation. Updates both sub-components:

```python
await self.personalization.update(interaction)
await self.predictive.update(interaction, meta_state)
```

Also handles persistence: every `_SAVE_INTERVAL` calls, writes the current personalization state to SQLite.

### `get_priors()` → `PredictionPriors`

Returns current predictions to inject into the workspace:

```python
class PredictionPriors(BaseModel):
    predicted_response_length: int        # chars
    predicted_formality_level: float      # 0=casual, 1=formal
    predicted_topic_domain: str           # e.g. "technical", "personal", "philosophical"
    items: list[WorkspacePriorItem]
```

`items` are workspace-ready strings summarizing the personalization context.

---

## PersonalizationState

```python
# src/echo/learning/personalization.py
class PersonalizationState:
    EMA_ALPHA: float = 0.15    # smoothing factor
```

Tracks user preferences using EMA: `new_value = α × current + (1 − α) × ema_value`

### Tracked Dimensions

| Dimension | Description | Default |
|-----------|-------------|---------|
| `avg_message_length` | Average user message length (chars) | 100 |
| `formality_score` | Estimated formality [0, 1] | 0.5 |
| `tech_vocabulary_ratio` | Ratio of technical terms [0, 1] | 0.3 |
| `question_ratio` | Ratio of messages that are questions [0, 1] | 0.3 |
| `preferred_response_length` | Preferred ECHO response length (chars) | 300 |
| `domain_interests` | `dict[str, float]` — domain → interest score | {} |

### `style_hint()` → `str`

Produces a natural-language hint injected into the workspace:

```python
def style_hint(self) -> str:
    parts = []
    if self.formality_score > 0.7:
        parts.append("User prefers formal, precise language")
    elif self.formality_score < 0.3:
        parts.append("User prefers casual, conversational style")
    if self.tech_vocabulary_ratio > 0.6:
        parts.append("User uses technical vocabulary")
    if self.preferred_response_length < 150:
        parts.append("User prefers concise responses")
    elif self.preferred_response_length > 500:
        parts.append("User appreciates detailed explanations")
    return ". ".join(parts) if parts else ""
```

---

## PredictiveAnalyticsEngine

```python
# src/echo/learning/predictive.py
class PredictiveAnalyticsEngine:
    EWMA_ALPHA: float = 0.2
```

Tracks rolling statistics on interaction quality:

| Metric | Description |
|--------|-------------|
| `avg_salience` | EWMA of memory salience scores |
| `avg_motivation_delta` | EWMA of total motivation change per interaction |
| `response_acceptance_rate` | Estimated user acceptance (no immediate correction/retry) |
| `dominant_drive_history` | List of the most active drive per interaction |

### Prediction Error Computation

The predictive engine computes `prediction_error` for the pipeline:

```python
def compute_prediction_error(
    self,
    interaction: InteractionRecord,
    predicted_length: int,
    predicted_formality: float,
) -> float:
    length_error = abs(interaction.response_word_count - predicted_length / 5) / max(predicted_length / 5, 1)
    formality_error = abs(actual_formality - predicted_formality)
    return min(1.0, (length_error + formality_error) / 2)
```

This value flows back to `PlasticityAdapter` to modulate weight updates.

---

## SQLite Persistence

Personalization data is stored in the `personalization_state` table:

```sql
CREATE TABLE personalization_state (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   DATETIME NOT NULL,
    state_json  TEXT NOT NULL    -- JSON-encoded PersonalizationState fields
);
```

Only the **latest row** is loaded at startup. Historical rows are kept for potential trend analysis.

---

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `_SAVE_INTERVAL` | `5` | Persist every N interactions |
| `EMA_ALPHA` (PersonalizationState) | `0.15` | Learning rate for style tracking |
| `EWMA_ALPHA` (PredictiveAnalytics) | `0.20` | Learning rate for metric tracking |

---

## Integration Points

| Component | Interaction |
|-----------|-------------|
| `CognitivePipeline.startup` | Calls `learning.startup()` |
| `CognitivePipeline._post_interact` | Calls `learning.observe()` |
| `CognitivePipeline.stream_interact` | Calls `learning.get_priors()` |
| `GlobalWorkspace` | Receives priors as workspace items |
| `PlasticityAdapter` | Receives `prediction_error` for weight modulation |
