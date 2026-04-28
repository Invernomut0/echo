"""Consolidation scheduler — APScheduler-based background job."""

from __future__ import annotations

import asyncio
import logging

from echo.core.config import settings

logger = logging.getLogger(__name__)


class ConsolidationScheduler:
    """Runs the consolidation phase on a configurable interval."""

    def __init__(self, interval_seconds: int | None = None) -> None:
        self._interval = interval_seconds or settings.consolidation_interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._last_report = None

    async def _loop(self) -> None:
        from echo.consolidation.sleep_phase import ConsolidationPhase

        phase = ConsolidationPhase()
        logger.info("ConsolidationScheduler started (interval=%ds)", self._interval)
        while self._running:
            await asyncio.sleep(self._interval)
            try:
                logger.info("Starting consolidation cycle")
                report = await phase.run()
                self._last_report = report
                logger.info("Consolidation done: %s", report.model_dump_json())
            except Exception as exc:  # noqa: BLE001
                logger.error("Consolidation error: %s", exc)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._running = True
            self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    async def trigger_now(self):
        """Manually trigger one consolidation cycle."""
        from echo.consolidation.sleep_phase import ConsolidationPhase

        phase = ConsolidationPhase()
        report = await phase.run()
        self._last_report = report
        return report
