# PROJECT ECHO — Documentation

**ECHO** is a persistent, self-modifying cognitive architecture built on top of a Large Language Model. It is not a chatbot, not a traditional RAG pipeline, and not a stateless assistant. It is an architecture designed to simulate proto-conscious behaviour through continuous adaptation, autobiographical memory, identity formation, and motivational dynamics.

> Version 0.4.0 · Python 3.12 · FastAPI · React 18 + TypeScript

---

## Table of Contents

### Architecture
- [High-Level Architecture](architecture.md) — system overview, data-flow diagram, module map

### Modules
| # | Module | File |
|---|--------|------|
| 01 | Cognitive Core (LLM pipeline) | [modules/01-cognitive-core.md](modules/01-cognitive-core.md) |
| 02 | Memory System | [modules/02-memory-system.md](modules/02-memory-system.md) |
| 03 | Self-Model (Identity Graph + MetaState) | [modules/03-self-model.md](modules/03-self-model.md) |
| 04 | Motivational System | [modules/04-motivational-system.md](modules/04-motivational-system.md) |
| 05 | Cognitive Ecology (Agents) | [modules/05-agents.md](modules/05-agents.md) |
| 06 | Global Workspace | [modules/06-global-workspace.md](modules/06-global-workspace.md) |
| 07 | Reflection Engine | [modules/07-reflection-engine.md](modules/07-reflection-engine.md) |
| 08 | Consolidation & Dream Phase | [modules/08-consolidation.md](modules/08-consolidation.md) |
| 09 | Plasticity Adapter | [modules/09-plasticity.md](modules/09-plasticity.md) |
| 10 | Deep Real-Time Learning | [modules/10-learning.md](modules/10-learning.md) |
| 11 | Curiosity Engine | [modules/11-curiosity.md](modules/11-curiosity.md) |
| 12 | Co-Evolutionary Cognitive Partner | [modules/12-co-evolution.md](modules/12-co-evolution.md) |

### API Reference
- [REST API](api/rest-api.md) — all HTTP endpoints with request/response schemas
- [Data Models](api/data-models.md) — all Pydantic types, enums, and their fields

### Development
- [Setup & Installation](development/setup.md) — requirements, env vars, first run
- [Configuration](development/configuration.md) — all settings and `.env` variables
- [Testing](development/testing.md) — test suite structure and how to run tests

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/Invernomut0/echo.git
cd echo
cp .env.example .env          # configure GITHUB_TOKEN and other vars
uv sync --extra dev

# Start Ollama with the embedding model
ollama pull nomic-embed-text

# Run backend
uv run uvicorn echo.api.server:app --host 0.0.0.0 --port 8000

# Open the UI
open http://localhost:8000
```

> **Note:** ECHO uses **GitHub Copilot** as the LLM backend (chat + streaming) and **Ollama** for embeddings only. LM Studio is no longer required.

---

## What Makes ECHO Different

| Traditional LLM | ECHO |
|-----------------|------|
| Stateless — forgets on session end | **Persistent** — memories survive across restarts |
| Frozen weights | **Adaptive routing** — agent weights evolve with every interaction |
| No internal motivation | **Drive system** — curiosity, coherence, stability, competence, compression |
| Single monolithic response | **Multi-agent deliberation** — 6 specialists + orchestrator |
| No self-model | **Identity graph** — beliefs about self accumulate and contradict each other |
| No sleep | **Consolidation cycle** — 5-min light cycle + 12-hour REM dream phase |

---

## Implementation Status

| Module | Status |
|--------|--------|
| Cognitive Core (LLM + pipeline) | ✅ Complete |
| Episodic Memory (ChromaDB + SQLite) | ✅ Complete |
| Semantic Memory | ✅ Complete |
| Autobiographical Memory | ✅ Complete |
| Identity Belief Graph | ✅ Complete |
| MetaState + Drive System | ✅ Complete |
| Agent Ecology (6 agents + orchestrator) | ✅ Complete |
| Agent Routing Weights (dynamic update) | ✅ Complete (fixed in v0.4.0) |
| Global Workspace | ✅ Complete |
| Reflection Engine | ✅ Complete |
| Consolidation Scheduler (light + REM) | ✅ Complete |
| Dream Phase | ✅ Complete |
| Plasticity Adapter | ✅ Complete |
| Memory Decay | ✅ Complete |
| Self-Prediction | ✅ Complete |
| Deep Real-Time Learning (module 16) | ✅ Complete |
| Curiosity Engine | ✅ Complete |
| Co-Evolutionary Cognitive Partner | ✅ Complete |
| Self-Maintained Personality File (echo.md) | ✅ Complete |
| MCP tool integration | ✅ Complete |
| REST API + WebSocket events | ✅ Complete |
| React frontend | ✅ Complete |
