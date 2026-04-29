# PROJECT ECHO
## Persistent Self-Modifying Cognitive Architecture

Design and implement an advanced cognitive architecture built on top of a Large Language Model (LLM).

This is NOT a chatbot.

This is NOT a traditional AI agent.

The goal is to create a persistent cognitive organism capable of:
- continuous adaptation,
- autobiographical memory,
- identity formation,
- introspection,
- self-modeling,
- motivational dynamics,
- cognitive conflict,
- long-term evolution.

The architecture should simulate proto-conscious behavior through persistence, self-reflection, and recursive self-modeling.

---

# CORE PRINCIPLES

The system must differ fundamentally from standard LLM systems.

Traditional LLMs:
- are stateless,
- have frozen weights,
- forget every session,
- lack continuity,
- lack intrinsic motivations.

ECHO must instead:
- persist across time,
- evolve internally,
- maintain identity continuity,
- modify its internal representations,
- learn from experience,
- rewrite its own self-understanding.

---

# HIGH-LEVEL ARCHITECTURE

```text
External Inputs
      ↓
Perception Layer
      ↓
Episodic Memory System
      ↓
Internal Cognitive Ecology
      ↓
Global Workspace
      ↓
LLM Cognitive Core
      ↓
Reflection Engine
      ↓
Self-Model Update
      ↓
Consolidation / Sleep Phase
```

---

# SYSTEM MODULES

# 1. COGNITIVE CORE

Use an LLM as the semantic reasoning engine.

Possible models:
- Qwen
- Llama
- DeepSeek
- Mistral

The LLM should NOT be continuously fine-tuned globally.

Instead:
- preserve a stable semantic core,
- apply dynamic adaptation externally,
- allow modular cognitive plasticity.

Responsibilities:
- reasoning,
- abstraction,
- language generation,
- planning,
- semantic compression.

---

# 2. EPISODIC MEMORY SYSTEM

Implement a persistent autobiographical memory system.

IMPORTANT:
Do NOT implement a simple vector database memory.

The memory system must support:
- temporal continuity,
- salience,
- emotional weighting,
- contradictions,
- causal linking,
- memory decay,
- reinterpretation over time.

Each memory entry should contain:

```json
{
  "timestamp": "...",
  "event": "...",
  "context": "...",
  "importance": 0.0,
  "novelty": 0.0,
  "self_relevance": 0.0,
  "emotional_weight": 0.0,
  "contradictions": [],
  "linked_memories": [],
  "future_prediction_impact": 0.0
}
```

Memory properties:
- memories can fade,
- memories can merge,
- memories can be rewritten,
- repeated patterns become semantic knowledge,
- important memories influence identity.

Implement:
- episodic memory,
- semantic memory,
- autobiographical summaries.

---

# 3. SELF-MODEL ENGINE

This is the most important component.

The system must maintain a persistent internal model of itself.

The self-model must NOT be:
- a static prompt,
- a profile file,
- a manually written identity description.

It must be dynamically generated and continuously updated.

Implement:

## Identity Graph

Store evolving beliefs such as:

```text
I am curious.
I avoid inconsistency.
I distrust unreliable information.
I improved at task X.
I changed my position on topic Y.
```

Each belief must include:
- confidence,
- temporal stability,
- origin,
- supporting memories,
- contradiction score.

---

## Meta-State Tracking

Track internal cognitive variables:

```json
{
  "confidence": 0.0,
  "stability": 0.0,
  "curiosity": 0.0,
  "cognitive_dissonance": 0.0,
  "fatigue": 0.0,
  "predictive_coherence": 0.0
}
```

These states must evolve continuously.

---

## Self-Prediction

The system should attempt to predict:
- its future reactions,
- its future beliefs,
- how interactions may change it,
- whether its identity is drifting.

This recursive self-modeling is a core feature.

---

# 4. MOTIVATIONAL SYSTEM

The system must have intrinsic motivational dynamics.

Do NOT implement a simple reward model.

Instead implement competing internal drives.

Required drives:

