"""Regression tests for curiosity SQLite connection lifecycle."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_interest_profile_repeated_calls_do_not_raise(db):
    """Repeated profile operations must not trigger aiosqlite thread restart errors."""
    from echo.curiosity.interest_profile import UserInterestProfile

    profile = UserInterestProfile()

    await profile.mark_preferred("systems thinking")
    await profile.mark_excluded("astrology")

    for _ in range(5):
        primary = await profile.primary_interests(n=10)
        all_topics = await profile.all_topics()
        excluded = await profile.excluded_topics()

        assert isinstance(primary, list)
        assert isinstance(all_topics, list)
        assert "astrology" in excluded


@pytest.mark.asyncio
async def test_stimulus_queue_repeated_calls_do_not_raise(db):
    """Repeated queue operations must be stable across multiple DB contexts."""
    from echo.curiosity.stimulus_queue import StimulusQueue

    queue = StimulusQueue()

    sid = await queue.enqueue(
        content="A finding about graph databases and memory retrieval.",
        topic="knowledge graphs",
        affinity_score=0.82,
        source_memory_id="mem-123",
    )

    assert sid

    for _ in range(5):
        pending = await queue.pending(limit=20)
        all_items = await queue.all_items(limit=20)

        assert isinstance(pending, list)
        assert isinstance(all_items, list)

    await queue.mark_presented(sid)
    await queue.record_feedback(sid, 0.9)
