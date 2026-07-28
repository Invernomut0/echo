"""Tests for ZPD topic caching in the user interest profile.

The curiosity panel polls ``GET /api/curiosity/profile`` every 8 seconds. That
endpoint called ``zpd_topics()``, which only ever cached *successful*
generations — so once the backend started returning empty completions, every
poll fired a fresh ``/v1/chat/completions`` request. On a local model whose
prompt processing outlasts the poll interval the requests also overlapped,
stacking up rather than queueing.

These tests exercise the real ``UserInterestProfile`` against a real SQLite
file; only the LLM call itself is substituted, since the point is to count how
often it happens.
"""

from __future__ import annotations

import asyncio

import pytest

from echo.curiosity import interest_profile as ip_mod
from echo.curiosity.interest_profile import (
    _ZPD_CACHE_TTL,
    _ZPD_FAILURE_TTL,
    UserInterestProfile,
)


@pytest.fixture
def profile(tmp_path, monkeypatch: pytest.MonkeyPatch) -> UserInterestProfile:
    """A profile backed by its own SQLite file, with real topics recorded."""
    monkeypatch.setattr(ip_mod, "_DB_PATH", tmp_path / "interests.db")
    # The user is never "active" in these tests — that path is covered separately.
    monkeypatch.setattr("echo.core.user_activity.is_active", lambda: False)
    return UserInterestProfile()


async def _seed(profile: UserInterestProfile) -> None:
    async with profile._get_db() as db:
        for topic in ("autonomous agents", "cognitive architectures", "vector databases"):
            await profile._upsert_topic(db, topic, 1.0)
        await db.commit()


class _CountingLLM:
    """Records how many completions were requested and what they returned."""

    def __init__(self, response: str, delay: float = 0.0) -> None:
        self.response = response
        self.delay = delay
        self.calls = 0

    async def chat(self, *_args, **_kwargs) -> str:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.response


@pytest.mark.asyncio
class TestEmptyCompletionsDoNotLoop:
    """The failure the user hit: a request every few seconds."""

    async def test_empty_response_is_cached(
        self, profile: UserInterestProfile, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _seed(profile)
        llm = _CountingLLM("")  # exactly what the backend was returning
        monkeypatch.setattr(ip_mod, "llm", llm)

        for _ in range(10):
            assert await profile.zpd_topics(n=4) == []

        assert llm.calls == 1, "each poll started a new generation"

    async def test_failure_backs_off_for_a_bounded_time(
        self, profile: UserInterestProfile, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failure must not be cached as long as a success — it should retry."""
        await _seed(profile)
        monkeypatch.setattr(ip_mod, "llm", _CountingLLM(""))
        await profile.zpd_topics()

        expires_at, _ = profile._zpd_cache
        ttl = expires_at - ip_mod._time.monotonic()
        assert _ZPD_FAILURE_TTL - 1 < ttl <= _ZPD_FAILURE_TTL
        assert ttl < _ZPD_CACHE_TTL

    async def test_llm_exception_is_cached(
        self, profile: UserInterestProfile, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _seed(profile)
        calls = 0

        async def _boom(*_args, **_kwargs) -> str:
            nonlocal calls
            calls += 1
            raise TimeoutError("read timeout")

        monkeypatch.setattr(ip_mod, "llm", type("L", (), {"chat": staticmethod(_boom)})())

        for _ in range(5):
            assert await profile.zpd_topics() == []
        assert calls == 1

    async def test_empty_profile_does_not_call_the_llm_repeatedly(
        self, profile: UserInterestProfile, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No topics recorded yet — the common state on a fresh install."""
        llm = _CountingLLM('["a", "b"]')
        monkeypatch.setattr(ip_mod, "llm", llm)

        for _ in range(5):
            assert await profile.zpd_topics() == []
        assert llm.calls == 0


@pytest.mark.asyncio
class TestConcurrency:
    async def test_overlapping_polls_share_one_generation(
        self, profile: UserInterestProfile, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prompt processing outlasts the 8 s poll interval on local models."""
        await _seed(profile)
        llm = _CountingLLM('["neuromorphic hardware", "active inference"]', delay=0.05)
        monkeypatch.setattr(ip_mod, "llm", llm)

        results = await asyncio.gather(*(profile.zpd_topics(n=2) for _ in range(8)))

        assert llm.calls == 1
        assert all(r == results[0] for r in results)
        assert "neuromorphic hardware" in results[0]


@pytest.mark.asyncio
class TestReadOnlyAccessor:
    async def test_cached_accessor_never_generates(
        self, profile: UserInterestProfile, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The polled endpoint uses this; it must not touch the LLM."""
        await _seed(profile)
        llm = _CountingLLM('["a"]')
        monkeypatch.setattr(ip_mod, "llm", llm)

        assert profile.zpd_topics_cached(n=4) == []
        assert llm.calls == 0

    async def test_cached_accessor_serves_generated_topics(
        self, profile: UserInterestProfile, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _seed(profile)
        monkeypatch.setattr(
            ip_mod, "llm", _CountingLLM('["neuromorphic hardware", "active inference"]')
        )

        generated = await profile.zpd_topics(n=2)
        assert profile.zpd_topics_cached(n=2) == generated
        assert generated

    async def test_profile_endpoint_does_not_generate(
        self, profile: UserInterestProfile, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: GET /api/curiosity/profile used to call the LLM."""
        from echo.api.routers.curiosity import get_interest_profile

        await _seed(profile)
        llm = _CountingLLM('["a"]')
        monkeypatch.setattr(ip_mod, "llm", llm)
        monkeypatch.setattr(ip_mod, "interest_profile", profile)

        for _ in range(5):
            payload = await get_interest_profile()

        assert llm.calls == 0
        assert payload["zpd_topics"] == []
        assert payload["total_topics"] == 3


@pytest.mark.asyncio
class TestUserActivity:
    async def test_zpd_skipped_while_user_is_active(
        self, profile: UserInterestProfile, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LLM budget belongs to the conversation while the user is typing."""
        await _seed(profile)
        llm = _CountingLLM('["a"]')
        monkeypatch.setattr(ip_mod, "llm", llm)
        monkeypatch.setattr("echo.core.user_activity.is_active", lambda: True)

        for _ in range(5):
            assert await profile.zpd_topics() == []
        assert llm.calls == 0

    async def test_skip_expires_sooner_than_a_failure(
        self, profile: UserInterestProfile, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Once the user goes idle, ZPD should resume promptly."""
        await _seed(profile)
        monkeypatch.setattr(ip_mod, "llm", _CountingLLM('["a"]'))
        monkeypatch.setattr("echo.core.user_activity.is_active", lambda: True)

        await profile.zpd_topics()
        expires_at, _ = profile._zpd_cache
        assert expires_at - ip_mod._time.monotonic() <= ip_mod._ZPD_SKIP_TTL
