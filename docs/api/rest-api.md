# REST API Reference

**Base URL:** `http://localhost:8000`  
**Frontend:** `http://localhost:5173`

---

## Authentication

No authentication is required. ECHO is designed for single-user local deployment.

---

## Endpoints

### Health

#### `GET /health`

Returns the system health status and version.

**Response:**
```json
{
  "status": "ok",
  "version": "0.4.0",
  "pipeline_ready": true,
  "memory_backend": "chromadb",
  "llm_provider": "lmstudio"
}
```

---

### Chat

#### `POST /api/chat`

Synchronous chat — waits for the full response before returning.

**Request body:**
```json
{
  "message": "string",
  "stream": false
}
```

**Response:**
```json
{
  "response": "string",
  "meta_state": {
    "drives": {
      "coherence": 0.65,
      "curiosity": 0.72,
      "stability": 0.50,
      "competence": 0.58,
      "compression": 0.45
    },
    "agent_weights": {
      "analyst": 1.0,
      "explorer": 1.15,
      "skeptic": 0.95,
      "archivist": 1.0,
      "social_self": 1.05,
      "planner": 0.90
    },
    "emotional_state": {
      "valence": 0.1,
      "arousal": 0.3,
      "label": "calm"
    }
  },
  "memory_sources": ["episodic", "semantic"],
  "timestamp": "2024-01-15T10:30:00Z"
}
```

---

#### `POST /api/interact`

Streaming SSE chat — yields tokens as they are generated.

**Request body:**
```json
{
  "message": "string"
}
```

**Response:** `text/event-stream`

Each event is a JSON object on a `data:` line.

**Delta event** (one per token):
```
data: {"type": "delta", "content": "Hello"}

```

**Done event** (stream complete):
```
data: {
  "type": "done",
  "meta_state": { ... },
  "memory_sources": ["episodic", "semantic"],
  "pipeline_trace": {
    "workspace_items": 4,
    "agents_used": ["analyst", "explorer", "planner"],
    "routing_weights": {"analyst": 1.0, "explorer": 1.15, "planner": 0.9},
    "reflection_triggered": false,
    "memories_stored": 2,
    "tools_used": []
  },
  "tools_used": []
}

```

**Error event:**
```
data: {"type": "error", "message": "LLM unavailable"}

```

---

### Pipeline

#### `GET /api/pipeline/trace`

Returns the trace from the most recent `/api/interact` call.

**Response:**
```json
{
  "workspace_items": 4,
  "agents_used": ["analyst", "explorer", "planner"],
  "routing_weights": {
    "analyst": 1.0,
    "explorer": 1.15,
    "skeptic": 0.95,
    "archivist": 1.0,
    "social_self": 1.05,
    "planner": 0.9
  },
  "reflection_triggered": false,
  "memories_stored": 2,
  "tools_used": []
}
```

---

### State

#### `GET /api/state`

Returns the current cognitive state of ECHO.

**Response:**
```json
{
  "meta_state": {
    "drives": { ... },
    "agent_weights": { ... },
    "emotional_state": { ... }
  },
  "memory_counts": {
    "episodic": 142,
    "semantic": 38,
    "autobiographical": 7
  },
  "workspace_active_items": 3,
  "identity_beliefs_count": 24,
  "uptime_seconds": 3600
}
```

---

#### `GET /api/state/history`

Returns a time series of historical state snapshots.

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 50 | Maximum number of snapshots |

**Response:**
```json
[
  {
    "timestamp": "2024-01-15T10:00:00Z",
    "drives": {
      "coherence": 0.60,
      "curiosity": 0.65,
      "stability": 0.55,
      "competence": 0.50,
      "compression": 0.40
    },
    "interaction_count": 10
  },
  ...
]
```

---

### Memory

#### `GET /api/memory/vectors`

Returns vector store status and statistics.

