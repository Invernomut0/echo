# ECHO — Persistent Self-Modifying Cognitive Architecture

> NOT a chatbot. An architecture that persists, evolves, and knows itself.

**Version:** 0.5.7 · **Last updated:** 2026-07-13

---

## What is ECHO?

ECHO is a multi-agent cognitive system that simulates proto-conscious behaviour through persistence, self-reflection, and recursive self-modelling. It is not stateless: every interaction leaves a trace, reshapes drives, updates identity beliefs, and feeds an ever-growing autobiographical memory.

---

## Architecture Overview

| Layer | Module | Description |
|-------|--------|-------------|
| Perception | `pipeline.py` | SSE streaming + sync pipeline, workspace loader, stimulus nudge |
| Memory | `episodic`, `semantic`, `autobiographical` | ChromaDB + SQLite, exponential decay |
| Identity | `identity_graph`, `meta_state` | NetworkX DiGraph, drive tracking, self-prediction |
| Agents | `analyst`, `explorer`, `skeptic`, `archivist`, `social_self`, `planner` | 6 specialist agents competing in Global Workspace |
| Workspace | `global_workspace` | Baars-inspired broadcast competition, 7 salience slots |
| Reflection | `reflection/engine` | Post-interaction LLM reflection → beliefs + drive adjustments |
| Consolidation | `consolidation/scheduler` | Light (hourly) + deep (nightly) sleep phases |
| Curiosity | `curiosity/engine` | Autonomous idle-time knowledge acquisition |
| Co-Evolution | `curiosity/interest_profile`, `curiosity/stimulus_queue` | User interest tracking + proactive stimulus injection |
| Self-Model | `self_model/echo_md` | ECHO's self-maintained personality file (`data/echo.md`) |
| Learning | `learning/` | Plasticity adapter, LLM wiki, personalisation priors |
| API | `api/routers/` | FastAPI, SSE, WebSocket |
| Frontend | `frontend/` | React 18 + TypeScript + Vite, dark theme |

---

## Key Features

### 🧠 Persistent Cognitive Architecture
Six specialised agents (Analyst, Explorer, Skeptic, Archivist, Social-Self, Planner) compete via salience in a Global Workspace. The winning coalition shapes every response.

### 💾 Multi-Layer Memory
- **Episodic**: ChromaDB, 768-dim cosine HNSW, exponential decay (`λ = 0.1/86400`)
- **Semantic**: Named facts, identity anchors
- **Autobiographical**: Long-arc narrative compressed by the consolidation scheduler

### 🆔 Identity Belief Graph
NetworkX DiGraph of identity beliefs with coherence scoring. Contradictory beliefs trigger drive spikes, which influence agent routing weights.

### 🎯 Drive System
Five intrinsic drives tracked as continuous scalars:

```
M = 0.25·coherence + 0.20·curiosity + 0.20·stability + 0.20·competence + 0.15·compression
```

### 🔭 Autonomous Curiosity Engine
ECHO researches topics autonomously during idle time. Every 4 cycles a **ZPD (Zone of Proximal Development)** cycle runs — it expands into adjacent, not-yet-explored topics.

### 🤝 Co-Evolutionary Cognitive Partner *(new in 0.4.0)*
ECHO builds a **user interest profile** via EMA-weighted topic affinity and injects relevant findings proactively during conversation:

- `UserInterestProfile` — EMA (α=0.10) per-topic affinity, up to 100 topics, ZPD expansion via LLM
- `StimulusQueue` — ranked findings queue; top stimuli are injected into the workspace with probability `p = 0.2 + 0.3 · arousal`
- Implicit feedback loop: when a stimulus-prompted memory has `self_relevance > 0.7`, positive feedback is recorded automatically
- Frontend panel: **Interest Profile** (affinity bars, exclude), **ZPD Zone** (explore→), **Pending Findings** (star rating)

### 📝 Self-Maintained Personality File *(new in 0.3.0)*
`data/echo.md` is written and updated by ECHO itself after every consolidation cycle. It reflects ECHO's current self-understanding — mood, values, tendencies — in natural language.

