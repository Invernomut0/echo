"""Integration tests for consolidation (requires LM Studio)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_consolidation_with_memories(db):
    from echo.core.llm_client import llm

    if not await llm.is_available():
        pytest.skip("LM Studio not available")

    import unittest.mock as mock

    from echo.consolidation.sleep_phase import ConsolidationPhase
    from echo.core.types import MemoryEntry, MemoryType
    from echo.memory.episodic import EpisodicMemoryStore, MemoryRow
    from echo.core.db import get_session_factory

    # Seed some memories directly into DB
    factory = get_session_factory()
    async with factory() as session:
        for i in range(5):
            row = MemoryRow(
                id=f"cons-test-{i:03d}",
                content=f"Test memory {i}: I observed something interesting about the world.",
                memory_type=MemoryType.EPISODIC.value,
                salience=0.8 if i < 3 else 0.3,
                decay_lambda=0.2,
                current_strength=1.0,
            )
            session.add(row)
        await session.commit()

    phase = ConsolidationPhase()
    report = await phase.run()

    assert report.memories_processed >= 5
    assert report.finished_at is not None