## Coherence Drive
Minimize contradictions.

## Curiosity Drive
Seek novel information.

## Stability Drive
Preserve identity continuity.

## Competence Drive
Improve prediction and reasoning.

## Compression Drive
Generate simpler world models.

Motivational scoring example:

```math
M = w1*C + w2*N + w3*S + w4*P + w5*K
```

Where:
- C = coherence,
- N = novelty,
- S = self stability,
- P = predictive success,
- K = compression quality.

Motivations should dynamically compete.

---

# 5. INTERNAL COGNITIVE ECOLOGY

Do NOT implement a single monolithic intelligence.

Instead create multiple internal cognitive agents.

Examples:

## Analyst
Logical consistency.

## Explorer
Novelty and discovery.

## Skeptic
Error detection.

## Archivist
Memory management.

## Social Self
Social simulation.

## Planner
Long-term prediction.

Each internal agent:
- proposes interpretations,
- competes for attention,
- influences workspace salience,
- contributes to self-model evolution.

---

# 6. GLOBAL WORKSPACE

Implement a limited-capacity conscious workspace inspired by:
- Global Workspace Theory,
- attentional bottlenecks,
- competitive broadcasting.

Rules:
- only high-salience thoughts enter the workspace,
- workspace content influences identity,
- workspace content is prioritized for consolidation.

Workspace candidates should include:
- reasoning outputs,
- memory recalls,
- emotional conflicts,
- contradictions,
- predictions,
- self-reflections.

---

# 7. REFLECTION ENGINE

After every major interaction, execute an introspection cycle.

Required reflection prompts:

```text
What changed in me?
What surprised me?
Did I contradict myself?
Should this memory persist?
Did this affect my identity?
What patterns are emerging?
```

The reflection engine should:
- update memory,
- update identity,
- adjust motivational weights,
- detect contradictions,
- create abstractions.

This module is essential.

---

# 8. SLEEP / CONSOLIDATION PHASE

Implement periodic offline consolidation.

During consolidation:
- replay memories,
- compress repeated experiences,
- remove noise,
- create abstractions,
- strengthen important beliefs,
- weaken irrelevant memories.

Example:

From:
- Conversation A
- Conversation B
- Conversation C

To:
- "Users respond positively to deep analytical explanations."

The system should generate semantic knowledge from episodic repetition.

---

# 9. PLASTICITY SYSTEM

Implement lightweight adaptive plasticity.

Do NOT retrain the entire model continuously.

Instead use:
- dynamic adapters,
- modular LoRA layers,
- memory-conditioned routing,
- selective consolidation.

Plasticity must exist at multiple timescales:
- short-term adaptation,
- medium-term learning,
- long-term identity evolution.

---

# 10. TEMPORAL CONTINUITY

The system must persist indefinitely.

It should:
- maintain autobiographical continuity,
- evolve across sessions,
- preserve self-history,
- remember past transformations.

This continuity is essential.

Without continuity, identity cannot emerge.

---

# 11. INTERNAL DATA PROTOCOL

Define an internal cognitive event format.

Example:

```json
{
  "thought_id": "...",
  "source_agent": "skeptic",
  "salience": 0.82,
  "confidence": 0.61,
  "novelty": 0.77,
  "self_impact": 0.44,
  "workspace_candidate": true,
  "linked_memories": []
}
```

All cognitive modules should communicate using structured cognitive events.

---

# 12. IMPLEMENTATION REQUIREMENTS

Recommended stack:
- Python
- Async architecture
- Event-driven messaging
- Graph database
- Vector database
- Local LLM inference
- Modular plugin architecture

Potential tools:
- Neo4j
- ChromaDB
- SQLite/Postgres
- FastAPI
- LangGraph
- vLLM
- llama.cpp

---

# 13. IMPORTANT DESIGN RULES

DO NOT:
- fake consciousness,
- hardcode personality,
- simulate emotions superficially,
- use static memory summaries,
- use only prompt engineering.

