# Module 11 — Curiosity Engine

**Source:** `src/echo/curiosity/engine.py`

The CuriosityEngine gives ECHO intrinsic motivation to learn. When ECHO has been idle (no user interaction) for long enough, it proactively searches the internet for topics related to its recent semantic memories — expanding its knowledge without being prompted.

---

## Overview

The curiosity loop runs as a background task started by `CognitivePipeline.startup`. It is entirely **autonomous** — no user input required.

```
idle check → extract queries → multi-source search → deduplicate → store
```

---

## CuriosityEngine

```python
# src/echo/curiosity/engine.py
class CuriosityEngine:
    async def start(self):          # starts the background loop
    async def tick(self):           # single curiosity cycle
    async def shutdown(self):
```

### The Curiosity Loop

```python
while True:
    await asyncio.sleep(check_interval)  # default: 60s
    await self.tick()
```

### `tick()`

```python
async def tick(self):
    # 1. Idle guard
    if time_since_last_interaction < curiosity_idle_threshold:
        return

    # 2. Extract queries from recent memories
    queries = await self._extract_queries()
    if not queries:
        return

    # 3. Search all providers
    results = await self._search_all(queries)

    # 4. Deduplicate
    unique_results = self._deduplicate(results)

    # 5. Store as semantic memories
    for result in unique_results:
        await self._store_discovery(result)
```

---

## Idle Guard

```python
if time_since_last_interaction < self.config.curiosity_idle_threshold_seconds:
    return   # user is active; don't interrupt with background learning
```

Default threshold: **180 seconds** (3 minutes).

This prevents curiosity from firing while ECHO is in an active conversation.

---

## Query Extraction

```python
async def _extract_queries(self) -> list[str]:
```

Retrieves the 10 most recent semantic memories and prompts the LLM to identify interesting follow-up topics:

```
Based on these recent thoughts:
{memory_summaries}

Generate 1-3 search queries for topics you're genuinely curious about.
Return JSON: {"queries": ["query1", "query2"]}
```

The LLM response is parsed; if parsing fails or the LLM returns 0 queries, the tick is skipped.

---

## Search Providers

Queries are sent to multiple providers in order. All searches run concurrently:

```python
tasks = [
    self._search_arxiv(query),
    self._search_hackernews(query),
    self._search_wikipedia(query),
    self._search_ddg(query),       # DuckDuckGo
]
if self.mcp_manager.brave_available:
    tasks.append(self._search_brave_mcp(query))

results = await asyncio.gather(*tasks, return_exceptions=True)
```

### Provider Details

| Provider | API / Method | Result fields |
|----------|-------------|---------------|
| **arXiv** | REST `export.arxiv.org/api/query` | title, abstract, URL, published date |
| **HackerNews** | Algolia HN Search API | title, points, URL, created_at |
| **Wikipedia** | Wikipedia REST API `/page/summary` | extract (first paragraph), URL |
| **DuckDuckGo** | `duckduckgo_search` library (HTML API) | title, body, URL |
| **Brave** (MCP) | `brave_search` MCP tool | title, description, URL |

Each provider returns up to 3 results per query. Failed providers are silently skipped.

---

## Deduplication

```python
def _deduplicate(self, results: list[SearchResult]) -> list[SearchResult]:
```

Uses a **word-overlap heuristic**:

1. Tokenize each result's title and description into a set of non-stopword words
2. Compute Jaccard similarity: `|A ∩ B| / |A ∪ B|`
3. If similarity > 0.5 with any already-accepted result → skip
4. Also skip results with the same URL

This avoids storing near-duplicate articles from different providers covering the same event.

---

## Storing Discoveries

Each unique result is stored as a semantic memory:

```python
await semantic_store.add(MemoryEntry(
    id=generate_uuid(),
    content=f"{result.title}\n\n{result.description}",
    source="curiosity",
    memory_type=MemoryType.semantic,
    tags=["curiosity", f"source:{result.provider}", result.topic_tag],
    salience=self._compute_salience(result),
    timestamp=datetime.utcnow(),
))
```

### Salience Computation

```python
def _compute_salience(self, result: SearchResult) -> float:
    base = 0.4
    if result.provider == "arxiv":
        base += 0.2   # academic papers get higher salience
    if result.recency_days < 7:
        base += 0.15  # fresh content is more salient
    return min(1.0, base)
```

### Tags

| Tag | Example | Meaning |
|-----|---------|---------|
| `"curiosity"` | `"curiosity"` | Always present |
| `"source:<provider>"` | `"source:arxiv"` | Which provider found it |
| Topic tag | `"technology"` | Extracted from LLM query context |

---

## MCP Integration

When the Brave Search MCP server is available, it is used as an additional provider. The MCP manager checks connectivity during `CognitivePipeline.startup`:

```python
self.mcp_manager = MCPManager(config)
await self.mcp_manager.startup()
# Registers: brave_search (if configured), fetch (always)
```

MCP tools are called via:

```python
result = await mcp_manager.call_tool("brave_search", {"query": q, "count": 3})
```

---

## Configuration

| Setting | Default | Env var |
|---------|---------|---------|
| `curiosity_idle_threshold_seconds` | `180` | `ECHO_CURIOSITY_IDLE_THRESHOLD_SECONDS` |

---

## Integration Points

| Component | Interaction |
|-----------|-------------|
| `CognitivePipeline.startup` | Starts the CuriosityEngine background loop |
| `SemanticMemoryStore` | Receives discovered content |
| `LLMClient` | Extracts search queries |
| `MCPManager` | Optionally provides Brave search tool |
