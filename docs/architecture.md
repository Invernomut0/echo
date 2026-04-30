# Architecture Overview

ECHO is a layered cognitive architecture. Each layer transforms the incoming signal and enriches it before passing it to the next. This document describes the layers, their relationships, and the data-flow through a single interaction.

---

## Conceptual Diagram

```
┌──────────────────────────────────────────────────────────┐
│                    External Input                         │
│              (user message via HTTP POST)                 │
└───────────────────────┬──────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────┐
│                  Perception Layer                         │
│   • Name extraction    • Interaction ID generation        │
│   • Event bus publish  (EventTopic.USER_INPUT)            │
└───────────────────────┬──────────────────────────────────┘
                        │
              ┌─────────┴──────────┐
              │                    │
              ▼                    ▼
  Episodic Memory              Semantic Memory
  retrieve_similar()           retrieve_similar()
  (ChromaDB + SQLite)          (ChromaDB + SQLite)
              │                    │
              └─────────┬──────────┘
                        │  memories[]
                        ▼
┌──────────────────────────────────────────────────────────┐
│               Global Workspace (7 slots)                  │
│   • Memory injection      • Self-prediction broadcast     │
│   • Learning priors       • Workspace competition         │
└───────────────────────┬──────────────────────────────────┘
                        │  WorkspaceSnapshot
                        ▼
┌──────────────────────────────────────────────────────────┐
│            Internal Cognitive Ecology                     │
│                                                           │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌────────────────┐ │
│  │Analyst  │ │Explorer │ │Skeptic  │ │  Archivist     │ │
│  └────┬────┘ └────┬────┘ └────┬────┘ └───────┬────────┘ │
│  ┌─────────┐ ┌─────────┐     │               │          │
│  │ Social  │ │Planner  │     │               │          │
│  │  Self   │ │         │     │               │          │
│  └────┬────┘ └────┬────┘     │               │          │
│       └────────────┴──────────┴───────────────┘          │
│                         │ deliberations[]                  │
└─────────────────────────┬────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│                   Orchestrator                            │
│   • Applies routing weights to rank agents                │
│   • Calls LLM synthesis with all deliberations            │
│   • Streams response tokens back to caller                │
└───────────────────────┬──────────────────────────────────┘
                        │  streamed response
                        ▼
              ┌──────────────────┐
              │    HTTP Client   │
              └────────┬─────────┘
                       │ (async, fire-and-forget)
                       ▼
┌──────────────────────────────────────────────────────────┐
│              Post-Interaction Pipeline                    │
│                                                           │
│  1. Motivational Scoring  (LLM → drive activation scores) │
│  2. Agent Weight Update   (drive scores → routing weights)│
│  3. Memory Storage        (episodic + semantic)           │
│  4. Reflection            (LLM → beliefs + drive deltas)  │
│  5. Plasticity Adaptation (agent weight fine-tuning)      │
│  6. Learning Engine       (personalization + predictor)   │
│  7. Meta-State Persistence (SQLite append-only snapshot)  │
└──────────────────────────────────────────────────────────┘

Background loops (always running):
  • ConsolidationScheduler  — 5-min light cycle + 12-h REM dream phase
  • DecayScheduler          — exponential memory strength decay (every 5 min)
  • CuriosityEngine         — idle-time autonomous web research
  • StimulusNudge           — proactive injection of findings into pipeline (p = 0.2 + 0.3·arousal)
```

---

## Source Code Layout

