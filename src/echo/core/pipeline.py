"""Main cognitive pipeline — connects all components into a single interaction flow."""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

from echo.agents.orchestrator import Orchestrator
from echo.consolidation.scheduler import ConsolidationScheduler
from echo.core.config import settings
from echo.core.event_bus import bus
from echo.core.types import (
    CognitiveEvent,
    EventTopic,
    IdentityBelief,
    InteractionRecord,
    MetaState,
    WorkspaceSnapshot,
)
from echo.memory.decay import DecayScheduler
from echo.memory.episodic import EpisodicMemoryStore, MemoryEntry
from echo.memory.semantic import SemanticMemoryStore
from echo.motivation.motivational_scorer import score_interaction
from echo.learning import LearningEngine
from echo.plasticity.adapter import PlasticityAdapter
from echo.reflection.engine import ReflectionEngine
from echo.self_model.identity_graph import IdentityGraph
from echo.self_model.meta_state import MetaStateTracker
from echo.self_model.self_prediction import predict_response
from echo.workspace.global_workspace import GlobalWorkspace

logger = logging.getLogger(__name__)

# Patterns that suggest the user is introducing their name.
_NAME_PATTERNS = [
    re.compile(r"\b(?:sono|mi chiamo|my name is|i am|chiamami|call me)\s+([A-Za-zÀ-ÖØ-öø-ÿ]{2,30})", re.IGNORECASE),
    re.compile(r"\bI'?m\s+([A-Za-z]{2,30})\b", re.IGNORECASE),
]


def _extract_user_name(text: str) -> str | None:
    """Return the user's name if they introduce themselves, else None."""
    for pat in _NAME_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1).strip().capitalize()
    return None


def _compute_prediction_error(prediction: str, response: str) -> float:
    """Token-overlap prediction error in [0, 1].

    Returns 0.0 = perfect overlap, 1.0 = no shared tokens.
    Used to modulate plasticity magnitude: high surprise → larger weight updates.
    """
    if not prediction or not response:
        return 0.5
    pred_tokens = set(prediction.lower().split())
    resp_tokens = set(response.lower().split())
    union = pred_tokens | resp_tokens
    if not union:
        return 0.5
    overlap = len(pred_tokens & resp_tokens) / len(union)
    return round(1.0 - overlap, 4)


async def _predict_with_timeout(user_input: str, meta_state: MetaState) -> str:
    """Run predict_response with a configurable timeout.

    On slow hardware (e.g. a phone CPU acting as LM Studio server) the
    self-prediction LLM call can easily take 40–100 s.  We cap it at
    ``settings.predict_timeout_s`` and return an empty string on timeout so
    the rest of the pipeline is not blocked.  Lower the cap in .env via
    ``ECHO_PREDICT_TIMEOUT_S=5`` for very constrained hardware.
    """
    try:
        return await asyncio.wait_for(
            predict_response(user_input, meta_state),
            timeout=settings.predict_timeout_s,
        )
    except asyncio.TimeoutError:
        logger.debug(
            "Self-prediction timed out after %.1f s — skipping",
            settings.predict_timeout_s,
        )
        return ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("Self-prediction failed: %s", exc)
        return ""


