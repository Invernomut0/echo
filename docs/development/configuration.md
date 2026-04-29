# Configuration Reference

ECHO is configured via environment variables loaded from a `.env` file in the project root. All variables use the `ECHO_` prefix and are handled by Pydantic Settings (`pydantic-settings`).

**Source:** `src/echo/core/config.py`

---

## Minimal `.env`

```env
# LM Studio base URL
ECHO_LM_STUDIO_URL=http://localhost:1234/v1

# Provider: "lmstudio" (default) or "copilot"
ECHO_LLM_PROVIDER=lmstudio
```

Everything else has a sensible default.

---

## Full reference

### LLM settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ECHO_LM_STUDIO_URL` | `http://localhost:1234/v1` | Base URL for LM Studio API |
| `ECHO_LLM_MODEL` | `Qwen2.5-7B-Instruct-Q4_K_M` | Model name for chat completions |
| `ECHO_EMBEDDING_MODEL` | `text-embedding-nomic-embed-text-v1.5` | Model name for embeddings |
| `ECHO_LLM_PROVIDER` | `lmstudio` | `lmstudio` or `copilot` |

When `ECHO_LLM_PROVIDER=copilot`, ECHO uses GitHub Copilot (gpt-4o) for completions and HuggingFace `paraphrase-multilingual-mpnet-base-v2` (768-dim) for embeddings.

---

### Memory settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ECHO_DB_PATH` | `data/sqlite/echo.db` | SQLite database file path |
| `ECHO_CHROMA_PATH` | `data/chroma` | ChromaDB data directory |

---

### Pipeline settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ECHO_MAX_WORKSPACE_SLOTS` | `7` | Max items in GlobalWorkspace |
| `ECHO_REFLECTION_TRIGGER_INTERVAL` | `5` | Interactions between reflections |

---

### Scheduler settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ECHO_CONSOLIDATION_INTERVAL_SECONDS` | `3600` | Light consolidation period (1 hour) |
| `ECHO_MEMORY_DECAY_INTERVAL_SECONDS` | `300` | Memory decay run period (5 minutes) |
| `ECHO_CURIOSITY_IDLE_THRESHOLD_SECONDS` | `180` | Idle time before curiosity fires (3 minutes) |

---

### MCP settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ECHO_BRAVE_SEARCH_API_KEY` | `""` | API key for Brave Search MCP tool |

If `ECHO_BRAVE_SEARCH_API_KEY` is empty, the Brave search provider is disabled; other curiosity providers (arXiv, HackerNews, Wikipedia, DuckDuckGo) remain active.

---

## Example `.env.example`

```env
# === LLM ===
ECHO_LM_STUDIO_URL=http://localhost:1234/v1
ECHO_LLM_MODEL=Qwen2.5-7B-Instruct-Q4_K_M
ECHO_EMBEDDING_MODEL=text-embedding-nomic-embed-text-v1.5
ECHO_LLM_PROVIDER=lmstudio   # "lmstudio" | "copilot"

# === Storage ===
ECHO_DB_PATH=data/sqlite/echo.db
ECHO_CHROMA_PATH=data/chroma

# === Pipeline ===
ECHO_MAX_WORKSPACE_SLOTS=7
ECHO_REFLECTION_TRIGGER_INTERVAL=5

# === Schedulers ===
ECHO_CONSOLIDATION_INTERVAL_SECONDS=3600
ECHO_MEMORY_DECAY_INTERVAL_SECONDS=300
ECHO_CURIOSITY_IDLE_THRESHOLD_SECONDS=180

# === MCP ===
ECHO_BRAVE_SEARCH_API_KEY=
```

---

## How settings are loaded

```python
# src/echo/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class EchoConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ECHO_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    lm_studio_url: str = "http://localhost:1234/v1"
    llm_model: str = "Qwen2.5-7B-Instruct-Q4_K_M"
    # ...
```

Settings can also be overridden by real environment variables (they take precedence over `.env`):

```bash
ECHO_MAX_WORKSPACE_SLOTS=10 uv run uvicorn echo.api.server:app
```

---

## Tuning guide

### Reduce LLM latency

Increase workspace slots to provide more context in fewer LLM calls:
```env
ECHO_MAX_WORKSPACE_SLOTS=10
```

Use a smaller/faster model:
```env
ECHO_LLM_MODEL=Qwen2.5-3B-Instruct-Q4_K_M
```

### Reduce memory growth

Increase decay frequency:
```env
ECHO_MEMORY_DECAY_INTERVAL_SECONDS=120
```

### Increase curiosity activity

Reduce the idle threshold:
```env
ECHO_CURIOSITY_IDLE_THRESHOLD_SECONDS=60
```

### Increase reflection depth

Trigger reflections more often:
```env
ECHO_REFLECTION_TRIGGER_INTERVAL=3
```
