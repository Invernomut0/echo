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
              ┌─────────┼──────────┐
              │         │          │
              ▼         ▼          ▼
  Episodic Memory  Semantic Memory  Associative Walk
  retrieve_similar() retrieve_similar() random_walk_retrieve()
  (ChromaDB+SQLite) (ChromaDB+SQLite)  (causal link traversal)
              │         │          │
              └─────────┼──────────┘
                        │  memories[]
                        ▼
┌──────────────────────────────────────────────────────────┐
│               Global Workspace (7 slots)                  │
│   • Memory injection      • Self-prediction broadcast     │
│   • Learning priors       • Drive behavior directives     │
│   • Curiosity stimuli     • Workspace competition         │
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
│   • Injects metacognitive self-model into system prompt   │
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
│  3. Adaptive Drive Dynamics (momentum + conflict resolve) │
│  4. Memory Storage        (episodic + semantic)           │
│  5. Learning Engine:                                      │
│     a. Meta-Learning      (quality tracking, adaptive α)  │
│     b. Self-Evaluation    (engagement, competence map)    │
│     c. Growth Tracker     (stagnation detection)          │
│  6. Reflection            (LLM → beliefs + drive deltas)  │
│  7. Metacognition Update  (absorb reflection insights)    │
│  8. Plasticity Adaptation (agent weight fine-tuning)      │
│  9. Meta-State Persistence (SQLite append-only snapshot)  │
└──────────────────────────────────────────────────────────┘