```
src/echo/
├── core/               ← Foundation layer
│   ├── config.py           Settings (pydantic-settings, .env)
│   ├── types.py            All shared Pydantic models and enums
│   ├── db.py               SQLAlchemy async engine + ChromaDB collections
│   ├── event_bus.py        In-process async pub/sub
│   ├── llm_client.py       LLM adapter (LM Studio / GitHub Copilot)
│   └── pipeline.py         CognitivePipeline — top-level controller
│
├── memory/             ← Persistence layer
│   ├── episodic.py         ChromaDB + SQLite episodic store
│   ├── semantic.py         ChromaDB + SQLite semantic store
│   ├── autobiographical.py Autobiographical summaries
│   ├── chunker.py          Text chunking for semantic memories
│   ├── decay.py            Exponential decay scheduler
│   └── dream_store.py      DreamEntry persistence
│
├── self_model/         ← Identity layer
│   ├── identity_graph.py   NetworkX DiGraph of IdentityBelief nodes
│   ├── meta_state.py       MetaStateTracker — drives + agent weights
│   ├── self_prediction.py  Predict ECHO's likely response before generation
│   └── echo_md.py          EchoMdManager — self-maintained personality file
│
├── motivation/         ← Drive layer
│   ├── drives.py           DriveScores model + descriptions
│   └── motivational_scorer.py  LLM-based drive activation scoring
│
├── agents/             ← Cognitive ecology
│   ├── base.py             BaseAgent abstract class
│   ├── analyst.py          Logical analysis
│   ├── explorer.py         Novel connections and hypotheses
│   ├── skeptic.py          Critical examination
│   ├── archivist.py        Memory retrieval and curation
│   ├── social_self.py      Emotional awareness and social context
│   ├── planner.py          Action planning
│   └── orchestrator.py     Multi-agent runner + LLM synthesis
│
├── workspace/
│   └── global_workspace.py  Baars GWT implementation (7-slot competition)
│
├── reflection/
│   └── engine.py            Post-interaction LLM introspection
│
├── consolidation/
│   ├── scheduler.py         Dual-heartbeat (5 min + 12 h) scheduler
│   ├── sleep_phase.py       Light consolidation: pattern extraction + pruning
│   ├── dream_phase.py       REM: LLM dream narrative generation
│   ├── weight_evolution.py  Fitness-guided agent weight mutation
│   ├── creative_synthesis.py  Bridge insights from distant memory pairs
│   └── swarm_dream.py       4 parallel dream personas (elitist selection)
│
├── plasticity/
│   └── adapter.py           PlasticityAdapter — drive-to-weight mapping
│
├── learning/
│   ├── engine.py            LearningEngine coordinator
│   ├── personalization.py   EMA-based style + depth adaptation
│   └── predictor.py         EWMA predictive analytics
│
├── curiosity/
│   ├── engine.py            Idle-time autonomous research
│   ├── interest_profile.py  EMA-based user interest tracking + ZPD generation
│   ├── stimulus_queue.py    Ranked findings queue with feedback propagation
│   ├── web_search.py        arXiv / HackerNews / Wikipedia / DuckDuckGo
│   └── mcp_search.py        Brave Search + URL fetch via MCP
│
├── mcp/
│   └── manager.py           MCP server lifecycle + tool registry
│
└── api/
    ├── server.py             FastAPI app factory + lifespan
    ├── schemas.py            API request/response Pydantic models
    └── routers/
        ├── interact.py       POST /api/chat, POST /api/interact (SSE)
        ├── state.py          GET /api/state, GET /api/state/history
        ├── memory.py         GET/DELETE /api/memory/*
        ├── identity.py       GET /api/identity/graph
        ├── consolidation.py  POST /api/consolidation/trigger; GET+POST /api/consolidation/echo-md
        ├── curiosity.py      GET /api/curiosity/activity; POST /api/curiosity/trigger;
        │                     GET /api/curiosity/profile; GET /api/curiosity/findings;
        │                     POST /api/curiosity/feedback; POST /api/curiosity/guide
        ├── setup.py          POST /api/setup (first-run)
        └── mcp.py            GET /api/mcp/tools
```

---

## Data Flow: Single Interaction (detailed)

### 1. HTTP Request → Perception
`POST /api/interact` with `{"message": "...", "history": [...]}` arrives at `interact_stream()`.  
A unique `interaction_id` (UUID4) is generated. A `CognitiveEvent` with topic `USER_INPUT` is published on the event bus. The response is a Server-Sent Events (SSE) stream.

### 2. Parallel Retrieval
Three async tasks run concurrently (via `asyncio.gather`):
- `episodic.retrieve_similar(user_input, n=5)` — semantically similar past interactions
- `semantic.retrieve_similar(user_input, n=5)` — relevant stored facts
- `predict_response(user_input, meta_state)` — self-prediction for the expected reply

