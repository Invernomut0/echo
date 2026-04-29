# Development Setup

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | ≥ 3.12 | Backend runtime |
| [uv](https://docs.astral.sh/uv/) | latest | Python package manager |
| Node.js | ≥ 20 | Frontend runtime |
| npm | ≥ 10 | Frontend package manager |
| [LM Studio](https://lmstudio.ai/) | ≥ 0.3 | Local LLM inference |
| Git | any | Version control |

---

## Clone and configure

```bash
git clone https://github.com/Invernomut0/echo.git
cd echo

# Copy the example environment file
cp .env.example .env
```

Edit `.env` to match your setup. At minimum, verify the LM Studio URL:

```env
ECHO_LM_STUDIO_URL=http://localhost:1234/v1
```

All other defaults work out of the box. See [Configuration](./configuration.md) for the full list.

---

## Backend

### Install dependencies

```bash
uv sync --extra dev
```

This creates a virtual environment at `.venv/` and installs all runtime + dev dependencies.

### Start in development mode (hot reload)

```bash
uv run uvicorn echo.api.server:app --reload
```

Server listens on `http://localhost:8000`. Code changes restart the server automatically.

### Start in production mode

```bash
uv run uvicorn echo.api.server:app --host 0.0.0.0 --port 8000
```

---

## Frontend

### Install dependencies

```bash
cd frontend
npm install
```

### Start development server (HMR)

```bash
npm run dev
```

Frontend listens on `http://localhost:5173` with Hot Module Replacement. API requests are proxied to `http://localhost:8000`.

### Build for production

```bash
npm run build
```

Output is placed in `frontend/dist/`. The FastAPI server can serve this directory as static files.

---

## LM Studio Setup

ECHO requires two models loaded simultaneously in LM Studio:

| Model | Purpose | Endpoint |
|-------|---------|---------|
| `Qwen2.5-7B-Instruct-Q4_K_M` | Chat completions | `/v1/chat/completions` |
| `nomic-embed-text-v1.5` | Embeddings | `/v1/embeddings` |

1. Download both models from the LM Studio model catalogue
2. Load the completion model on port `1234`
3. Load the embedding model on the same server

Verify the server is running:

```bash
curl http://localhost:1234/v1/models
```

### Alternative: Copilot provider

If LM Studio is not available, set `ECHO_LLM_PROVIDER=copilot` in `.env` to use GitHub Copilot (gpt-4o) for completions. Embeddings will fall back to HuggingFace (`paraphrase-multilingual-mpnet-base-v2`, 768-dim).

---

## Data directories

ECHO creates these automatically on first run:

```
data/
├── sqlite/
│   └── echo.db        # SQLite relational store
└── chroma/            # ChromaDB vector store
```

To reset ECHO's memory entirely:

```bash
rm -rf data/
```

---

## Verify the installation

1. Start LM Studio with both models loaded
2. Start the backend: `uv run uvicorn echo.api.server:app --reload`
3. Check health: `curl http://localhost:8000/health`
4. Start the frontend: `cd frontend && npm run dev`
5. Open `http://localhost:5173`

Expected health response:

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

## Project layout

```
echo/
├── src/echo/                  # Python package
│   ├── api/                   # FastAPI routers and server
│   │   └── routers/
│   ├── core/                  # Pipeline, config, shared types
│   ├── memory/                # Episodic, semantic, autobiographical stores
│   ├── identity/              # Belief graph (NetworkX)
│   ├── agents/                # Multi-agent orchestra
│   ├── workspace/             # GlobalWorkspace (WTA)
│   ├── reflection/            # ReflectionEngine
│   ├── consolidation/         # Consolidation + dream schedulers
│   ├── plasticity/            # PlasticityAdapter
│   ├── learning/              # LearningEngine + PersonalizationState
│   └── curiosity/             # CuriosityEngine
├── frontend/                  # React + TypeScript + Vite
│   ├── src/
│   │   ├── components/
│   │   ├── hooks/
│   │   └── types/
│   └── dist/                  # Built output
├── tests/
│   ├── unit/                  # 26 tests, no LM Studio required
│   ├── integration/           # requires LM Studio
│   └── e2e/                   # requires full stack
├── data/                      # runtime data (git-ignored)
├── docs/                      # this documentation
├── pyproject.toml
├── .env.example
└── PROJECT_ECHO.md            # project vision document
```