class CognitivePipeline:
    """Top-level controller for a single interact() call."""

    def __init__(self) -> None:
        self.identity_graph = IdentityGraph()
        self.meta_tracker = MetaStateTracker()
        self.workspace = GlobalWorkspace()
        self.episodic = EpisodicMemoryStore()
        self.semantic = SemanticMemoryStore()
        self.orchestrator = Orchestrator()
        self.reflection = ReflectionEngine(self.identity_graph)
        self.plasticity = PlasticityAdapter()
        self.consolidation = ConsolidationScheduler()
        self.decay = DecayScheduler()
        self.learning = LearningEngine()  # module 16: deep real-time learning
        self._interaction_count = 0
        self._last_drift: float = 0.0  # last identity-drift score (fed to LearningEngine)
        self._last_pipeline_trace: dict[str, Any] = {}  # pipeline trace for UI visualisation
        # Track fire-and-forget tasks so we can await them on graceful shutdown
        self._pending_tasks: set[asyncio.Task] = set()
        self._ready = False

    async def startup(self) -> None:
        """Initialise all stateful components."""
        from echo.core.db import startup as db_startup
        from echo.mcp import mcp_manager

        await db_startup()
        await self.identity_graph.load()
        await self.meta_tracker.load_latest()
        self.consolidation.start()
        self.decay.start()
        await mcp_manager.startup()
        await self.learning.startup()
        self._ready = True
        logger.info("CognitivePipeline ready")

    async def shutdown(self) -> None:
        self.consolidation.stop()
        self.decay.stop()

        # Flush any in-flight fire-and-forget tasks before exiting
        if self._pending_tasks:
            logger.info("Awaiting %d pending post-interact task(s)…", len(self._pending_tasks))
            await asyncio.gather(*self._pending_tasks, return_exceptions=True)

        from echo.core.llm_client import llm
        from echo.mcp import mcp_manager

        await mcp_manager.shutdown()
        await llm.aclose()
        logger.info("CognitivePipeline shutdown")

    @property
    def meta_state(self) -> MetaState:
        return self.meta_tracker.current

    # ------------------------------------------------------------------
    # Core interact()
    # ------------------------------------------------------------------

    async def interact(
        self,
        user_input: str,
        history: list[dict[str, str]] | None = None,
    ) -> InteractionRecord:
        """Full synchronous interact — returns complete record."""
        response, _ = await self._run_pipeline(user_input, history)
        return response

    async def stream_interact(
        self,
        user_input: str,
        history: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[str | dict, None]:
        """Streaming interact — yields status dicts and response string deltas."""
        interaction_id = str(uuid.uuid4())

        # Publish input event
        await bus.publish(
            CognitiveEvent(
                topic=EventTopic.USER_INPUT,
                payload={"text": user_input, "interaction_id": interaction_id},
            )
        )

        # Status: memory retrieval
        _t_pipeline = time.monotonic()
        yield {"_status": "Retrieving episodic memories…"}

        # Retrieve memories + generate self-prediction concurrently (reduces latency)
        # Pre-compute the embedding vector once — episodic and semantic stores both
        # need the same vector so this avoids two sequential LM Studio embed calls.
        _t_retrieval = time.monotonic()
        from echo.core.llm_client import llm as _llm  # noqa: PLC0415
        query_vector = await _llm.embed_one(user_input)
        episodic_mems, semantic_mems, self_pred = await asyncio.gather(
            self.episodic.retrieve_similar(user_input, n_results=5, query_vector=query_vector or None),
            self.semantic.retrieve_similar(user_input, n_results=5, query_vector=query_vector or None),  # 5 → more room for identity facts
            _predict_with_timeout(user_input, self.meta_tracker.current),
        )
        _retrieval_ms = round((time.monotonic() - _t_retrieval) * 1000)
        # Track source counts for downstream SSE metadata
        self._last_memory_sources = {
            "episodic": len(episodic_mems),
            "semantic": len(semantic_mems),
        }

        # Status: workspace loading
        yield {"_status": f"Loaded {len(episodic_mems)} episodic + {len(semantic_mems)} semantic memories…"}

        memories = semantic_mems + episodic_mems  # semantic facts first (identity, name)
        self.workspace.clear()
        self.workspace.load_memories(memories, "archivist")
        # Broadcast self-prediction into workspace so agents can see expected behaviour
        if self_pred:
            self.workspace.broadcast(f"[Self-Prediction] {self_pred}", "self_model", salience=0.65)

        # MODULE-16: inject prediction priors + personalisation hint into workspace
        for _prior_content, _prior_salience in self.learning.get_priors().workspace_items():
            self.workspace.broadcast(_prior_content, "learning", salience=_prior_salience)
        _style_hint = self.learning.personalization.style_hint()
        if _style_hint:
            self.workspace.broadcast(_style_hint, "learning", salience=0.40)

        context: dict[str, Any] = {
            "memories": memories,
            "interaction_id": interaction_id,
            "history": history or [],
            "self_prediction": self_pred,
        }
        meta_state = self.meta_tracker.current

        # Capture workspace snapshot for post-interaction reflection (before streaming clears it)
        workspace_summary = "\n".join(
            f"  [{item.source_agent}] {item.content[:80]}"
            for item in self.workspace.snapshot.items
        )

        # MODULE-16 — build pipeline trace for UI visualisation
        _priors = self.learning.get_priors()
        _pers = self.learning.personalization
        self._last_pipeline_trace = {
            "interaction_id": interaction_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "retrieval": {
                "episodic_count": len(episodic_mems),
                "semantic_count": len(semantic_mems),
                "episodic_snippets": [m.content[:100] for m in episodic_mems[:3]],
                "semantic_snippets": [m.content[:100] for m in semantic_mems[:3]],
            },
            "self_prediction": self_pred or "",
            "learning_priors": {
                "emotional_valence_forecast": round(_priors.emotional_valence_forecast, 3),
                "curiosity_spike_prob": round(_priors.curiosity_spike_prob, 3),
                "identity_drift_risk": round(_priors.identity_drift_risk, 3),
                "consolidation_urgency": round(_priors.consolidation_urgency, 3),
                "is_notable": _priors.is_notable(),
                "workspace_items": [[c, round(s, 3)] for c, s in _priors.workspace_items()],
            },
            "personalization": {
                "verbosity": round(_pers.verbosity, 3),
                "topic_depth": round(_pers.topic_depth, 3),
                "recall_frequency": round(_pers.recall_frequency, 3),
                "style_hint": _pers.style_hint(),
                "n_observations": _pers._n,
            },
            "workspace_items": [
                {
                    "source": item.source_agent,
                    "content": item.content[:120],
                    "salience": round(item.salience, 3),
                    "competition_score": round(item.competition_score, 3),
                }
                for item in self.workspace.snapshot.items
            ],
            "drives_before": {
                "curiosity": round(meta_state.drives.curiosity, 3),
                "coherence": round(meta_state.drives.coherence, 3),
                "stability": round(meta_state.drives.stability, 3),
                "competence": round(meta_state.drives.competence, 3),
            },
            "valence_before": round(meta_state.emotional_valence, 3),
            "arousal_before": round(meta_state.arousal, 3),
            "identity_drift": round(self._last_drift, 3),
            "post_interact_complete": False,
            "drive_scores": {},
            "prediction_error": None,
            "valence_after": None,
            "arousal_after": None,
            "response_length": None,
            "step_times": {
                "retrieval_ms": _retrieval_ms,
                "generation_ms": None,  # filled after streaming completes
                "total_ms": None,
            },
        }

        full_response = []
        # Status: generating response
        yield {"_status": "Generating response…"}
        _t_generation = time.monotonic()
        async for delta in self.orchestrator.stream(
            user_input, self.workspace.snapshot, meta_state, context
        ):
            full_response.append(delta)
            yield delta
        _generation_ms = round((time.monotonic() - _t_generation) * 1000)
        _total_ms = round((time.monotonic() - _t_pipeline) * 1000)
        self._last_pipeline_trace["step_times"]["generation_ms"] = _generation_ms
        self._last_pipeline_trace["step_times"]["total_ms"] = _total_ms

        # Post-interaction (async, non-blocking — tracked for graceful shutdown)
        response_text = "".join(full_response)
        task = asyncio.create_task(
            self._post_interact(
                interaction_id, user_input, response_text, memories,
                self_prediction=self_pred,
                workspace_summary=workspace_summary,
            )
        )
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)

    # ------------------------------------------------------------------
    # Internal pipeline steps
    # ------------------------------------------------------------------

    async def _run_pipeline(
        self,
        user_input: str,
        history: list[dict[str, str]] | None = None,
    ) -> tuple[InteractionRecord, dict[str, str]]:
        interaction_id = str(uuid.uuid4())

        # Publish input event
        await bus.publish(
            CognitiveEvent(
                topic=EventTopic.USER_INPUT,
                payload={"text": user_input, "interaction_id": interaction_id},
            )
        )

        # Retrieve memories + generate self-prediction concurrently.
        # Pre-compute the embedding vector once — both stores share it.
        from echo.core.llm_client import llm as _llm  # noqa: PLC0415
        query_vector = await _llm.embed_one(user_input)
        episodic_mems, semantic_mems, self_pred = await asyncio.gather(
            self.episodic.retrieve_similar(user_input, n_results=5, query_vector=query_vector or None),
            self.semantic.retrieve_similar(user_input, n_results=5, query_vector=query_vector or None),  # 5 → more room for identity facts
            _predict_with_timeout(user_input, self.meta_tracker.current),
        )
        memories = semantic_mems + episodic_mems  # semantic facts first
        self.workspace.clear()
        self.workspace.load_memories(memories, "archivist")
        if self_pred:
            self.workspace.broadcast(f"[Self-Prediction] {self_pred}", "self_model", salience=0.65)

        # MODULE-16: inject prediction priors + personalisation hint into workspace
        for _prior_content, _prior_salience in self.learning.get_priors().workspace_items():
            self.workspace.broadcast(_prior_content, "learning", salience=_prior_salience)
        _style_hint = self.learning.personalization.style_hint()
        if _style_hint:
            self.workspace.broadcast(_style_hint, "learning", salience=0.40)

        context: dict[str, Any] = {
            "memories": memories,
            "history": history or [],
            "self_prediction": self_pred,
        }
        meta_state_before = self.meta_tracker.current.model_copy(deep=True)
        meta_state = self.meta_tracker.current

        workspace_summary = "\n".join(
            f"  [{item.source_agent}] {item.content[:80]}"
            for item in self.workspace.snapshot.items
        )

        # Run orchestrator
        response, agent_outputs = await self.orchestrator.run(
            user_input, self.workspace.snapshot, meta_state, context
        )

        # Post-interaction (blocking in this code path)
        await self._post_interact(
            interaction_id, user_input, response, memories,
            self_prediction=self_pred,
            workspace_summary=workspace_summary,
        )

        record = InteractionRecord(
            id=interaction_id,
            user_input=user_input,
            assistant_response=response,
            meta_state_before=meta_state_before,
            meta_state_after=self.meta_tracker.current,
            memories_retrieved=[m.id for m in memories],
        )
        return record, agent_outputs

    async def _post_interact(
        self,
        interaction_id: str,
        user_input: str,
        response: str,
        memories: list[MemoryEntry],
        self_prediction: str = "",
        workspace_summary: str = "",
    ) -> None:
        """Store memory, reflect, adapt weights — runs async fire-and-forget.

        self_prediction: ECHO's pre-response prediction (for predictive coding error).
        workspace_summary: snapshot of active workspace items for richer reflection.
        """
        try:
            meta_state = self.meta_tracker.current

            # IM-11: Compute prediction error — 0 = perfect prediction, 1 = max surprise
            prediction_error = _compute_prediction_error(self_prediction, response)

            # NEW-1: Log prediction quality so we can monitor self-awareness over time
            if self_prediction and prediction_error is not None:
                logger.info(
                    "Self-prediction quality: error=%.3f  (0=perfect, 1=max surprise)",
                    prediction_error,
                )

            # BUG-2 / IM-1: LLM-based motivational scoring replaces heuristic drives
            drive_scores = await score_interaction(user_input, response, meta_state)

            # FIX: Update agent routing weights based on drive activations each turn.
            # Each drive has semantic affinity with one or more agents — the agent whose
            # specialty is most useful given the current motivational state gets a weight boost.
            # This is the ONLY place update_agent_weight() is called; without it all
            # agents stay permanently at 1.0 and the routing system is inert.
            _AGENT_WEIGHT_LR = 0.03  # small step — weights should drift slowly
            # Maps drive name → list of (agent_name, direction).
            # direction=+1: drive↑ boosts agent; direction=-1: drive↑ suppresses agent.
            _DRIVE_AGENT_MAP: list[tuple[str, str, float]] = [
                ("curiosity",    "explorer",      +1.0),
                ("curiosity",    "archivist",     -0.4),  # exploration ↔ conservation trade-off
                ("coherence",    "analyst",       +1.0),
                ("coherence",    "skeptic",       +0.6),
                ("coherence",    "explorer",      -0.3),
                ("stability",    "archivist",     +1.0),
                ("stability",    "explorer",      -0.5),
                ("competence",   "planner",       +1.0),
                ("competence",   "analyst",       +0.4),
                ("compression",  "analyst",       +0.8),
                ("compression",  "planner",       +0.4),
            ]
            for drive, agent, direction in _DRIVE_AGENT_MAP:
                score = drive_scores.get(drive, 0.5)
                # delta: positive when score is above neutral (0.5), scaled by direction
                delta = (score - 0.5) * direction * _AGENT_WEIGHT_LR
                self.meta_tracker.update_agent_weight(agent, delta)

            # social_self tracks emotional valence directly — high valence → more active
            valence_now = meta_state.emotional_valence
            self.meta_tracker.update_agent_weight(
                "social_self", valence_now * 0.5 * _AGENT_WEIGHT_LR
            )
            # orchestrator weight is the geometric mean of all other weights — stays balanced
            # (no explicit update; it naturally tracks the weighted result via the scores)

            # MODULE-16: Deep Real-Time Learning — update personalization + predictor
            await self.learning.observe(
                response=response,
                user_input=user_input,
                novelty_score=drive_scores.get("curiosity", 0.5),
                curiosity=meta_state.drives.curiosity,
                coherence=meta_state.drives.coherence,
                emotional_valence=meta_state.emotional_valence,
                identity_drift=self._last_drift,
                memory_count=len(memories),
            )

            # NEW-6: Derive emotional valence from drive activations.
            # coherence/competence → positive affect; low stability → negative affect.
            valence_signal = (
                drive_scores.get("coherence", 0.5)
                + drive_scores.get("competence", 0.5)
                - drive_scores.get("stability", 0.5) * 0.3
            ) / 2.0 - 0.5  # approx [-0.5, +0.5]
            self.meta_tracker.update_valence(
                (valence_signal - meta_state.emotional_valence) * 0.15
            )

            # NEW-6: Arousal rises with prediction error (surprise) and drive activation
            mean_activation = sum(drive_scores.values()) / max(len(drive_scores), 1)
            arousal_target = 0.3 + 0.5 * prediction_error + 0.2 * mean_activation
            self.meta_tracker.update_arousal(
                (arousal_target - meta_state.arousal) * 0.10
            )

            # Read updated state so emotional_weight reflects the live valence
            updated_state = self.meta_tracker.current

            # NEW-2: Scale attractor deltas by drive weights so plastic drives move faster
            _DRIVE_ATTRACTION = 0.08
            score_deltas: dict[str, float] = {
                k: (v - getattr(meta_state.drives, k, 0.5))
                   * _DRIVE_ATTRACTION
                   * (meta_state.drives.weights.get(k, 0.2) / 0.2)
                for k, v in drive_scores.items()
                if hasattr(meta_state.drives, k)
            }

            # BUG-4 / IM-3: Dynamic salience from motivational scores.
            # NEW-2 + NEW-6: emotional_weight combines live valence and weighted drives.
            weighted_drive = updated_state.drives.weighted_sum(drive_scores)
            mem = MemoryEntry(
                content=f"User: {user_input}\nECHO: {response}",
                importance=drive_scores.get("competence", 0.6),
                novelty=drive_scores.get("curiosity", 0.5),
                self_relevance=drive_scores.get("coherence", 0.6),
                emotional_weight=max(
                    0.1,
                    0.5 * abs(updated_state.emotional_valence) + 0.5 * weighted_drive,
                ),
                source_agent="pipeline",
            )
            stored_mem = await self.episodic.store(mem)

            # NEW-3: Temporal causal link — new memory points back to the previous one
            try:
                recent = await self.episodic.get_recent(n=2)
                prev = next((m for m in recent if m.id != stored_mem.id), None)
                if prev is not None:
                    await self.episodic.add_causal_link(stored_mem.id, prev.id)
                    logger.debug("Causal link: %s → %s", prev.id[:8], stored_mem.id[:8])
            except Exception as exc:  # noqa: BLE001
                logger.debug("Causal linking failed: %s", exc)

            # NEW-4: Promote highly competitive workspace items to weak identity beliefs.
            # Items with competition_score > 0.6 that aren't already from identity agents
            # are turned into low-confidence beliefs so ECHO can learn from "what was conscious".
            try:
                for item in self.workspace.snapshot.items[:3]:
                    if (
                        item.competition_score > 0.6
                        and item.source_agent not in ("archivist", "self_model")
                        and len(item.content.strip()) > 20
                    ):
                        belief = IdentityBelief(
                            content=item.content[:200],
                            confidence=0.25,
                            source_agent="workspace",
                        )
                        await self.identity_graph.add_belief(belief)
                        logger.debug("Workspace→belief: %.30s…", item.content)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Workspace→belief promotion failed: %s", exc)

            # Persist user identity if they introduced themselves
            user_name = _extract_user_name(user_input)
            if user_name:
                await self.semantic.store(
                    content=f"The user's name is {user_name}.",
                    tags=["user_identity", "name"],
                    salience=0.95,
                )
                logger.info("Stored user identity: name=%s", user_name)

            # LLM Wiki — lightweight post-interaction update (fire-and-forget within post_interact)
            try:
                from echo.memory.wiki import wiki as _wiki  # noqa: PLC0415
                result = await _wiki.update_from_interaction(user_input, response)
                if result.get("pages_updated", 0):
                    logger.debug("Wiki: updated %d page(s) from interaction", result["pages_updated"])
            except Exception as exc:  # noqa: BLE001
                logger.debug("Wiki update skipped: %s", exc)

            self._interaction_count += 1

            # BUG-1 / IM-4: Configurable reflection interval (was hardcoded)
            if self._interaction_count % settings.reflection_trigger_interval == 0:
                # IM-8: Pass workspace snapshot so reflection knows what was "conscious"
                reflection = await self.reflection.reflect(
                    interaction_id, user_input, response,
                    self.meta_tracker.current,
                    workspace_summary=workspace_summary,
                )

                # Merge scorer deltas with reflection-generated adjustments
                merged_deltas = dict(score_deltas)
                for k, v in reflection.drive_adjustments.items():
                    merged_deltas[k] = merged_deltas.get(k, 0.0) + v

                self.meta_tracker.update_drives(merged_deltas)

                # IM-11: Plasticity modulated by prediction error (surprise ↑ → learning ↑)
                self.plasticity.apply(
                    self.meta_tracker.current,
                    reflection.insights,
                    prediction_error=prediction_error,
                )

                # NEW-5: Identity drift detection — fires every reflection cycle.
                # Cosine distance between current and previous agent_weights vectors.
                if hasattr(self, "_weights_snapshot") and self._weights_snapshot:
                    drift = _compute_identity_drift(
                        self._weights_snapshot,
                        self.meta_tracker.current.agent_weights,
                    )
                    self._last_drift = drift  # expose to LearningEngine on next turn
                    if drift > 0.15:
                        logger.info("Identity drift detected: %.3f", drift)
                        await bus.publish(CognitiveEvent(
                            topic=EventTopic.META_STATE_UPDATE,
                            payload={
                                "type": "identity_drift",
                                "drift": round(drift, 4),
                                "interaction_count": self._interaction_count,
                            },
                        ))
                # Always snapshot for the next check
                self._weights_snapshot = dict(self.meta_tracker.current.agent_weights)

                await self.meta_tracker.save()

                await bus.publish(
                    CognitiveEvent(
                        topic=EventTopic.REFLECTION_COMPLETE,
                        payload={
                            "interaction_id": interaction_id,
                            "insights": reflection.insights,
                            "new_beliefs": len(reflection.new_beliefs),
                            "prediction_error": round(prediction_error, 3),
                            "emotional_valence": round(
                                self.meta_tracker.current.emotional_valence, 3
                            ),
                            "arousal": round(self.meta_tracker.current.arousal, 3),
                        },
                    )
                )
                logger.debug(
                    "Reflection done — prediction_error=%.3f insights=%d "
                    "valence=%.3f arousal=%.3f",
                    prediction_error,
                    len(reflection.insights),
                    self.meta_tracker.current.emotional_valence,
                    self.meta_tracker.current.arousal,
                )
            else:
                # Between reflections: still apply drive scores so drives stay live
                self.meta_tracker.update_drives(score_deltas)
                await self.meta_tracker.save()

            # MODULE-16 — update pipeline trace with post-interact results
            self._last_pipeline_trace.update({
                "drive_scores": {k: round(v, 3) for k, v in drive_scores.items()},
                "prediction_error": round(prediction_error, 3),
                "identity_drift": round(self._last_drift, 3),
                "valence_after": round(self.meta_tracker.current.emotional_valence, 3),
                "arousal_after": round(self.meta_tracker.current.arousal, 3),
                "response_length": len(response),
                "post_interact_complete": True,
            })

        except Exception as exc:  # noqa: BLE001
            logger.error("Post-interact error: %s", exc)


def _compute_identity_drift(
    prev_weights: dict[str, float],
    curr_weights: dict[str, float],
) -> float:
    """Return cosine distance between two agent_weights vectors.

    0.0 = identical (no drift), 1.0 = orthogonal (maximum drift).
    """
    keys = sorted(set(curr_weights) | set(prev_weights))
    v1 = [prev_weights.get(k, 0.0) for k in keys]
    v2 = [curr_weights.get(k, 0.0) for k in keys]
    dot = sum(a * b for a, b in zip(v1, v2))
    mag1 = sum(a ** 2 for a in v1) ** 0.5
    mag2 = sum(b ** 2 for b in v2) ** 0.5
    if mag1 * mag2 == 0.0:
        return 0.0
    return 1.0 - dot / (mag1 * mag2)


# Module-level singleton (lazily initialised at startup)
pipeline: CognitivePipeline = CognitivePipeline()
