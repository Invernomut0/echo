"""Heartbeat scheduler — two-speed consolidation loop.

Light heartbeat  (every LIGHT_INTERVAL seconds, default 300 = 5 min):
    Runs a standard ConsolidationPhase cycle.

Deep / REM heartbeat (every DEEP_INTERVAL seconds, default 43 200 = 12 h):
    Runs a full ConsolidationPhase *plus* DreamPhase (LLM dream generation),
    then persists the resulting DreamEntry to DreamStore.

Both loops are started/stopped together via start() / stop().
Manual triggers are available via trigger_now() (light) and trigger_rem_now() (deep).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any

from echo.core.event_bus import bus
from echo.core.types import CognitiveEvent, ConsolidationReport, DreamEntry, EventTopic

logger = logging.getLogger(__name__)

# Default intervals — overridable via CONSOLIDATION_LIGHT_INTERVAL_S / CONSOLIDATION_DEEP_INTERVAL_S
LIGHT_INTERVAL = 300     # 5 minutes
DEEP_INTERVAL = 43_200   # 12 hours


class ConsolidationScheduler:
    """Dual-heartbeat scheduler for light and deep (REM) consolidation."""

    def __init__(
        self,
        light_interval: int = LIGHT_INTERVAL,
        deep_interval: int = DEEP_INTERVAL,
    ) -> None:
        self._light_interval = light_interval
        self._deep_interval = deep_interval

        # asyncio tasks
        self._light_task: asyncio.Task[None] | None = None
        self._deep_task: asyncio.Task[None] | None = None
        self._running = False
        self._light_running = False  # guard: prevent overlapping light cycles
        self._deep_running = False   # guard: prevent overlapping deep cycles

        # Pipeline reference (set by CognitivePipeline.startup via attach())
        self._pipeline: Any | None = None

        # Status tracking
        self._last_report: ConsolidationReport | None = None
        self._event_log: deque[dict[str, Any]] = deque(maxlen=50)
        self._last_light_at: datetime | None = None
        self._last_deep_at: datetime | None = None
        self._next_light_at: datetime | None = None
        self._next_deep_at: datetime | None = None

    # ------------------------------------------------------------------
    # Loops
    # ------------------------------------------------------------------

    async def _light_loop(self) -> None:
        logger.info("Light heartbeat started (interval=%ds)", self._light_interval)
        while self._running:
            self._next_light_at = datetime.now(timezone.utc) + timedelta(
                seconds=self._light_interval
            )
            await asyncio.sleep(self._light_interval)
            if not self._running:
                break
            if self._light_running:
                logger.info("Light cycle skipped — previous cycle still running")
                continue
            try:
                self._light_running = True
                logger.info("Light consolidation tick (cycle #%d)", self._cycle_count if hasattr(self, '_cycle_count') else 0)
                if not hasattr(self, '_cycle_count'):
                    self._cycle_count = 0
                self._cycle_count += 1
                report = await self._run_light()
                self._last_report = report
                self._last_light_at = datetime.now(timezone.utc)
                self._event_log.append({
                    "id": str(uuid.uuid4())[:8],
                    "type": "light",
                    "timestamp": self._last_light_at.isoformat(),
                    "actions": {
                        "memories_processed": report.memories_processed,
                        "memories_promoted": report.memories_promoted,
                        "memories_pruned": report.memories_pruned,
                        "episodic_deduped": report.episodic_deduped,
                        "semantic_deduped": report.semantic_deduped,
                        "patterns_found": len(report.patterns_found),
                        "patterns": report.patterns_found,
                        "promoted_snippets": report.promoted_snippets,
                        "pruned_snippets": report.pruned_snippets,
                        "deduped_pairs": [{"winner": w, "loser": l} for w, l in report.deduped_pairs[:5]],
                    },
                })
                self._next_light_at = self._last_light_at + timedelta(
                    seconds=self._light_interval
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("Light consolidation error: %s", exc)
            finally:
                self._light_running = False

    async def _deep_loop(self) -> None:
        logger.info("Deep (REM) heartbeat started (interval=%ds)", self._deep_interval)
        while self._running:
            self._next_deep_at = datetime.now(timezone.utc) + timedelta(
                seconds=self._deep_interval
            )
            await asyncio.sleep(self._deep_interval)
            if not self._running:
                break
            if self._deep_running:
                logger.info("Deep cycle skipped — previous cycle still running")
                continue
            try:
                self._deep_running = True
                logger.info("REM consolidation tick")
                report = await self._run_deep()
                self._last_report = report
                self._last_deep_at = datetime.now(timezone.utc)
                self._event_log.append({
                    "id": str(uuid.uuid4())[:8],
                    "type": "deep",
                    "timestamp": self._last_deep_at.isoformat(),
                    "actions": {
                        "memories_processed": report.memories_processed,
                        "memories_promoted": report.memories_promoted,
                        "memories_pruned": report.memories_pruned,
                        "episodic_deduped": report.episodic_deduped,
                        "semantic_deduped": report.semantic_deduped,
                        "patterns_found": len(report.patterns_found),
                        "patterns": report.patterns_found,
                        "promoted_snippets": report.promoted_snippets,
                        "pruned_snippets": report.pruned_snippets,
                        "deduped_pairs": [{"winner": w, "loser": l} for w, l in report.deduped_pairs[:5]],
                    },
                })
                self._next_deep_at = self._last_deep_at + timedelta(
                    seconds=self._deep_interval
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("REM consolidation error: %s", exc)
            finally:
                self._deep_running = False

    # ------------------------------------------------------------------
    # Phase runners
    # ------------------------------------------------------------------

    async def _run_light(self) -> ConsolidationReport:
        from echo.consolidation.sleep_phase import ConsolidationPhase

        phase = ConsolidationPhase()
        # Light cycle: apply decay + mark dormant — do NOT delete memories
        report = await phase.run(elapsed_seconds=self._light_interval, prune=False)
        logger.info(
            "Light done: processed=%d promoted=%d dormant=%d",
            report.memories_processed,
            report.memories_promoted,
            report.memories_pruned,
        )

        # Idle-time curiosity: search for new knowledge when no user is active
        try:
            from echo.core.user_activity import is_active as _user_active  # noqa: PLC0415
            from echo.curiosity.engine import CuriosityEngine, _is_running as _curiosity_running  # noqa: PLC0415
            if _user_active():
                logger.debug("Curiosity skipped — user recently active")
            elif _curiosity_running:
                logger.debug("Curiosity cycle skipped — previous cycle still running")
            else:
                new_memories = await CuriosityEngine().run_cycle()
                if new_memories:
                    logger.info("Curiosity acquired %d new semantic memories", new_memories)
                # Log curiosity event; include skip reason when known
                curiosity_log: dict[str, Any] = {
                    "id": str(uuid.uuid4())[:8],
                    "type": "curiosity",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "actions": {"memories_stored": new_memories or 0},
                }
                # Retrieve skip reason from activity log if available
                try:
                    from echo.curiosity.engine import _activity_log as _clog  # noqa: PLC0415
                    if _clog:
                        last = _clog[-1]
                        if last.get("status") == "skipped":
                            curiosity_log["actions"]["skip_reason"] = last.get("skip_reason", "")
                        elif last.get("status") == "completed":
                            curiosity_log["actions"]["topics"] = last.get("topics_searched", [])
                except Exception:  # noqa: BLE001
                    pass
                self._event_log.append(curiosity_log)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Curiosity cycle error: %s", exc)

        # Proactive Initiative Engine: generate insights, questions, milestone updates
        try:
            from echo.core.user_activity import is_active as _user_active2  # noqa: PLC0415
            from echo.initiative.engine import initiative_engine  # noqa: PLC0415
            if _user_active2():
                logger.debug("Initiative skipped — user recently active")
            else:
                initiatives = await initiative_engine.run_cycle()
                if initiatives:
                    logger.info(
                        "Initiative cycle: %d proactive message(s) generated",
                        len(initiatives),
                    )
                    self._event_log.append({
                        "id": str(uuid.uuid4())[:8],
                        "type": "initiative",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "actions": {
                            "messages_generated": len(initiatives),
                            "types": list({i.get("type", "unknown") for i in initiatives}),
                        },
                    })
        except Exception as exc:  # noqa: BLE001
            logger.warning("Initiative cycle error: %s", exc)

        # Proactive state evaluator — ECHO decides autonomously what to share via Telegram
        if self._pipeline is not None:
            try:
                from echo.core.user_activity import is_active as _ua_proactive  # noqa: PLC0415
                if not _ua_proactive():
                    from echo.initiative.proactive_engine import proactive_echo  # noqa: PLC0415
                    msg = await proactive_echo.evaluate_and_reach_out(self._pipeline)
                    if msg:
                        self._event_log.append({
                            "id": str(uuid.uuid4())[:8],
                            "type": "proactive",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "actions": {"message": msg[:300], "delivered": True},
                        })
            except Exception as exc:  # noqa: BLE001
                logger.warning("Proactive engine error: %s", exc)

        # Autonomous self-modification (6h cooldown — effectively max 4×/day)
        if self._pipeline is not None:
            try:
                from echo.core.user_activity import is_active as _ua_sm  # noqa: PLC0415
                if not _ua_sm():
                    from echo.self_modification.engine import self_modification_engine  # noqa: PLC0415
                    mod = await self_modification_engine.evaluate_and_modify(self._pipeline)
                    if mod:
                        self._event_log.append({
                            "id": str(uuid.uuid4())[:8],
                            "type": "selfmod",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "actions": {
                                "file": mod.get("file", ""),
                                "description": mod.get("description", ""),
                                "pushed": mod.get("pushed", False),
                            },
                        })
            except Exception as exc:  # noqa: BLE001
                logger.warning("Self-modification engine error: %s", exc)

        # GitHub wiki sync — runs every WIKI_SYNC_INTERVAL_H hours (default 24h)
        try:
            from echo.memory.wiki_sync import wiki_sync  # noqa: PLC0415
            sync_result = await wiki_sync.sync()
            if sync_result.get("synced", 0) > 0 or sync_result.get("error"):
                self._event_log.append({
                    "id": str(uuid.uuid4())[:8],
                    "type": "wiki_sync",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "actions": sync_result,
                })
        except Exception as exc:  # noqa: BLE001
            logger.warning("Wiki sync error: %s", exc)

        # Spurious / conflicting semantic memory cleanup
        try:
            from echo.memory.semantic import SemanticMemoryStore  # noqa: PLC0415

            semantic = SemanticMemoryStore()
            cleanup = await semantic.detect_and_clean_conflicts()
            if cleanup["auto_fixed"]:
                logger.info(
                    "Memory cleanup: auto-fixed %d spurious/conflicting entries: %s",
                    len(cleanup["auto_fixed"]),
                    [f["content"][:50] for f in cleanup["auto_fixed"]],
                )
            if cleanup["needs_review"]:
                logger.warning(
                    "Memory conflicts need user review (%d category/ies): %s",
                    len(cleanup["needs_review"]),
                    cleanup["needs_review"],
                )
                # Publish event so the frontend / SSE consumers can alert the user.
                await bus.publish(CognitiveEvent(
                    topic=EventTopic.CONSOLIDATION_COMPLETE,
                    source_agent="memory_cleanup",
                    payload={
                        "cycle": "light",
                        "memory_conflicts": cleanup["needs_review"],
                        "message": (
                            "Conflicting memories detected — please review: "
                            + ", ".join(
                                f"{c['category']}: "
                                + " vs ".join(
                                    f"'{cand['content'][:30]}…'"
                                    for cand in c["candidates"]
                                )
                                for c in cleanup["needs_review"]
                            )
                        ),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                ))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Memory conflict cleanup error: %s", exc)

        # IM-10: Collect memory health telemetry and emit CONSOLIDATION_COMPLETE
        try:
            from echo.memory.episodic import EpisodicMemoryStore  # noqa: PLC0415
            store = EpisodicMemoryStore()
            active_mems = await store.get_all(limit=500, include_dormant=False)
            dormant_mems = await store.get_dormant(limit=500)
            total_active = len(active_mems)
            dormant_count = len(dormant_mems)
            avg_salience = (
                sum(m.salience for m in active_mems) / total_active
                if total_active else 0.0
            )
            report.dormant_count = dormant_count
            report.avg_salience = round(avg_salience, 4)
            report.total_active = total_active
            await bus.publish(CognitiveEvent(
                topic=EventTopic.CONSOLIDATION_COMPLETE,
                source_agent="scheduler",
                payload={
                    "cycle": "light",
                    "total_active": total_active,
                    "dormant_count": dormant_count,
                    "avg_salience": round(avg_salience, 4),
                    "memories_promoted": report.memories_promoted,
                    "memories_processed": report.memories_processed,
                    "episodic_deduped": report.episodic_deduped,
                    "semantic_deduped": report.semantic_deduped,
                    "re_embedded": report.re_embedded,
                    "memories_pruned": report.memories_pruned,
                    "patterns_found": len(report.patterns_found),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            ))
            logger.info(
                "Memory health: active=%d dormant=%d avg_salience=%.3f",
                total_active, dormant_count, avg_salience,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Memory health metrics collection failed: %s", exc)

        # echo.md self-update — best-effort, non-blocking
        try:
            from echo.self_model.echo_md import EchoMdManager  # noqa: PLC0415
            from echo.core.pipeline import pipeline as _pl  # noqa: PLC0415
            _ms = _pl.meta_state if _pl._ready else None
            updated = await EchoMdManager().review_and_update(
                meta_state=_ms,
                patterns=report.patterns_found or [],
            )
            if updated:
                logger.info("echo.md updated during light consolidation cycle")
        except Exception as exc:  # noqa: BLE001
            logger.warning("echo.md review (light) failed: %s", exc)

        return report

    async def _run_deep(self) -> ConsolidationReport:
        from echo.consolidation.dream_phase import DreamPhase
        from echo.consolidation.sleep_phase import ConsolidationPhase
        from echo.memory.dream_store import DreamStore

        # Deep/REM cycle: elapsed_seconds=0 (light already applied decay)
        # prune=True → permanently delete sub-threshold memories
        phase = ConsolidationPhase()
        report = await phase.run(elapsed_seconds=0, prune=True)
        logger.info(
            "REM consolidation done: processed=%d promoted=%d pruned=%d patterns=%d",
            report.memories_processed,
            report.memories_promoted,
            report.memories_pruned,
            len(report.patterns_found),
        )

        # BUG-8: Persist consolidated patterns as semantic memories
        # (previously logged but immediately discarded)
        if report.patterns_found:
            from echo.memory.semantic import SemanticMemoryStore  # noqa: PLC0415

            semantic = SemanticMemoryStore()
            stored_count = 0
            for pattern in report.patterns_found:
                if pattern and len(pattern.strip()) > 10:
                    await semantic.store(
                        content=f"[Consolidated pattern] {pattern.strip()}",
                        tags=["consolidated_pattern", "sleep_phase"],
                        salience=0.75,
                    )
                    stored_count += 1
            logger.info(
                "Persisted %d/%d consolidated pattern(s) as semantic memories",
                stored_count, len(report.patterns_found),
            )

        # BUG-7: Resolve contradictions in the identity graph during deep sleep
        # Uses lazy import to avoid circular dependency (scheduler → pipeline)
        try:
            from echo.core.pipeline import pipeline  # noqa: PLC0415

            if pipeline._ready:
                resolved = await pipeline.identity_graph.resolve_contradictions()
                if resolved:
                    logger.info(
                        "Deep-sleep contradiction resolution: %d belief(s) attenuated",
                        len(resolved),
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Contradiction resolution error: %s", exc)

        # Retrieve current MetaState (best-effort — errors are non-fatal)
        _meta_state = None
        try:
            from echo.core.pipeline import pipeline  # noqa: PLC0415
            if pipeline._ready:
                _meta_state = pipeline.meta_state
        except Exception:  # noqa: BLE001
            pass

        dream = await DreamPhase().run(meta_state=_meta_state)
        await DreamStore().store(dream)
        logger.info("Dream stored (id=%s, type=%s)", dream.id, dream.cycle_type)

        # Apply weight mutations produced by WeightEvolution
        if dream.weight_mutations:
            try:
                from echo.core.pipeline import pipeline as _pl  # noqa: PLC0415
                if _pl._ready and _pl.meta_state:
                    ms = _pl.meta_state
                    for agent, delta in dream.weight_mutations.items():
                        cur = ms.agent_weights.get(agent, 1.0)
                        ms.agent_weights[agent] = float(max(0.1, min(2.0, cur + delta)))
                    await bus.publish(CognitiveEvent(
                        topic=EventTopic.PLASTICITY_UPDATE,
                        source_agent="dream_evolution",
                        payload={
                            "mutations": dream.weight_mutations,
                            "source": "dream_evolution",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    ))
                    logger.info("Dream weight evolution applied: %s", dream.weight_mutations)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Weight mutation apply failed: %s", exc)

        # Spurious / conflicting semantic memory cleanup (deep pass — prune=True)
        try:
            from echo.memory.semantic import SemanticMemoryStore  # noqa: PLC0415

            semantic = SemanticMemoryStore()
            cleanup = await semantic.detect_and_clean_conflicts()
            if cleanup["auto_fixed"]:
                logger.info(
                    "REM memory cleanup: auto-fixed %d spurious entries: %s",
                    len(cleanup["auto_fixed"]),
                    [f["content"][:50] for f in cleanup["auto_fixed"]],
                )
            if cleanup["needs_review"]:
                logger.warning(
                    "REM: memory conflicts need user review: %s",
                    cleanup["needs_review"],
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("REM memory conflict cleanup error: %s", exc)

        # Collect memory health telemetry and emit CONSOLIDATION_COMPLETE
        try:
            from echo.memory.episodic import EpisodicMemoryStore  # noqa: PLC0415
            store = EpisodicMemoryStore()
            active_mems = await store.get_all(limit=500, include_dormant=False)
            dormant_mems = await store.get_dormant(limit=500)
            total_active = len(active_mems)
            dormant_count = len(dormant_mems)
            avg_salience = (
                sum(m.salience for m in active_mems) / total_active
                if total_active else 0.0
            )
            report.dormant_count = dormant_count
            report.avg_salience = round(avg_salience, 4)
            report.total_active = total_active
            await bus.publish(CognitiveEvent(
                topic=EventTopic.CONSOLIDATION_COMPLETE,
                source_agent="scheduler",
                payload={
                    "cycle": "rem",
                    "total_active": total_active,
                    "dormant_count": dormant_count,
                    "avg_salience": round(avg_salience, 4),
                    "memories_promoted": report.memories_promoted,
                    "memories_processed": report.memories_processed,
                    "episodic_deduped": report.episodic_deduped,
                    "semantic_deduped": report.semantic_deduped,
                    "re_embedded": report.re_embedded,
                    "memories_pruned": report.memories_pruned,
                    "patterns_found": len(report.patterns_found),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            ))
            logger.info(
                "REM health: active=%d dormant=%d avg_salience=%.3f deduped=ep%d/sem%d",
                total_active, dormant_count, avg_salience,
                report.episodic_deduped, report.semantic_deduped,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("REM health metrics collection failed: %s", exc)

        # echo.md self-update — best-effort, non-blocking
        try:
            from echo.self_model.echo_md import EchoMdManager  # noqa: PLC0415
            updated = await EchoMdManager().review_and_update(
                meta_state=_meta_state,
                patterns=report.patterns_found or [],
            )
            if updated:
                logger.info("echo.md updated during REM consolidation cycle")
        except Exception as exc:  # noqa: BLE001
            logger.warning("echo.md review (REM) failed: %s", exc)

        # Growth report generation (deep-sleep milestone)
        try:
            from echo.learning.growth_tracker import growth_tracker as _gt  # noqa: PLC0415
            growth_report = await _gt.generate_report()
            if growth_report:
                logger.info("Growth report generated during REM cycle")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Growth report generation failed: %s", exc)

        # MODULE-6: Deep Associative Memory — cross-pollination + temporal clustering
        try:
            from echo.memory.associative import associative_memory  # noqa: PLC0415
            associations = await associative_memory.cross_pollinate()
            themes = await associative_memory.temporal_clustering()
            if associations or themes:
                logger.info(
                    "Associative memory: %d cross-pollinations, %d temporal themes",
                    len(associations), len(themes),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Associative memory cycle failed: %s", exc)

        # MODULE-7: Metacognitive deep review — update self-model from learning data
        try:
            from echo.self_model.metacognition import metacognitive_model  # noqa: PLC0415
            from echo.learning.meta_learning import meta_learning as _ml  # noqa: PLC0415
            from echo.learning.self_evaluation import self_evaluation as _se  # noqa: PLC0415
            from echo.learning.growth_tracker import growth_tracker as _gt2  # noqa: PLC0415

            # Feed accumulated learning data into metacognition
            await metacognitive_model.update_from_learning(
                growth_trajectory=(
                    "improving" if _gt2.metrics.is_growing
                    else "stagnant" if _gt2.metrics.is_stagnant
                    else "stable"
                ),
                best_conditions=_ml.quality.best_conditions,
                competence_map=_se.competence_map,
                engagement_score=_se.engagement_score,
            )
            # Run full LLM-based deep review
            updated = await metacognitive_model.deep_review()
            if updated:
                logger.info("Metacognitive model updated during REM cycle")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Metacognitive deep review failed: %s", exc)

        return report

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def attach_pipeline(self, pipeline: Any) -> None:
        """Attach the CognitivePipeline reference so the proactive engine can read state."""
        self._pipeline = pipeline

    def start(self) -> None:
        """Start both heartbeat loops."""
        if self._running:
            return
        self._running = True
        self._light_task = asyncio.create_task(self._light_loop())
        self._deep_task = asyncio.create_task(self._deep_loop())
        now = datetime.now(timezone.utc)
        self._next_light_at = now + timedelta(seconds=self._light_interval)
        self._next_deep_at = now + timedelta(seconds=self._deep_interval)
        logger.info("HeartbeatScheduler started (light=%ds deep=%ds)",
                    self._light_interval, self._deep_interval)

    async def stop(self) -> None:
        """Cancel both loops and wait for them to finish."""
        self._running = False
        tasks = [t for t in (self._light_task, self._deep_task) if t and not t.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("HeartbeatScheduler stopped")

    # ------------------------------------------------------------------
    # Manual triggers
    # ------------------------------------------------------------------

    async def trigger_now(self) -> ConsolidationReport:
        """Manually trigger one light consolidation cycle (no decay step).

        Equivalent to _run_light() but without the scheduling overhead.
        Includes the curiosity engine run.
        """
        report = await self._run_light()
        self._last_report = report
        self._last_light_at = datetime.now(timezone.utc)
        return report

    async def trigger_rem_now(self) -> DreamEntry:
        """Manually trigger the full REM phase (no extra decay step)."""
        from echo.consolidation.dream_phase import DreamPhase
        from echo.consolidation.sleep_phase import ConsolidationPhase
        from echo.memory.dream_store import DreamStore

        phase = ConsolidationPhase()
        report = await phase.run(elapsed_seconds=0, prune=True)

        _meta_state = None
        try:
            from echo.core.pipeline import pipeline  # noqa: PLC0415
            if pipeline._ready:
                _meta_state = pipeline.meta_state
        except Exception:  # noqa: BLE001
            pass

        dream = await DreamPhase().run(meta_state=_meta_state)
        await DreamStore().store(dream)

        # Collect health telemetry and update last report
        try:
            from echo.memory.episodic import EpisodicMemoryStore  # noqa: PLC0415
            store = EpisodicMemoryStore()
            active_mems = await store.get_all(limit=500, include_dormant=False)
            dormant_mems = await store.get_dormant(limit=500)
            total_active = len(active_mems)
            dormant_count = len(dormant_mems)
            avg_salience = (
                sum(m.salience for m in active_mems) / total_active
                if total_active else 0.0
            )
            report.dormant_count = dormant_count
            report.avg_salience = round(avg_salience, 4)
            report.total_active = total_active
        except Exception as exc:  # noqa: BLE001
            logger.warning("REM telemetry in trigger_rem_now failed: %s", exc)

        self._last_report = report
        self._last_deep_at = datetime.now(timezone.utc)
        return dream

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @property
    def event_log(self) -> list[dict[str, Any]]:
        """Return heartbeat event log newest-first (max 50 entries)."""
        events = list(self._event_log)
        events.reverse()
        return events

    @property
    def last_report(self) -> ConsolidationReport | None:
        return self._last_report

    @property
    def heartbeat_status(self) -> dict:
        def _fmt(dt: datetime | None) -> str | None:
            return dt.isoformat() if dt else None

        return {
            "last_light_at": _fmt(self._last_light_at),
            "last_deep_at": _fmt(self._last_deep_at),
            "next_light_at": _fmt(self._next_light_at),
            "next_deep_at": _fmt(self._next_deep_at),
            "light_interval_seconds": self._light_interval,
            "deep_interval_seconds": self._deep_interval,
            "running": self._running,
        }
