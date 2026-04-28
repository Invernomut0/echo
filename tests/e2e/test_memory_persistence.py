"""E2E tests — memory persistence across pipeline restarts."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_memory_persists_across_restart(db):
    from echo.core.llm_client import llm

    if not await llm.is_available():
        pytest.skip("LM Studio not available")

    import unittest.mock as mock

    from echo.core.pipeline import CognitivePipeline
    from echo.core.types import MemoryEntry

    # First pipeline instance — store a memory
    p1 = CognitivePipeline()
    await p1.startup()

    entry = MemoryEntry(
        content="The sky is blue because of Rayleigh scattering.",
        importance=0.9,
        novelty=0.8,
        self_relevance=0.5,
        emotional_weight=0.1,
    )
    with mock.patch.object(p1.episodic, "store", wraps=p1.episodic.store):
        pass
    entry.compute_salience()

    # Write directly to DB (bypass embedding)
    from echo.memory.episodic import MemoryRow
    from echo.core.db import get_session_factory
    factory = get_session_factory()
    async with factory() as session:
        row = MemoryRow(
            id=entry.id,
            content=entry.content,
            memory_type=entry.memory_type.value,
            salience=entry.salience,
            decay_lambda=entry.decay_lambda,
            current_strength=1.0,
        )
        session.add(row)
        await session.commit()

    await p1.shutdown()

    # Second pipeline instance — should find the memory
    p2 = CognitivePipeline()
    await p2.startup()

    retrieved = await p2.episodic.get_by_id(entry.id)
    assert retrieved is not None
    assert retrieved.content == entry.content

    await p2.shutdown()
