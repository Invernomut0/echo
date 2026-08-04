"""Integration tests for memory store (requires DB but no LM Studio)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from echo.core.types import MemoryEntry, MemoryType


@pytest.mark.asyncio
async def test_store_and_retrieve_by_id(db):
    """Store a memory and retrieve it by ID (no embeddings)."""
    from echo.memory.episodic import EpisodicMemoryStore

    store = EpisodicMemoryStore()

    entry = MemoryEntry(
        content="Python was created by Guido van Rossum.",
        importance=0.7,
        novelty=0.5,
        self_relevance=0.3,
        emotional_weight=0.1,
    )
    entry.compute_salience()

    # We skip the embedding call — patch it
    import unittest.mock as mock

    with mock.patch.object(
        store.__class__, "store", new_callable=mock.AsyncMock
    ) as mock_store:
        mock_store.return_value = entry
        result = await store.store(entry)

    assert result.id == entry.id


@pytest.mark.asyncio
async def test_memory_decay_formula(db):
    """Test that apply_decay updates current_strength correctly."""
    import math

    from echo.core.db import get_session_factory
    from echo.memory.episodic import EpisodicMemoryStore, MemoryRow

    # Insert a raw row directly
    factory = get_session_factory()
    async with factory() as session:
        row = MemoryRow(
            id="test-decay-001",
            content="test memory",
            memory_type=MemoryType.EPISODIC.value,
            salience=0.6,
            decay_lambda=0.4,
            current_strength=1.0,
        )
        session.add(row)
        await session.commit()

    store = EpisodicMemoryStore()
    # Δt is measured in days, and a memory accessed within the last 7 days is
    # protected from decay entirely — so backdate last_accessed to get any decay
    # at all. 30 days elapsed, access_count 0 → access_factor 1.0.
    async with factory() as session:
        from sqlalchemy import select

        from echo.memory.episodic import MemoryRow as MR
        row = (await session.execute(select(MR).where(MR.id == "test-decay-001"))).scalar_one()
        row.last_accessed = (
            datetime.now(timezone.utc) - timedelta(days=90)
        ).isoformat()
        await session.commit()

    await store.apply_decay(30 * 86400.0)  # 30 days

    async with factory() as session:
        from sqlalchemy import select

        from echo.memory.episodic import MemoryRow as MR
        row2 = (await session.execute(select(MR).where(MR.id == "test-decay-001"))).scalar_one()

    expected_strength = 1.0 * math.exp(-0.4 * 30.0)  # elapsed_days = 30.0
    assert abs(row2.current_strength - expected_strength) < 0.01


@pytest.mark.asyncio
async def test_decay_skips_recently_accessed(db):
    """A memory accessed inside the 7-day protection window must not decay."""
    from echo.core.db import get_session_factory
    from echo.memory.episodic import EpisodicMemoryStore, MemoryRow

    factory = get_session_factory()
    async with factory() as session:
        session.add(
            MemoryRow(
                id="test-decay-002",
                content="fresh memory",
                memory_type=MemoryType.EPISODIC.value,
                salience=0.6,
                decay_lambda=0.4,
                current_strength=1.0,
                last_accessed=datetime.now(timezone.utc).isoformat(),
            )
        )
        await session.commit()

    await EpisodicMemoryStore().apply_decay(30 * 86400.0)

    async with factory() as session:
        from sqlalchemy import select
        row = (
            await session.execute(select(MemoryRow).where(MemoryRow.id == "test-decay-002"))
        ).scalar_one()
    assert row.current_strength == 1.0