**Response:**
```json
{
  "backend": "chromadb",
  "embedding_dim": 768,
  "total_vectors": 180,
  "active_vectors": 155,
  "dormant_vectors": 25,
  "avg_chunks_per_memory": 2.3,
  "collections": {
    "episodic": 120,
    "semantic": 38,
    "autobiographical": 22
  }
}
```

---

#### `GET /api/memory/semantic`

Returns all semantic memories (knowledge, discoveries, insights).

**Query parameters:**

| Parameter | Type | Default |
|-----------|------|---------|
| `limit` | integer | 50 |

**Response:**
```json
{
  "memories": [
    {
      "id": "uuid",
      "content": "string",
      "tags": ["curiosity", "source:arxiv"],
      "salience": 0.72,
      "timestamp": "2024-01-15T09:00:00Z",
      "is_dormant": false
    }
  ],
  "total": 38
}
```

---

#### `GET /api/memory/chunks`

Returns raw memory chunks (embedding-level granularity).

**Query parameters:**

| Parameter | Type | Default |
|-----------|------|---------|
| `limit` | integer | 200 |

**Response:**
```json
{
  "chunks": [
    {
      "id": "uuid",
      "parent_memory_id": "uuid",
      "content": "string",
      "embedding_dim": 768,
      "has_vector": true,
      "memory_type": "episodic"
    }
  ],
  "total": 180
}
```

---

#### `GET /api/memory/{id}`

Returns a single memory by ID.

**Path parameters:**

| Parameter | Description |
|-----------|-------------|
| `id` | Memory UUID |

**Response:** `MemoryEntry` object (see [Data Models](./data-models.md)).

**Error:**
```json
{"detail": "Memory not found"}
```
HTTP 404.

---

#### `DELETE /api/memory/{id}`

Deletes a memory from both SQLite and ChromaDB.

**Path parameters:**

| Parameter | Description |
|-----------|-------------|
| `id` | Memory UUID |

**Response:**
```json
{"deleted": true, "id": "uuid"}
```

---

#### `POST /api/memory/resolve-conflict`

Manually resolves a contradiction between two identity beliefs.

**Request body:**
```json
{
  "belief_id_a": "uuid",
  "belief_id_b": "uuid",
  "resolution": "keep_a" | "keep_b" | "merge" | "mark_uncertain"
}
```

**Response:**
```json
{
  "resolved": true,
  "action": "keep_a",
  "removed_belief_id": "uuid",
  "coherence_score_after": 0.82
}
```

---

### WebSocket

#### `WS /ws/events`

Live event stream of all internal cognitive events.

**Connect:** `ws://localhost:8000/ws/events`

**Received messages** (JSON):

```json
{
  "topic": "memory.stored",
  "data": {
    "memory_id": "uuid",
    "memory_type": "episodic",
    "salience": 0.65
  },
  "timestamp": "2024-01-15T10:30:01Z"
}
```

**Available topics:**

| Topic | Description |
|-------|-------------|
| `memory.stored` | New memory added |
| `memory.dormant` | Memory became dormant |
| `workspace.broadcast` | Item added to GlobalWorkspace |
| `reflection.triggered` | Reflection cycle started |
| `reflection.complete` | Reflection finished |
| `consolidation.started` | Consolidation phase begins |
| `dream.generated` | Dream narrative created |
| `curiosity.discovered` | New knowledge found |
| `curiosity.stimulus_injected` | Proactive stimulus pushed to workspace |
| `agent.weight_updated` | Agent weight changed |
| `drive.updated` | Drive score changed |

---

## Error Responses

---

### Curiosity

#### `GET /api/curiosity/activity`

Returns curiosity cycle history and activity statistics.

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `hours` | integer | 24 | Look-back window |

**Response:**
```json
{
  "cycles": [
    {
      "id": "uuid",
      "timestamp": "2026-04-30T10:00:00Z",
      "queries_run": 3,
      "results_found": 8,
      "stored": 2,
      "sources": ["arxiv", "wikipedia"],
      "topics": ["machine learning", "cognitive science"]
    }
  ],
  "recently_searched": ["machine learning", "consciousness"],
  "total_discoveries": 42
}
```

