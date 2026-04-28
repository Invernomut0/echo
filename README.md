# ECHO — Persistent Self-Modifying Cognitive Architecture

NOT a chatbot. An architecture.

## Architecture Overview

ECHO is a multi-agent cognitive system built on LM Studio with:

- **6 Specialized Agents** (Analyst, Explorer, Skeptic, Archivist, Social-Self, Planner)
- **Global Workspace** (Baars-inspired broadcast competition, 7 slots)
- **Episodic / Semantic / Autobiographical Memory** (ChromaDB + SQLite, exponential decay)
- **Identity Belief Graph** (NetworkX DiGraph, coherence scoring)
- **Drive System** (coherence, curiosity, stability, competence, compression)
- **Reflection Engine** (post-interaction LLM reflection → beliefs + drive adjustments)
- **Consolidation Scheduler** (memory promotion, pattern extraction)
- **Plasticity Adapter** (agent routing weights adapt over time)
- **React + D3.js + Recharts frontend** (dark OpenClaw theme)

## Requirements

- Python ≥ 3.12 (via `uv`)
- Node.js ≥ 20.19 (for frontend build)
- [LM Studio](https://lmstudio.ai/) running locally on port 1234

## Setup

```bash
# Backend
cp .env.example .env          # Edit as needed
uv sync --extra dev

# Frontend
cd frontend
npm install
npm run build
cd ..
```

## Running

```bash
# Start LM Studio with:
#   - Qwen2.5-7B-Instruct-Q4_K_M  (completions)
#   - nomic-embed-text-v1.5       (embeddings)

uv run uvicorn echo.api.server:app --host 0.0.0.0 --port 8000
# Open http://localhost:8000
```

## Development (hot-reload frontend + backend)

```bash
# Terminal 1
uv run uvicorn echo.api.server:app --reload

# Terminal 2
cd frontend && npm run dev   # Vite dev server on :5173, proxies to :8000
```

## Testing

```bash
uv run pytest tests/unit/           # 26 unit tests, no LM Studio needed
uv run pytest tests/integration/    # Requires LM Studio running
uv run pytest tests/e2e/            # End-to-end, requires LM Studio running
```

## Project Structure

```
src/echo/
  core/           config, types, event_bus, llm_client, db, pipeline
  memory/         episodic, semantic, autobiographical, decay
  self_model/     identity_graph, meta_state, self_prediction
  motivation/     drives, motivational_scorer
  agents/         analyst, explorer, skeptic, archivist, social_self, planner, orchestrator
  workspace/      global_workspace
  reflection/     engine
  consolidation/  sleep_phase, scheduler
  plasticity/     adapter
  api/            schemas, routers (interact, state, memory, identity, consolidation), server

frontend/src/
  components/     ChatPanel, DriveChart, DriveHistory, IdentityGraph,
                  MemoryPanel, ConsolidationPanel
  App.tsx, api.ts, hooks.ts
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Synchronous chat |
| POST | `/api/interact` | SSE streaming interaction |
| GET | `/api/state` | Current meta-state + stats |
| GET | `/api/state/history` | Drive score history |
| GET | `/api/memory` | Recent memories |
| GET | `/api/memory/search/{query}` | Semantic search |
| GET | `/api/identity/graph` | D3-ready belief graph |
| POST | `/api/consolidation/trigger` | Manual consolidation |
| WS | `/ws/events` | Real-time event stream |
| GET | `/health` | Health + LM Studio status |

## Salience Formula

```
s = 0.3·importance + 0.2·novelty + 0.3·self_relevance + 0.2·emotional_weight
```

## Memory Decay

```
I(t) = I₀ · e^(−λ·Δt)
```
where `λ = 0.1 / 86400` (characteristic time ~10 days).

## Total Motivation

```
M = Σ wᵢ · dᵢ
```
with weights: coherence=0.25, curiosity=0.20, stability=0.20, competence=0.20, compression=0.15.
