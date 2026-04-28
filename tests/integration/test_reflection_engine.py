"""Integration tests for reflection engine (requires LM Studio)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_reflection_produces_insights(db):
    from echo.core.llm_client import llm

    if not await llm.is_available():
        pytest.skip("LM Studio not available")

    from echo.core.types import MetaState
    from echo.reflection.engine import ReflectionEngine
    from echo.self_model.identity_graph import IdentityGraph

    graph = IdentityGraph()
    engine = ReflectionEngine(graph)

    result = await engine.reflect(
        interaction_id="test-001",
        user_input="Why do humans feel emotions?",
        response="Emotions evolved as adaptive signals that guide behaviour.",
        meta_state=MetaState(),
    )

    assert result.interaction_id == "test-001"
    # Should produce at least one insight or belief
    assert isinstance(result.insights, list)
    assert isinstance(result.new_beliefs, list)