---

#### `POST /api/curiosity/trigger`

Manually triggers one curiosity cycle (ignores idle guard).

**Response:**
```json
{"stored": 2, "queries": ["machine learning", "cognitive architectures"]}
```

---

#### `GET /api/curiosity/profile`

Returns the user interest profile built by ECHO through conversation.

**Response:**
```json
{
  "primary_interests": [
    {
      "topic": "machine learning",
      "affinity_score": 0.82,
      "interaction_count": 14,
      "last_seen": "2026-04-30T09:15:00Z",
      "is_excluded": false,
      "is_preferred": false
    }
  ],
  "zpd_topics": ["transfer learning", "cognitive architectures"],
  "excluded_topics": ["cryptocurrency"],
  "total_topics": 23
}
```

`zpd_topics` are adjacent, unexplored topics suggested by the LLM based on the user's primary interests (Zone of Proximal Development).

---

#### `GET /api/curiosity/findings`

Returns pending (not-yet-rated) stimuli from the queue.

**Query parameters:**

| Parameter | Type | Default |
|-----------|------|---------|
| `limit` | integer | 20 |

**Response:**
```json
{
  "pending": [
    {
      "id": "uuid",
      "content": "New paper: Scaling laws for neural language models...",
      "topic": "machine learning",
      "affinity_score": 0.75,
      "created_at": "2026-04-30T08:00:00Z",
      "presented_at": "2026-04-30T10:00:00Z",
      "feedback_score": null
    }
  ],
  "count": 3
}
```

---

#### `GET /api/curiosity/findings/all`

Returns all stimuli (pending + rated), ordered by affinity descending.

**Query parameters:**

| Parameter | Type | Default |
|-----------|------|---------|
| `limit` | integer | 50 |

**Response:**
```json
{"items": [...], "count": 12}
```

---

#### `POST /api/curiosity/feedback`

Rate how relevant a finding was. Propagates feedback to the interest profile affinity score.

**Request body:**
```json
{"stimulus_id": "uuid", "score": 0.8}
```

`score` is `[0, 1]` (0 = irrelevant, 1 = very relevant).

**Response:**
```json
{"ok": true}
```

---

#### `POST /api/curiosity/guide`

Guide ECHO's curiosity by marking topics as preferred or excluded.

**Request body:**
```json
{
  "preferred": ["cognitive science", "neuroscience"],
  "excluded": ["cryptocurrency"]
}
```

**Response:**
```json
{"ok": true, "preferred_added": 2, "excluded_added": 1}
```

---

### Consolidation & Self-Model

#### `POST /api/consolidation/trigger`

Manually triggers a consolidation cycle.

**Response:**
```json
{"triggered": true, "phase": "light"}
```

---

#### `GET /api/consolidation/echo-md`

Returns the current content of ECHO's self-maintained personality file (`data/echo.md`). This file is written and updated by ECHO itself after every consolidation cycle.

**Response:**
```json
{
  "content": "# ECHO\n\nI am ECHO...",
  "last_modified": "2026-04-30T06:00:00Z",
  "path": "data/echo.md"
}
```

---

#### `POST /api/consolidation/echo-md/review`

Manually triggers a personality self-review. ECHO reads its current `echo.md` and the latest MetaState, then rewrites the file to reflect its current state.

**Response:**
```json
{"updated": true, "changed": true}
```

`changed` is `false` if ECHO decided no update was necessary.

---

## Error Responses

All errors return standard HTTP status codes with a JSON body:

```json
{
  "detail": "Error message"
}
```

| Status | Meaning |
|--------|---------|
| `400` | Invalid request body |
| `404` | Resource not found |
| `422` | Validation error (Pydantic) |
| `500` | Internal server error |
| `503` | LLM unavailable |
