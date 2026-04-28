"""Memory decay scheduler — runs in background and applies exponential decay."""

from __future__ import annotations

import asyncio
import logging

from echo.core.config import settings

logger = logging.getLogger(__name__)


class DecayScheduler:
    """Periodically applies exponential decay to episodic memories."""

    def __init__(self, interval_seconds: int | None = None) -> None:
        self._interval = interval_seconds or settings.memory_decay_interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def _run(self) -> None:
        # Import here to avoid circular at module level
        from echo.memory.episodic import EpisodicMemoryStore

        store = EpisodicMemoryStore()
        logger.info("DecayScheduler started (interval=%ds)", self._interval)
        while self._running:
            await asyncio.sleep(self._interval)
            try:
                prunable = await store.apply_decay(float(self._interval))
                if prunable > 0:
                    removed = await store.prune_weak()
                    logger.info("Decay cycle: pruned %d memories", removed)
            except Exception as exc:  # noqa: BLE001
                logger.error("Decay cycle error: %s", exc)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._running = True
            self._task = asyncio.create_task(self._run())

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
