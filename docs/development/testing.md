# Testing

---

## Test suite structure

```
tests/
├── unit/           # 26 tests, no external services needed
├── integration/    # requires LM Studio running
└── e2e/            # requires full stack (backend + frontend)
```

---

## Running tests

### Unit tests

No LM Studio or database required. All external calls are mocked.

```bash
uv run pytest tests/unit/
```

Run with coverage:

```bash
uv run pytest tests/unit/ --cov=echo --cov-report=term-missing
```

### Integration tests

Require LM Studio running with both models loaded (see [Setup](./setup.md)).

```bash
uv run pytest tests/integration/
```

### End-to-end tests

Require the full stack (backend + frontend) running:

```bash
# Terminal 1
uv run uvicorn echo.api.server:app --reload

# Terminal 2
cd frontend && npm run dev

# Terminal 3
uv run pytest tests/e2e/
```

### All tests

```bash
uv run pytest
```

---

## Unit test coverage (26 tests)

| Module | Tests | What is covered |
|--------|-------|-----------------|
| `core/types.py` | 4 | Salience formula, decay formula, enum values |
| `memory/episodic.py` | 5 | Storage, retrieval, dormancy, chunk query |
| `memory/semantic.py` | 3 | Tag filtering, deduplication |
| `identity/graph.py` | 4 | Belief add/remove, edge creation, coherence score |
| `agents/orchestra.py` | 4 | Weight normalization, dispatch, fallback |
| `workspace/global_workspace.py` | 3 | Slot limit enforcement, WTA competition, eviction |
| `plasticity/adapter.py` | 3 | Weight update math, clamp bounds, decay |

---

## Writing tests

### Unit test conventions

```python
# tests/unit/test_workspace.py
import pytest
from echo.workspace.global_workspace import GlobalWorkspace
from echo.core.config import EchoConfig

@pytest.fixture
def workspace():
    config = EchoConfig(max_workspace_slots=3)
    return GlobalWorkspace(config)

def test_slot_limit_enforced(workspace):
    for i in range(5):
        workspace.add_item(f"item {i}", salience=0.5)
    assert len(workspace.active_items) == 3  # max_slots = 3
```

### Mocking the LLM client

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_reflection_skips_on_llm_failure():
    with patch("echo.reflection.engine.LLMClient") as mock_llm:
        mock_llm.return_value.complete.side_effect = RuntimeError("LLM down")
        # reflection should catch the exception and not raise
        engine = ReflectionEngine(config, ...)
        await engine.reflect()   # should not raise
```

### Testing async code

All async tests require `pytest-asyncio`:

```python
import pytest

@pytest.mark.asyncio
async def test_memory_store():
    store = EpisodicMemoryStore(config)
    await store.startup()
    entry = await store.store("test content")
    assert entry.id is not None
```

---

## Test configuration

`pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.coverage.run]
source = ["src/echo"]
omit = ["*/tests/*", "*/__pycache__/*"]
```

---

## CI pipeline

The GitHub Actions workflow (`.github/workflows/test.yml`) runs the unit test suite on every push:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --extra dev
      - run: uv run pytest tests/unit/ --cov=echo
```

Integration and e2e tests are not run in CI (require LM Studio).

---

## Common issues

### `asyncio.run() cannot be called from a running event loop`

Add `asyncio_mode = "auto"` to `pyproject.toml` or use:

```bash
uv run pytest tests/unit/ -p asyncio
```

### ChromaDB dimension mismatch

If you switch embedding models and the ChromaDB collection already exists with a different dimension, delete `data/chroma/` and restart:

```bash
rm -rf data/chroma/
```

### LM Studio connection refused

Ensure LM Studio is running and the model server is enabled. Check:

```bash
curl http://localhost:1234/v1/models
```
