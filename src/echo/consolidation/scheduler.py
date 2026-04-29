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
from datetime import datetime, timedelta, timezone

from echo.core.event_bus import bus
from echo.core.types import CognitiveEvent, ConsolidationReport, DreamEntry, EventTopic

logger = logging.getLogger(__name__)

# Default intervals
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

        # Status tracking
        self._last_report: ConsolidationReport | None = None
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
            try:
                logger.info("Light consolidation tick")
                report = await self._run_light()
                self._last_report = report
                self._last_light_at = datetime.now(timezone.utc)
                self._next_light_at = self._last_light_at + timedelta(
                    seconds=self._light_interval
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("Light consolidation error: %s", exc)

    async def _deep_loop(self) -> None:
        logger.info("Deep (REM) heartbeat started (interval=%ds)", self._deep_interval)
        while self._running:
            self._next_deep_at = datetime.now(timezone.utc) + timedelta(
                seconds=self._deep_interval
            )
            await asyncio.sleep(self._deep_interval)
            if not self._running:
                break
            try:
                logger.info("REM consolidation tick")
                report = await self._run_deep()
                self._last_report = report
                self._last_deep_at = datetime.now(timezone.utc)
                self._next_deep_at = self._last_deep_at + timedelta(
                    seconds=self._deep_interval
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("REM consolidation error: %s", exc)

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
            from echo.curiosity.engine import CuriosityEngine  # noqa: PLC0415
            new_memories = await CuriosityEngine().run_cycle()
            if new_memories:
                logger.info("Curiosity acquired %d new semantic memories", new_memories)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Curiosity cycle error: %s", exc)

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
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            ))
            logger.info(
                "Memory health: active=%d dormant=%d avg_salience=%.3f",
                total_active, dormant_count, avg_salience,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Memory health metrics collection failed: %s", exc)

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

        return report

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

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

    def stop(self) -> None:
        """Cancel both loops."""
        self._running = False
        for task in (self._light_task, self._deep_task):
            if task and not task.done():
                task.cancel()
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
        await phase.run(elapsed_seconds=0)  # consolidate without extra decay

        _meta_state = None
        try:
            from echo.core.pipeline import pipeline  # noqa: PLC0415
            if pipeline._ready:
                _meta_state = pipeline.meta_state
        except Exception:  # noqa: BLE001
            pass

        dream = await DreamPhase().run(meta_state=_meta_state)
        await DreamStore().store(dream)
        self._last_deep_at = datetime.now(timezone.utc)
        return dream

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

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
