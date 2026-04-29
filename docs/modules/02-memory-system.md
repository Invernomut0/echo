# Module 02 — Memory System

**Source:** `src/echo/memory/`

ECHO maintains three distinct memory stores, each serving a different cognitive purpose. All stores use a dual-backend: **SQLite** for structured metadata and **ChromaDB** for vector embeddings (semantic similarity retrieval).

---

## Overview

| Store | Purpose | File |
|-------|---------|------|
| `EpisodicMemoryStore` | Autobiographical interactions | `episodic.py` |
| `SemanticMemoryStore` | Facts, beliefs, knowledge | `semantic.py` |
| `AutobiographicalStore` | Compressed life summaries | `autobiographical.py` |

---

## MemoryEntry (shared data model)

Defined in `src/echo/core/types.py`:

```python
class MemoryEntry(BaseModel):
    id: str                         # UUID
    content: str                    # Full text content
    memory_type: MemoryType         # episodic | semantic | autobiographical
    importance: float = 0.5         # [0, 1]
    novelty: float = 0.5            # [0, 1]
    self_relevance: float = 0.5     # [0, 1]
    emotional_weight: float = 0.5   # [0, 1]
    salience: float                 # computed (see formula below)
    decay_lambda: float             # 1.0 - salience
    current_strength: float = 1.0   # decays over time
    created_at: datetime
    tags: list[str] = []
    is_dormant: bool = False        # set by consolidation when unused
    has_vector: bool = False        # True when ChromaDB entry exists
```

### Salience Formula

$$\text{salience} = 0.3 \times \text{importance} + 0.2 \times \text{novelty} + 0.3 \times \text{self\_relevance} + 0.2 \times \text{emotional\_weight}$$

### Memory Decay

ECHO implements exponential decay on all memories:

$$I(t) = I_0 \cdot e^{-\lambda t}$$

where $\lambda = 1 - \text{salience}$.

High-salience memories (importance + emotional weight + self-relevance) decay slowly; low-salience memories degrade quickly. The decay scheduler runs every `memory_decay_interval_seconds` (default: 300 s).

---

## Episodic Memory Store

```python
# src/echo/memory/episodic.py
class EpisodicMemoryStore:
```

**SQLite table:** `episodic_memories`  
**ChromaDB collection:** `episodic_memory`

Episodic memory records every interaction ECHO has. Each entry captures the conversational content plus its metadata (importance, emotional weight, salience).

### Key Methods

| Method | Description |
|--------|-------------|
| `store(entry: MemoryEntry)` | Save to SQLite; attempt ChromaDB vector embedding |
| `retrieve_similar(text, n_results=5)` | Vector search (falls back to SQLite if ChromaDB unavailable) |
| `get_all(limit=100)` | All memories sorted by `salience × current_strength` |
| `get(memory_id)` | Single memory by ID |
| `delete(memory_id)` | Remove from both SQLite and ChromaDB |
| `count()` → `int` | Synchronous ChromaDB count |
| `acount()` → `int` | Async SQLite count |

### Lifecycle Flags

- `is_dormant`: set by the light consolidation phase when a memory has not been accessed recently. Dormant memories are candidates for compression or deletion. Cleared automatically when a memory is retrieved.
- `has_vector`: set to `True` only when ChromaDB embedding succeeded. Memories without vectors cannot be retrieved via semantic similarity — they are reachable only by direct ID lookup.

### ChromaDB Dimension Mismatch Handling

If the embedding model changes between runs (e.g., from 768-dim HuggingFace to 384-dim LM Studio), the `store()` method catches the `InvalidDimensionException` and gracefully skips vector storage, logging a warning. The entry is still saved to SQLite with `has_vector=False`.

---

## Semantic Memory Store

```python
# src/echo/memory/semantic.py
class SemanticMemoryStore:
```

**SQLite table:** `semantic_memories`  
**ChromaDB collection:** `semantic_memory`

Semantic memory stores factual knowledge, extracted concepts, beliefs, and findings from the curiosity engine. While episodic memory is autobiographical (what happened), semantic memory is encyclopedic (what is known).

### Chunking

Large semantic memory entries are split into overlapping chunks by `src/echo/memory/chunker.py` before embedding. This allows fine-grained vector retrieval even for long documents.

Each chunk is stored as a separate ChromaDB document, linked back to the parent memory ID via metadata. The `get_all_chunks(limit)` method returns each memory with its associated chunk texts and embedding previews.

### Key Methods

Identical interface to `EpisodicMemoryStore`, plus:

| Method | Description |
|--------|-------------|
| `get_all_chunks(limit=200)` | Returns list of dicts with `memory_id`, `content`, `chunks`, `chunk_count`, `avg_chunks` |

---

## Autobiographical Store

```python
# src/echo/memory/autobiographical.py
class AutobiographicalStore:
```

**SQLite table:** `autobiographical_memories`

Autobiographical memory stores compressed summaries of ECHO's life history, produced during deep consolidation cycles. Unlike episodic memory (individual events), autobiographical memory captures narrative arcs and identity-relevant patterns spanning multiple interactions.

Entries include:
- `period_start` / `period_end` timestamps
- `summary` text (LLM-generated narrative)
- `key_events` list (references to episodic memory IDs)
- `identity_impact` score (how much this period shaped identity beliefs)

---

## Memory Decay Scheduler

```python
# src/echo/memory/decay.py
class DecayScheduler:
```

Runs as a background asyncio task every `memory_decay_interval_seconds` (default: 300 s). On each tick:

1. Loads all memories from both episodic and semantic stores.
2. Applies the exponential decay formula to `current_strength`.
3. Writes updated `current_strength` back to SQLite.
4. Memories below a configured minimum strength threshold may be marked dormant.

This ensures that memories ECHO rarely accesses gradually fade in relevance, mimicking biological memory consolidation.

---

## Dream Store

```python
# src/echo/memory/dream_store.py
class DreamStore:
```

**SQLite table:** `dream_entries`

Stores `DreamEntry` records generated during the REM phase:

```python
class DreamEntry(BaseModel):
    id: str
    dream: str                  # LLM-generated dream narrative
    source_memory_count: int    # How many memories seeded the dream
    cycle_type: str             # "light" | "rem"
    created_at: datetime
```

Dreams are first-person poetic narratives (2–4 sentences) that weave together themes from the most salient recent memories in a non-linear, symbolic way. They are stored for introspective purposes but do not directly influence the pipeline unless accessed via the reflection engine.

---

## Memory Pipeline Integration

```
Interaction
  │
  ├── episodic.retrieve_similar()    ← pre-interaction: find relevant context
  ├── semantic.retrieve_similar()    ← pre-interaction: find relevant facts
  │
  │   [response generated]
  │
  ├── episodic.store(new_entry)      ← post-interaction: record what happened
  └── semantic.store(extracted_facts)  ← post-interaction: store key knowledge
```

The retrieval results are loaded into the Global Workspace before agents deliberate, providing them with contextual grounding from ECHO's past experience.

---

## ChromaDB vs SQLite Coverage

The `/api/memory/vectors` endpoint reports coverage:

```json
{
  "episodic_sqlite_count": 42,
  "episodic_vector_count": 38,
  "semantic_sqlite_count": 17,
  "semantic_vector_count": 15,
  "episodic_coverage_pct": 90.5,
  "semantic_coverage_pct": 88.2
}
```

Coverage below 100% indicates memories stored before the embedding model was available, or that were affected by dimension mismatch. These memories are still accessible via direct ID or full-text listing, but will not appear in similarity search results.