### 📚 LLM Wiki
Persistent Markdown knowledge base that ECHO builds and queries during interactions.

### 🎨 Personalisation
ECHO tracks verbosity, topic depth, and recall frequency preferences and adapts its response style over time.

---

## Requirements

- Python ≥ 3.12 (via `uv`)
- Node.js ≥ 20.19
- **LLM provider** — one of:
  - **OpenCode** `opencode.ai` — recommended (big-pickle default, no local GPU needed)
  - **OpenRouter** `openrouter.ai` — 300+ models via single API key
  - **LM Studio** — local inference, OpenAI-compatible
  - **Ollama** — local inference
  - **OpenAI** / **Groq** / **Anthropic** / **GitHub Copilot**
- Ollama running locally on port 11434 with `nomic-embed-text` for embeddings (optional — HuggingFace fallback available)

---

## Setup

```bash
# 1. Clone
git clone https://github.com/Invernomut0/echo.git
cd echo

# 2. Backend
cp .env.example .env     # configure GITHUB_TOKEN and other vars
uv sync --extra dev

# 3. Embeddings (Ollama)
ollama pull nomic-embed-text

# 4. Frontend
cd frontend && npm install && npm run build && cd ..
```

---

## Running

```bash
# Start the backend
uv run uvicorn echo.api.server:app --host 0.0.0.0 --port 8000

# Open http://localhost:8000
```

### Telegram Bot (optional)

ECHO can also interact with users through a Telegram bot (long polling).

1. Create a bot with `@BotFather` and copy the token
2. Configure these vars in `.env`:

```env
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=<your_bot_token>
# Optional hardening: allow only selected chats
TELEGRAM_ALLOWED_CHAT_IDS=[123456789]
# Optional: disable goal-completion notifications
TELEGRAM_GOAL_NOTIFICATIONS_ENABLED=true
```

3. Start ECHO normally (`uv run uvicorn echo.api.server:app ...`)

When enabled, the Telegram bridge starts automatically with the API lifespan
and routes each incoming message through `pipeline.interact`.

Additionally, when a goal is marked `achieved` (from API or autonomous curiosity
cycle), ECHO now:

- consolidates the full resolution (goal, why chosen, findings, solution) into semantic memory,
- sends a Telegram summary with: **goal**, **why it was chosen**, **solution summary**.

## Development (hot-reload)

```bash
# Terminal 1 — backend with reload
uv run uvicorn echo.api.server:app --reload

# Terminal 2 — Vite dev server (proxies /api → :8000)
cd frontend && npm run dev
```

---

## Testing

```bash
uv run pytest tests/unit/           # unit tests, no LLM needed
uv run pytest tests/integration/    # requires Ollama + GitHub Copilot
uv run pytest tests/e2e/            # end-to-end
```

---

## Project Structure

```
src/echo/
  core/           config, types, event_bus, llm_client, db, pipeline
  memory/         episodic, semantic, autobiographical, decay, wiki
  self_model/     identity_graph, meta_state, self_prediction, echo_md
  motivation/     drives, motivational_scorer
  agents/         analyst, explorer, skeptic, archivist, social_self, planner, orchestrator
  workspace/      global_workspace
  reflection/     engine
  consolidation/  sleep_phase, scheduler
  curiosity/      engine, interest_profile, stimulus_queue        ← co-evolution
  plasticity/     adapter
  learning/       personalisation, priors
  api/            schemas, routers/, server

frontend/src/
  components/     ChatPanel, DriveChart, DriveHistory, IdentityGraph,
                  MemoryPanel, ConsolidationPanel, CuriosityPanel,
                  EchoMdPanel
  hooks.ts        useCuriosityProfile, useDriveHistory, …
  api.ts          typed wrappers for all REST endpoints

data/
  chroma/         vector store (gitignored)
  sqlite/echo.db  relational store (gitignored)
  echo.md         ECHO's self-maintained personality file (gitignored)
```

---

## API Reference

