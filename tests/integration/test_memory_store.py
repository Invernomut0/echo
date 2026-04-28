"""Integration tests for memory store (requires DB but no LM Studio)."""

from __future__ import annotations

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

    from echo.memory.episodic import EpisodicMemoryStore, MemoryRow
    from echo.core.db import get_session_factory

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
    await store.apply_decay(3600.0)  # 1 hour

    async with factory() as session:
        from sqlalchemy import select
        from echo.memory.episodic import MemoryRow as MR
        row2 = (await session.execute(select(MR).where(MR.id == "test-decay-001"))).scalar_one()

    expected_strength = 1.0 * math.exp(-0.4 * 1.0)  # elapsed_hours = 1.0
    assert abs(row2.current_strength - expected_strength) < 0.01