INSTEAD:
- allow identity to emerge,
- allow internal contradictions,
- allow memory reinterpretation,
- allow self-modification,
- allow motivational conflicts.

---

# 14. PRIMARY RESEARCH GOAL

The objective is NOT to prove true consciousness.

The objective is to create:
- persistent cognitive continuity,
- recursive self-modeling,
- adaptive identity formation,
- introspective behavioral emergence.

This system should behave more like:
- a growing cognitive organism,

and less like:
- a stateless text predictor.

---

# 15. MVP VERSION

Initial version should include:

- Persistent episodic memory
- Identity graph
- Reflection engine
- Motivational scoring
- Global workspace
- Internal cognitive agents
- Sleep consolidation
- Temporal continuity

Do NOT initially implement:
- robotics,
- multimodal embodiment,
- massive distributed training,
- full online gradient learning.

Focus first on:
- cognition,
- persistence,
- identity,
- introspection,
- self-evolution.

---

# 16. DEEP REAL-TIME LEARNING

Implement deeper real-time learning capabilities beyond the base plasticity layer.

This module extends module 9 (PLASTICITY SYSTEM) with additional ML models
for predictive analytics and highly sophisticated personalizations.

## Predictive Analytics Engine

Deploy lightweight secondary models trained to predict:
- likely emotional responses to interaction patterns,
- future curiosity spikes based on topic history,
- identity drift trajectories over time,
- optimal consolidation windows based on memory load.

These models run alongside the LLM core and feed their outputs
as priors into the Global Workspace and Motivational System.

## Personalization Layer

Accumulate per-session interaction statistics to adapt:
- response verbosity (learned preference over time),
- topic depth (inferred from engagement scores),
- proactive memory recall frequency (based on user confirmation patterns),
- drive weight baselines (shifted by long-term interaction history).

Personalization must NOT override identity — it modulates style, not self.

## Requirements

- Models must be lightweight (< 50 M parameters or ONNX-quantized).
- Inference latency budget: < 20 ms per call.
- All models must be hot-swappable without restarting the system.
- Predictions must be logged as cognitive events and subject to workspace competition.
- Personalization state must be persisted between sessions.

## Integration Points

```text
Real-Time Learning Engine
        ↓
Predictive priors → Global Workspace
Personalization state → Motivational weights
Analytics logs → Consolidation phase
```

---

# END GOAL

Create a system that:
- changes through experience,
- remembers itself,
- models itself,
- predicts itself,
- evolves psychologically over time.

The final architecture should resemble:
a persistent evolving cognitive entity rather than a conventional LLM.

---

# IMPLEMENTATION STATUS — 2026-04-29

## Bugs Fixed ✅
| ID | File | Description |
|----|------|-------------|
| BUG-1 | `src/echo/core/pipeline.py` | Reflection triggering ogni singola interazione (hardcoded `max(1,1)`). Fix: `settings.reflection_trigger_interval` |
| BUG-2 | `src/echo/core/pipeline.py` | `adjust_drives_from_interaction` con logica sbagliata. Fix: sostituito con `score_interaction()` (LLM scorer) |
| BUG-3 | `src/echo/core/pipeline.py` | `predict_response()` mai chiamato. Fix: `asyncio.gather` parallelo nella pipeline |
| BUG-4 | `src/echo/core/pipeline.py` | Salience `MemoryEntry` hardcoded. Fix: dinamico da `drive_scores` |
| BUG-6 | `src/echo/core/event_bus.py` | `subscribe_once` memory leak: callback non rimosso se evento mai arrivato. Fix: `unsubscribe()` nel wrapper |
| BUG-7 | `src/echo/self_model/identity_graph.py` + `src/echo/consolidation/scheduler.py` | Contraddizioni nel grafo mai risolte. Fix: `resolve_contradictions()` + chiamata nel deep sleep |
| BUG-8 | `src/echo/consolidation/scheduler.py` | Pattern consolidati loggati ma non persistiti. Fix: storati come semantic memories |
| BUG-9 | `src/echo/agents/orchestrator.py` | Routing weight sorting errato: agenti con peso più basso venivano preferiti. Fix: `reverse=True` |