### Core

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Synchronous chat |
| POST | `/api/interact` | SSE streaming interaction |
| GET | `/api/state` | Current meta-state + stats |
| GET | `/api/state/history` | Drive score history |
| WS | `/ws/events` | Real-time cognitive event stream |
| GET | `/health` | Health check |

### Memory

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/memory` | Recent memories |
| GET | `/api/memory/search/{query}` | Semantic search |
| GET | `/api/identity/graph` | D3-ready belief graph |

### Curiosity

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/curiosity/activity` | Cycle history + stats |
| POST | `/api/curiosity/trigger` | Manual curiosity cycle |
| GET | `/api/curiosity/profile` | User interest profile + ZPD topics |
| GET | `/api/curiosity/findings` | Pending stimuli queue |
| GET | `/api/curiosity/findings/all` | All stimuli (history) |
| POST | `/api/curiosity/feedback` | Rate a finding `{stimulus_id, score: 0–1}` |
| POST | `/api/curiosity/guide` | Guide topics `{preferred: [], excluded: []}` |

### Consolidation & Self-Model

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/consolidation/trigger` | Manual consolidation |
| GET | `/api/consolidation/echo-md` | Read ECHO's personality file |
| POST | `/api/consolidation/echo-md/review` | Manual personality review |

---

## Key Formulas

**Salience**
```
s = 0.3·importance + 0.2·novelty + 0.3·self_relevance + 0.2·emotional_weight
```

**Memory Decay**
```
I(t) = I₀ · e^(−λ·Δt)     λ = 0.1 / 86400  (~10 days half-life)
```

**Topic Affinity (EMA)**
```
affinity ← (1 − α) · affinity + α · delta     α = 0.10
```

**Stimulus Nudge Probability**
```
p = 0.2 + 0.3 · arousal
```

---

## Changelog

> Full history in [CHANGELOG.md](CHANGELOG.md)

### 0.5.7 — 2026-07-13
- **REM wiki consolidation**: every deep cycle, ECHO finds isolated wiki pages (degree-0 nodes) and appends `## Related [[wikilinks]]` to connect them — knowledge graph grows autonomously
- `SESSION_DUMP.md`: full session context file for LLM continuity across context resets

### 0.5.6 — 2026-07-12
- **Proactive engine acts**: uses tools to actually write files, commit, search wiki/memory during idle — reports what it did, not what it plans
- **Self-code-modification**: ECHO can improve its own source code (auto-validated with ast.parse + rollback on syntax error)
- **echo-workspace + bash MCP servers**: full repo file access and sandboxed shell for ECHO
- **Goal loop fix**: file-creation goals auto-achieved when file exists; goal pursuit writes files instead of web-searching

### 0.5.5 — 2026-07-12
- **Full repo self-modification**: ECHO can now modify any file in its codebase and commit/push autonomously
- **echo-workspace MCP server**: 7 tools for direct file editing, git ops, Python validation
- **All UI labels in English**: IdentityGraph, AnalyticsPanel, WikiGraph, mood/drive labels; tab GRAPH → MEMORY
- **Telegram language fix**: cron tasks now respond in Italian when `ECHO_LANGUAGE=it`

### 0.5.4 — 2026-07-09
- **`ECHO_LANGUAGE=it`**: all generated text (synthesis, proactive, self-mod) in configured language
- **Self-modification fixed**: LLM now outputs JSON instead of narrative; passes full file listing as context
- **Embedding UI**: dedicated section in Setup showing 3-tier chain (Ollama → LM Studio → HuggingFace)
- **Unsloth Studio**: corrected to local server (`localhost:2242`); `opencode-mcp` startup crash fixed

### 0.5.3 — 2026-07-08
- **GitHub wiki auto-sync**: ECHO fetches all `.md` files from a configured repo (default: `Invernomut0/echo`), detects changes by commit SHA, ingests into wiki automatically every 24h
- `📚 WIKI` badge in HeartbeatPanel; config via `WIKI_SYNC_REPO`, `WIKI_SYNC_INTERVAL_H`, `GITHUB_TOKEN`

