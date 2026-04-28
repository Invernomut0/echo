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

    def subscribe_once(
        self, topic: EventTopic, maxsize: int = 64
    ) -> asyncio.Queue[CognitiveEvent]:
        """Return a queue that will receive the next event for `topic`."""
        q: asyncio.Queue[CognitiveEvent] = asyncio.Queue(maxsize=maxsize)
        self._subscribers[topic].append(q)
        return q

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
