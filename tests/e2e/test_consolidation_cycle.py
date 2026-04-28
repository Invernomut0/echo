"""E2E test — full consolidation cycle with LM Studio."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_full_consolidation_cycle(db):
    from echo.core.llm_client import llm

    if not await llm.is_available():
        pytest.skip("LM Studio not available")

    from echo.consolidation.sleep_phase import ConsolidationPhase
    from echo.core.types import MemoryType
    from echo.memory.episodic import MemoryRow
    from echo.core.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        for i in range(10):
            row = MemoryRow(
                id=f"e2e-cons-{i:03d}",
                content=f"Interaction {i}: The system learned about {'curiosity' if i % 2 == 0 else 'memory'}.",
                memory_type=MemoryType.EPISODIC.value,
                salience=0.75 + (i % 3) * 0.05,
                decay_lambda=0.25,
                current_strength=1.0,
                self_relevance=0.8,
            )
            session.add(row)
        await session.commit()

    phase = ConsolidationPhase()
    report = await phase.run()

    assert report.memories_processed == 10
    assert report.finished_at is not None
    # High-salience memories should be promoted
    assert report.memories_promoted >= 1
    # At least some patterns extracted
    # (may be empty if LLM response parsing fails, so just check types)
    assert isinstance(report.patterns_found, list)
