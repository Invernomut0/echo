"""Unit tests for the event bus."""

from __future__ import annotations

import asyncio

import pytest

from echo.core.event_bus import EventBus
from echo.core.types import CognitiveEvent, EventTopic


@pytest.mark.asyncio
async def test_publish_and_receive():
    bus = EventBus()
    received = []

    async def consumer():
        async for event in bus.subscribe(EventTopic.USER_INPUT):
            received.append(event)
            break  # only wait for one

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0)  # yield to let consumer start

    event = CognitiveEvent(topic=EventTopic.USER_INPUT, payload={"text": "hello"})
    await bus.publish(event)

    await asyncio.wait_for(task, timeout=2.0)
    assert len(received) == 1
    assert received[0].payload["text"] == "hello"


@pytest.mark.asyncio
async def test_wildcard_subscriber():
    bus = EventBus()
    received = []

    async def consumer():
        async for event in bus.subscribe():
            received.append(event)
            if len(received) >= 2:
                break

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0)

    await bus.publish(CognitiveEvent(topic=EventTopic.USER_INPUT, payload={}))
    await bus.publish(CognitiveEvent(topic=EventTopic.REFLECTION_COMPLETE, payload={}))

    await asyncio.wait_for(task, timeout=2.0)
    assert len(received) == 2


@pytest.mark.asyncio
async def test_no_subscribers_no_error():
    bus = EventBus()
    # Should not raise
    await bus.publish(CognitiveEvent(topic=EventTopic.MEMORY_STORE, payload={}))


@pytest.mark.asyncio
async def test_subscriber_count():
    bus = EventBus()
    assert bus.subscriber_count(EventTopic.USER_INPUT) == 0

    async def consumer():
        async for _ in bus.subscribe(EventTopic.USER_INPUT):
            break

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0)
    assert bus.subscriber_count(EventTopic.USER_INPUT) == 1
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, StopAsyncIteration):
        pass
