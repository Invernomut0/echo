"""Integration tests for full interact pipeline (requires LM Studio)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_pipeline_interact(db):
    from echo.core.llm_client import llm

    if not await llm.is_available():
        pytest.skip("LM Studio not available")

    from echo.core.pipeline import CognitivePipeline

    p = CognitivePipeline()
    await p.startup()

    record = await p.interact("What is the capital of France?")

    assert record.user_input == "What is the capital of France?"
    assert len(record.assistant_response) > 0

    await p.shutdown()


@pytest.mark.asyncio
async def test_pipeline_stream(db):
    from echo.core.llm_client import llm

    if not await llm.is_available():
        pytest.skip("LM Studio not available")

    from echo.core.pipeline import CognitivePipeline

    p = CognitivePipeline()
    await p.startup()

    chunks = []
    async for delta in p.stream_interact("Tell me a one-sentence fact."):
        chunks.append(delta)

    assert len(chunks) > 0
    full = "".join(chunks)
    assert len(full) > 10

    await p.shutdown()