Background loops (always running):
  • ConsolidationScheduler  — 5-min light cycle + 12-h REM dream phase
  • DecayScheduler          — gentle memory decay (every 1 hour, days-based)
  • CuriosityEngine         — idle-time autonomous web research
  • InitiativeEngine        — proactive insights, questions, goal milestones
  • StimulusNudge           — injection of findings (p = 0.2 + 0.3·arousal)
  • AssociativeMemory       — cross-pollination + temporal clustering (REM)
  • MetacognitiveReview     — deep self-model update (REM)
  • GrowthReport            — periodic trajectory assessment (REM)
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
│   ├── llm_client.py       LLM adapter (GitHub Copilot + Ollama embed)
│   └── pipeline.py         CognitivePipeline — top-level controller
│
├── memory/             ← Persistence layer
│   ├── episodic.py         ChromaDB + SQLite episodic store
│   ├── semantic.py         ChromaDB + SQLite semantic store
│   ├── associative.py      Random walk + cross-pollination + temporal clustering
│   ├── autobiographical.py Autobiographical summaries
│   ├── chunker.py          Text chunking for semantic memories
│   ├── decay.py            Gentle exponential decay scheduler (days-based)
│   ├── goals.py            GoalStore — persistent autonomous goal tracking
│   ├── wiki.py             LLM Wiki — structured knowledge pages
│   └── dream_store.py      DreamEntry persistence
│
├── self_model/         ← Identity layer
│   ├── identity_graph.py   NetworkX DiGraph of IdentityBelief nodes
│   ├── meta_state.py       MetaStateTracker — drives + agent weights
│   ├── self_prediction.py  Predict ECHO's likely response before generation
│   ├── metacognition.py    Metacognitive self-model (functional self-awareness)
│   └── echo_md.py          EchoMdManager — self-maintained personality file
│
├── motivation/         ← Drive layer
│   ├── drives.py           DriveScores model + descriptions
│   ├── motivational_scorer.py  LLM-based drive activation scoring
│   └── adaptive_drives.py  Momentum, conflict resolution, drive→goal bridge
│
├── agents/             ← Cognitive ecology
│   ├── base.py             BaseAgent abstract class
│   ├── analyst.py          Logical analysis
│   ├── explorer.py         Novel connections and hypotheses
│   ├── skeptic.py          Critical examination
│   ├── archivist.py        Memory retrieval and curation
│   ├── social_self.py      Emotional awareness and social context
│   ├── planner.py          Action planning
│   └── orchestrator.py     Multi-agent runner + LLM synthesis + metacognition injection
│
├── workspace/
│   └── global_workspace.py  Baars GWT implementation (7-slot competition)
│
├── reflection/
│   └── engine.py            Post-interaction LLM introspection
│
├── consolidation/
│   ├── scheduler.py         Dual-heartbeat scheduler + initiative + growth + associative
│   ├── sleep_phase.py       Light consolidation: pattern extraction + pruning
│   ├── dream_phase.py       REM: LLM dream narrative generation
│   ├── weight_evolution.py  Fitness-guided agent weight mutation
│   ├── creative_synthesis.py  Bridge insights from distant memory pairs
│   └── swarm_dream.py       4 parallel dream personas (elitist selection)
│
├── plasticity/
│   └── adapter.py           PlasticityAdapter — drive-to-weight mapping
│
├── learning/           ← Deep learning & self-improvement
│   ├── engine.py            LearningEngine coordinator (all sub-modules)
│   ├── personalization.py   EMA-based style + depth adaptation (adaptive α)
│   ├── predictor.py         EWMA predictive analytics
│   ├── meta_learning.py     Meta-learning: tracks how ECHO learns best
│   ├── self_evaluation.py   Skill assessment + competence map + engagement
│   └── growth_tracker.py    Long-term improvement trajectory + shake-ups
│
├── initiative/         ← Proactive communication
│   └── engine.py            Insights, questions, milestones, reflections → Telegram
│
├── curiosity/
│   ├── engine.py            Idle-time autonomous research + goal management
│   ├── interest_profile.py  EMA-based user interest tracking + ZPD generation
│   ├── stimulus_queue.py    Ranked findings queue with feedback propagation
│   ├── web_search.py        arXiv / HackerNews / Wikipedia / DuckDuckGo
│   └── mcp_search.py        Brave Search + URL fetch via MCP
│
├── integrations/
│   ├── telegram_bot.py      Telegram bot bridge (inbound)
│   └── telegram_notify.py   Outbound notifications (goals, initiatives)
│
├── mcp/
│   └── __init__.py          MCP server lifecycle + tool registry
│
└── api/
    ├── server.py             FastAPI app factory + lifespan
    ├── schemas.py            API request/response Pydantic models
    └── routers/
        ├── interact.py       POST /api/chat, POST /api/interact (SSE)
        ├── state.py          GET /api/state, GET /api/state/history
        ├── memory.py         GET/DELETE /api/memory/*
        ├── identity.py       GET /api/identity/graph
        ├── goals.py          GET/POST /api/goals/*
        ├── consolidation.py  POST /api/consolidation/trigger
        ├── curiosity.py      GET /api/curiosity/activity; POST /api/curiosity/trigger
        ├── wiki.py           GET/POST /api/wiki/*
        ├── setup.py          POST /api/setup (first-run)
        └── mcp.py            GET /api/mcp/tools
```

---

## Data Flow: Single Interaction (detailed)

### 1. HTTP Request → Perception
`POST /api/interact` with `{"message": "...", "history": [...]}` arrives at `interact_stream()`.
A unique `interaction_id` (UUID4) is generated. A `CognitiveEvent` with topic `USER_INPUT` is published on the event bus.

### 2. Parallel Retrieval
Four async tasks run concurrently:
- `episodic.retrieve_similar(user_input, n=5)` — semantically similar past interactions
- `semantic.retrieve_similar(user_input, n=5)` — relevant stored facts
- `predict_response(user_input, meta_state)` — self-prediction
- After retrieval: `associative_memory.random_walk_retrieve()` — follow causal links for lateral connections

### 3. Global Workspace Loading
Memories (vector + associative) are pushed into the 7-slot workspace. Self-prediction, learning priors, drive behavior directives, and curiosity stimuli compete for workspace slots by `salience × (1 + routing_weight × 0.2)`.

### 4. Agent Deliberation
The `Orchestrator` runs all 6 specialist agents in parallel. Each receives the workspace snapshot and produces a deliberation. Agents are sorted by routing weight for synthesis (primacy bias).

### 5. LLM Synthesis
The orchestrator builds a system prompt that includes:
- Base ECHO identity and rules
- **Metacognitive self-model** (ECHO reads its own cognitive state)
- Available MCP tools (if connected)

Then sends all deliberations + memories + wiki context for synthesis.

### 6. Post-Interaction (async, fire-and-forget)
1. **Motivational scoring** — LLM evaluates drive activations
2. **Agent weight update** — drive scores → routing weight deltas
3. **Adaptive Drive Dynamics** — momentum, conflict resolution, drive→goal bridge
4. **Learning Engine** — meta-learning (quality, adaptive α) + self-evaluation (engagement, competence) + growth tracker (trajectory, stagnation)
5. **Memory storage** — episodic + semantic + causal links
6. **Reflection** (every N turns) — insights, beliefs, drive adjustments
7. **Metacognition update** — absorb reflection insights into self-model
8. **Plasticity** — fine-tune weights from insights + prediction error
9. **Persistence** — MetaState snapshot to SQLite

### 7. Background Loops

| Loop | Interval | Actions |
|------|----------|---------|
| Light Heartbeat | 5 min | Consolidation + curiosity + initiative + memory cleanup |
| Deep/REM Heartbeat | 12 h | Full consolidation + dream + cross-pollination + temporal clustering + growth report + metacognitive review |
| Decay | 1 hour | Gentle exponential decay (days-based, access-protected) |

---

## Persistence

| Data | Backend | Table/Collection |
|------|---------|------------------|
| Episodic memories | SQLite + ChromaDB | `episodic_memories` + `episodic_memory` collection |
| Semantic memories | SQLite + ChromaDB | `semantic_memories` + `semantic_memory` collection |
| MetaState history | SQLite | `meta_states` (append-only) |
| Identity beliefs | SQLite | `identity_beliefs` + `belief_edges` |
| Dream entries | SQLite | `dream_entries` |
| Personalization | SQLite | `personalization_state` |
| Meta-learning observations | SQLite | `meta_learning_observations` |
| Meta-learning insights | SQLite | `meta_insights` |
| Skill assessments | SQLite | `skill_assessments` |
| Competence map | SQLite | `competence_map` |
| Growth reports | SQLite | `growth_reports` |
| Memory associations | SQLite | `memory_associations` |
| Cognitive model | SQLite | `cognitive_model` |
| Goals | SQLite | `goals` + `goal_actions` |
| Initiative log | SQLite | `initiative_log` |
| Interest profile | SQLite | `interest_profile` |

---

## Memory Decay Model

ECHO uses a **gentle, use-based** decay system:

```
I(t) = I₀ · e^(−λ · Δt_days)
```

Where:
- `λ = (1 - salience) × 0.005` — very small; high-salience memories are nearly permanent
- `Δt` is measured in **days** (not hours)
- Memories accessed within the last **7 days** are fully protected (zero decay)
- Each retrieval **reinforces** strength by 20% toward 1.0
- `access_count` provides additional decay resistance

**Result**: A medium-salience memory unused for 6 months retains ~68% strength. Only memories unused for 2+ years approach pruning threshold.

---

## Autonomous Self-Improvement Loop

ECHO continuously evaluates and improves itself:

```
[Each Interaction]
    → Meta-Learning: classify type, compute adaptive α
    → Self-Evaluation: engagement detection, competence tracking
    → Growth Tracker: rolling metrics, stagnation check

[Every 50 Interactions]
    → Full Skill Assessment (LLM): accuracy, helpfulness, depth, empathy, creativity
    → Competence Map update per domain

[Every 200 Interactions (if stagnant)]
    → SHAKE-UP: boost curiosity, create self-improvement goals

[Light Consolidation — every 5 min]
    → Proactive Initiative: insights, questions, goal milestones → Telegram

[Deep Sleep — every 12h]
    → Cross-pollination: find unexpected connections between distant memories
    → Temporal clustering: identify recurring themes across days
    → Growth Report: trajectory summary stored as semantic memory
    → Metacognitive Deep Review: LLM re-evaluates self-model from all learning data
```
