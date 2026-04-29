"""Async publish/subscribe event bus backed by asyncio.Queue per topic."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import AsyncGenerator
from typing import Any

from echo.core.types import CognitiveEvent, EventTopic

logger = logging.getLogger(__name__)


class EventBus:
    """Lightweight asyncio pub/sub bus.

    Usage::

        bus = EventBus()

        # producer
        await bus.publish(CognitiveEvent(topic=EventTopic.USER_INPUT, payload={"text": "hi"}))

        # consumer
        async for event in bus.subscribe(EventTopic.USER_INPUT):
            ...
    """

    def __init__(self) -> None:
        # topic → list of queues (one per subscriber)
        self._subscribers: dict[EventTopic, list[asyncio.Queue[CognitiveEvent]]] = defaultdict(
            list
        )
        # wildcard subscribers receive every event
        self._wildcard: list[asyncio.Queue[CognitiveEvent]] = []

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def publish(self, event: CognitiveEvent) -> None:
        queues = self._subscribers.get(event.topic, []) + self._wildcard
        if not queues:
            logger.debug("No subscribers for topic %s", event.topic)
            return
        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "Queue full for topic %s — dropping event %s", event.topic, event.id
                )

    def publish_sync(self, event: CognitiveEvent) -> None:
        """Fire-and-forget from sync context (schedules coroutine on running loop)."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.publish(event))
        except RuntimeError:
            # no running loop — best-effort
            pass

    # ------------------------------------------------------------------
    # Subscribing
    # ------------------------------------------------------------------

    async def subscribe(
        self,
        *topics: EventTopic,
        maxsize: int = 256,
    ) -> AsyncGenerator[CognitiveEvent, None]:
        """Async generator that yields events for the given topics."""
        q: asyncio.Queue[CognitiveEvent] = asyncio.Queue(maxsize=maxsize)

        if topics:
            for topic in topics:
                self._subscribers[topic].append(q)
        else:
            self._wildcard.append(q)

        try:
            while True:
                event = await q.get()
                yield event
                q.task_done()
        finally:
            if topics:
                for topic in topics:
                    try:
                        self._subscribers[topic].remove(q)
                    except ValueError:
                        pass
            else:
                try:
                    self._wildcard.remove(q)
                except ValueError:
                    pass

    async def subscribe_once(
        self,
        topic: EventTopic,
        timeout: float | None = None,
    ) -> CognitiveEvent | None:
        """Await the next event on ``topic`` and auto-unsubscribe.

        Unlike ``subscribe()``, the queue is removed from ``_subscribers``
        immediately after the first event is received (or on timeout/error),
        preventing the unbounded queue leak present in the old sync variant.

        Args:
            topic:   The event topic to listen on.
            timeout: Optional seconds to wait before giving up. Returns ``None``
                     on timeout.
        """
        q: asyncio.Queue[CognitiveEvent] = asyncio.Queue(maxsize=64)
        self._subscribers[topic].append(q)
        try:
            if timeout is not None:
                return await asyncio.wait_for(q.get(), timeout=timeout)
            return await q.get()
        except asyncio.TimeoutError:
            return None
        finally:
            # Always remove the queue — even on exception or cancellation.
            try:
                self._subscribers[topic].remove(q)
            except ValueError:
                pass

    def prune_stale_queues(self, threshold: int = 200) -> int:
        """Remove queues that are full beyond *threshold* items (dead listeners).

        A queue that is nearly or completely full has stopped being consumed —
        its listener likely crashed or was abandoned without closing the async
        generator.  Pruning prevents unbounded memory growth.

        Returns the number of queues removed.
        """
        pruned = 0
        for topic in list(self._subscribers):
            stale = [q for q in self._subscribers[topic] if q.qsize() >= threshold]
            for q in stale:
                self._subscribers[topic].remove(q)
                pruned += 1
                logger.warning(
                    "Pruned stale queue for topic %s (size=%d)", topic, q.qsize()
                )
            # Clean up empty lists to keep the dict tidy
            if not self._subscribers[topic]:
                del self._subscribers[topic]
        return pruned

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def subscriber_count(self, topic: EventTopic | None = None) -> int:
        if topic is None:
            return sum(len(v) for v in self._subscribers.values()) + len(self._wildcard)
        return len(self._subscribers.get(topic, []))

    def emit(
        self,
        topic: EventTopic,
        payload: dict[str, Any],
        source_agent: str = "system",
    ) -> None:
        """Convenience: build and publish an event synchronously."""
        event = CognitiveEvent(topic=topic, payload=payload, source_agent=source_agent)
        self.publish_sync(event)


# Module-level singleton
bus: EventBus = EventBus()
