# Module 18 — Deep Associative Memory

**Source:** `src/echo/memory/associative.py`

Enhances memory retrieval beyond vector similarity with lateral connections, cross-pollination, and temporal pattern discovery.

---

## Components

### 1. Random Walk Retrieval
During each interaction, after standard vector retrieval:

```
seed_memories (with linked_ids)
    │
    ├── hop 1: follow random causal link
    ├── hop 2: follow another link
    └── hop 3: (max depth)
```

- Follows `linked_ids` edges (causal links from temporal sequencing)
- Max 3 hops, branch factor 2
- Returns 1-2 additional memories not found by vector search
- Only memories with `current_strength > 0.1` are returned

**Purpose:** Discover contextually relevant memories that share a causal chain with the current conversation, even if their content isn't directly similar.

### 2. Cross-Pollination (Deep-Sleep)
During REM consolidation:

1. Select 3 pairs of memories that are:
   - Distant in time (different thirds of memory timeline)
   - Not already linked
2. Ask LLM: "Is there a non-obvious conceptual connection?"
3. If connection found:
   - Create bidirectional causal link
   - Persist association with description + strength
   - Store synthesis as semantic memory

**Purpose:** Discover analogies and patterns that emerge from diverse experiences.

### 3. Temporal Clustering (Deep-Sleep)
1. Group memories from the last 7 days by date
2. Ask LLM to identify 1-3 recurring themes spanning multiple days
3. Store discovered themes as semantic memories (tag: `temporal_pattern`)

**Purpose:** Surface implicit interests or concerns the user hasn't stated explicitly.

---

## SQLite Table

| Column | Type | Description |
|--------|------|-------------|
| `memory_a_id` | String | First memory in the association |
| `memory_b_id` | String | Second memory |
| `association_type` | String | `cross_pollination`, `temporal`, `random_walk` |
| `description` | Text | LLM-generated connection description |
| `strength` | Float | Connection strength [0, 1] |

---

## Integration

| Component | Trigger |
|-----------|---------|
| Pipeline retrieval | `random_walk_retrieve()` after vector search |
| REM consolidation | `cross_pollinate()` + `temporal_clustering()` |
| Episodic store | New causal links created by cross-pollination |
