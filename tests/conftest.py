"""Shared pytest fixtures."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

# Point DB to tmp dirs during tests
_tmp_dir = tempfile.mkdtemp(prefix="echo_test_")


def pytest_configure(config):
    os.environ.setdefault("SQLITE_PATH", str(Path(_tmp_dir) / "test.db"))
    os.environ.setdefault("CHROMA_PATH", str(Path(_tmp_dir) / "chroma"))
    os.environ.setdefault("CONSOLIDATION_INTERVAL_SECONDS", "9999")
    os.environ.setdefault("MEMORY_DECAY_INTERVAL_SECONDS", "9999")


@pytest.fixture
async def db():
    """Initialise the DB for each test."""
    from echo.core.db import Base, _get_engine, init_db

    await init_db()
    yield
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def meta_state():
    from echo.core.types import MetaState

    return MetaState()


@pytest.fixture
def sample_memory():
    from echo.core.types import MemoryEntry

    entry = MemoryEntry(
        content="The capital of France is Paris.",
        importance=0.8,
        novelty=0.6,
        self_relevance=0.4,
        emotional_weight=0.1,
    )
    entry.compute_salience()
    return entry


def lm_studio_required(func):
    """Decorator to skip test if LM Studio is not available."""
    import asyncio
    import functools

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        from echo.core.llm_client import llm

        if not await llm.is_available():
            pytest.skip("LM Studio not available at localhost:1234")
        return await func(*args, **kwargs)

    return wrapper