### 0.5.2 — 2026-07-08
- **Autonomous self-modification**: ECHO can improve its own code, commit + push, notify Telegram, create notes
- **Emotional state UI**: sidebar shows mood emoji (😔→🤩) + drive mini-bars with color intensity
- **Heartbeat fixes**: LIGHT/PROACTIVE/INITIATIVE events now properly logged; 4 import/init bugs fixed
- **Telegram HTML format**: markdown converted to proper HTML bold/italic/code before sending

### 0.5.1 — 2026-07-08
- **Telegram bidirectional**: web chat responses mirrored to Telegram; proactive heartbeat messages (insights/questions) delivered via shared bridge
- **Cerebras provider**: free, ~1800 tok/s, `llama-3.3-70b` default
- **Cerebras rate limiter**: global 1.1s/req token bucket prevents 429 bursts; agent timeout raised to 60s
- **Cron fixes**: `llm_task` prompt fallback from description; `MemoryEntry` JSON serialization bug fixed; `_safe()` serializer on all run records
- **Telegram stability**: `--reload-dir src/echo` prevents bridge kills on DB writes; `_bootstrap()` validates token + clears webhooks

### 0.5.0 — 2026-07-07
- **Multi-provider support**: OpenCode, OpenRouter, LM Studio, Ollama, OpenAI, Groq, Anthropic, GitHub Copilot — switchable via Setup UI without restart
- **Thinking model support**: all `max_tokens` budgets raised 3-4× for models with internal reasoning (gemma-4, QwQ, DeepSeek-R1)
- **Dynamic agent routing**: keyword heuristic selects 2-3 relevant agents per query; simple queries skip all agents; ≥40-word queries get full 6-agent routing
- **Single-pass streaming**: eliminated double synthesis (was ~40s overhead on tool calls); responses stream directly with in-flight tool detection
- **Cognitive improvements**: agent weight floor 0.1→0.3, workspace age penalty, drive conflict evidence accumulation, meta-learning stagnation detection
- **Curiosity fixes**: TTL-based topic cache, robust Brave MCP parser, `force=True` manual trigger, 5-min post-interaction silence
- **Live progress status**: granular step messages during thinking (memory recall → specialist selection → synthesis → tool use)
- **Safety metadata filter**: detects and discards OpenRouter moderation responses, prevents them entering episodic memory

### 0.4.11 — 2026-05-09
- Centralized achieved-goal consolidation in `GoalStore.update_status` (single source of truth across API + curiosity paths)
- Added semantic "Goal Resolution Report" persistence (why chosen, extracted findings, adopted solution, final outcome)
- Added Telegram outbound notifier for goal completion summaries (`goal`, `why chosen`, `solution summary`)
- Added config flag `TELEGRAM_GOAL_NOTIFICATIONS_ENABLED`
- Added unit coverage for goal-resolution payload building, transition-trigger behavior, and notification dispatch

### 0.4.0 — 2026-04-30
- **Co-evolutionary cognitive partner**: `UserInterestProfile`, `StimulusQueue`, ZPD cycles, proactive stimulus injection, implicit feedback loop
- Frontend: CuriosityPanel extended with Interest Profile, ZPD Zone, Pending Findings sections with star-rating feedback
- New event type `EventTopic.CURIOSITY_STIMULUS` on cognitive bus

### 0.3.0
- `echo.md` — ECHO's self-maintained personality file, updated at every consolidation heartbeat
- EchoMdPanel in frontend; manual review endpoint
- LLM migrated from LM Studio → GitHub Copilot

### 0.2.0
- Curiosity Engine (autonomous idle-time knowledge acquisition)
- LLM Wiki (persistent Markdown knowledge base)
- Personalisation priors + style hints
- Pipeline trace for UI visualisation

### 0.1.0
- Initial architecture: 6 agents, Global Workspace, Episodic/Semantic/Autobiographical memory, Drive System, Identity Belief Graph, Reflection Engine, Consolidation Scheduler


## Contributing

Per contribuire a ECHO, consultare il file CONTRIBUTING.md per linee guida, standard di codice e processo di pull request.