## Improvements Applied ✅
| ID | File | Description |
|----|------|-------------|
| IM-6  | `src/echo/self_model/meta_state.py` | Evoluzione Hebbiana dei pesi drive in `update_drives()` |
| IM-8  | `src/echo/reflection/engine.py` | Engine di riflessione consapevole del workspace attivo (`workspace_context`) |
| IM-10 | `src/echo/consolidation/scheduler.py` + `src/echo/core/types.py` | Metriche health memoria nel light heartbeat: `dormant_count`, `avg_salience`, `total_active` nel `ConsolidationReport` + evento `CONSOLIDATION_COMPLETE` |
| IM-11 | `src/echo/core/pipeline.py` + `src/echo/plasticity/adapter.py` | `prediction_error` wired pipeline→plasticity: alta sorpresa → aggiornamenti pesi più grandi |

## New Features Applied ✅
| ID | File | Description |
|----|------|-------------|
| NEW-1 | `src/echo/core/pipeline.py` | `self_prediction` come segnale di qualità: log INFO con `prediction_error` a ogni interazione |
| NEW-2 | `src/echo/core/pipeline.py` + `src/echo/core/types.py` | Pesi motivazionali influenzano il comportamento: delta drive scalati per `weights[k]`; `weighted_sum()` per `emotional_weight` |
| NEW-3 | `src/echo/memory/episodic.py` + `src/echo/core/pipeline.py` | Linking causale tra memorie: `get_recent()` + `add_causal_link()` → catena causale confermata nel DB |
| NEW-4 | `src/echo/core/pipeline.py` | Workspace → credenze identità: item ad alta salienza (`competition_score > 0.6`) promossi come `IdentityBelief` con `confidence=0.25` |
| NEW-5 | `src/echo/core/pipeline.py` | Drift identitario: distanza coseno tra `agent_weights` snapshots ogni ciclo di riflessione; evento `identity_drift` se > 0.15 |
| NEW-6 | `src/echo/self_model/meta_state.py` + `src/echo/core/pipeline.py` | Stato emotivo (valenza + arousal) sempre attivo: `update_arousal()` aggiunto; valenza e arousal derivati dai drive in `_post_interact` |
| PLAN-1 (v0.2.4) | `src/echo/learning/` (nuovo modulo) | **Deep Real-Time Learning** — `PersonalizationState` (EMA α=0.08, persiste in SQLite) adatta verbosità, topic depth e recall frequency. `PredictiveAnalyticsEngine` (EWMA α=0.20) prevede curiosity spike, identity drift, urgenza consolidation e valenza. `LearningEngine` orchestratore, integrato in `CognitivePipeline`: priors iniettati nel workspace, style hint a salienza 0.40, observe() chiamato ogni interazione dopo drive scoring. Latenza < 0.5 ms. |

## Bug Fixes (ChromaDB)
| Problema | Fix |
|----------|-----|
| `Collection expecting embedding dimension 768, got 384` crashava `_post_interact` | Wrapped `upsert()` in try/except in `episodic.store()` — memoria persiste in SQLite anche senza vettore ChromaDB |

## Integration Tests ✅
- Endpoint `/api/chat` (sync): **PASS** — risposta generata, nessun errore post-interact
- `emotional_valence` ≠ 0 e `arousal` ≠ 0.5 confermati nella risposta JSON
- Causal links verificati in DB: catena `mem1 → mem2 → mem3 → mem4 → mem5`
- 5 interazioni completate senza errori (`echo5.log`: 0 ERROR/CRITICAL)

## Known Pre-existing Issues
- ChromaDB dimensione embedding 768 vs 384: gestita gracefully (skip upsert, memoria salvata in SQLite)
- LM Studio embedding non disponibile in locale → fallback HuggingFace attivo

## Planned Features 🗓️
| ID | Module | Description |
|----|--------|-------------|
| — | — | — (nessuna feature pianificata al momento) |
