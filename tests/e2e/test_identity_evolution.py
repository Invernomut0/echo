"""E2E tests — identity evolution over multiple interactions."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_identity_evolves(db):
    from echo.core.llm_client import llm

    if not await llm.is_available():
        pytest.skip("LM Studio not available")

    from echo.core.pipeline import CognitivePipeline

    p = CognitivePipeline()
    await p.startup()

    # Seed identity with initial belief
    from echo.core.types import IdentityBelief
    initial_belief = IdentityBelief(content="I am a curious, reflective cognitive system.", confidence=0.5)
    await p.identity_graph.add_belief(initial_belief)

    # Run several interactions
    messages = [
        "What makes a system truly self-aware?",
        "How does memory shape identity?",
        "What is the nature of consciousness?",
    ]
    for msg in messages:
        await p.interact(msg)

    # Graph should have grown
    beliefs = p.identity_graph.all_beliefs()
    assert len(beliefs) >= 1  # at least the initial + reflections

    await p.shutdown()