### 3. Global Workspace Loading
Memories are pushed into the 7-slot workspace with `load_memories()`. The self-prediction and learning priors are broadcast as additional workspace items. Items compete by `salience × (1 + routing_weight × 0.2)` — lowest-scoring items are evicted when all 7 slots are full.

### 4. Agent Deliberation
The `Orchestrator` runs all 6 specialist agents in parallel. Each agent receives the workspace snapshot and produces a `deliberation` string. The orchestrator reads `meta_state.agent_weights` to sort agents by priority before synthesis.

### 5. LLM Synthesis
The orchestrator sends a synthesis prompt to the LLM containing all deliberations, retrieved memories, and the user message. The response is streamed token-by-token back to the client as SSE `data: {"type": "delta", "content": "..."}` events.

### 6. Post-Interaction (async, fire-and-forget)
After the last token is sent, `_post_interact()` runs asynchronously:
1. **Motivational scoring** — LLM evaluates which drives were activated (0–1 per drive).
2. **Agent weight update** — drive scores drive routing weight deltas via `_DRIVE_AGENT_MAP`.
3. **Memory storage** — interaction stored as episodic memory; key facts extracted to semantic memory.
4. **Interest profile inference** — `interest_profile.infer_from_memories()` extracts topics from the interaction via LLM and updates EMA affinity scores.
5. **Implicit stimulus feedback** — if a stimulus was injected and `mem.self_relevance > 0.7`, a positive feedback score (0.8) is recorded in the stimulus queue.
6. **Reflection** — LLM produces insights, new identity beliefs, and drive adjustments.
7. **Plasticity** — `PlasticityAdapter.apply()` fine-tunes weights from reflection insights + prediction error.
8. **Learning** — `LearningEngine.observe()` updates personalization style and prediction priors.
7. **Persistence** — full `MetaState` snapshot appended to SQLite.

### 7. Background Loops
Running continuously in separate asyncio tasks:
- **Light heartbeat** (every 5 min): promotes strong memories, marks dormant ones, extracts patterns.
- **Deep heartbeat** (every 12 h): runs full light consolidation + REM dream phase + weight evolution + creative synthesis + swarm dream.
- **Decay** (every 5 min): applies `I(t) = I₀ · e^(−λt)` to all memory strengths.
- **Curiosity** (after 3 min idle): searches arXiv, HackerNews, Wikipedia, and Brave for topics extracted from recent memories; stores findings as semantic memories.

---

## Persistence

| Data | Backend | Location |
|------|---------|----------|
| Episodic memories | SQLite + ChromaDB | `data/sqlite/echo.db` + `data/chroma/` |
| Semantic memories | SQLite + ChromaDB | same |
| MetaState history | SQLite | `meta_states` table (append-only) |
| Identity beliefs | SQLite | `identity_beliefs` + `belief_edges` tables |
| Dream entries | SQLite | `dream_entries` table |
| Personalization state | SQLite | `personalization_state` table |

---

## Event Bus

ECHO uses an in-process async publish/subscribe bus (`echo.core.event_bus`). Topics are defined in `EventTopic` enum:

| Topic | Emitted by | Consumed by |
|-------|-----------|-------------|
| `USER_INPUT` | pipeline | WebSocket `/ws/events` clients |
| `AGENT_RESPONSE` | orchestrator | WebSocket clients |
| `WORKSPACE_UPDATE` | global_workspace | WebSocket clients |
| `MEMORY_STORE` | episodic/semantic stores | WebSocket clients |
| `BELIEF_UPDATE` | identity_graph | WebSocket clients |
| `DRIVE_UPDATE` | meta_state | WebSocket clients |
| `REFLECTION_COMPLETE` | reflection engine | WebSocket clients |
| `CONSOLIDATION_COMPLETE` | consolidation scheduler | WebSocket clients |
| `META_STATE_UPDATE` | meta_state tracker | WebSocket clients |
| `PLASTICITY_UPDATE` | plasticity adapter | WebSocket clients |

The WebSocket endpoint `ws://localhost:8000/ws/events` forwards all bus events to connected browser clients in real time.
