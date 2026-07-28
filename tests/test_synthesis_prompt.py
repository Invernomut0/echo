"""Regression tests for synthesis-prompt rendering.

``_SYNTHESIS_TEMPLATE`` used to be formatted inline at three separate call
sites. ``str.format`` only reports a missing placeholder at runtime, so when
``{beliefs}`` was added to the template the greeting fast path in
``Orchestrator.stream`` was silently left behind: every "ciao" ended in
``KeyError: 'beliefs'`` and the UI rendered ``[Error: 'beliefs']``. The unit
suite never caught it because it exercised ``_fmt_beliefs`` directly and never
drove the fast path.

These tests close both gaps: they assert the template is rendered in exactly one
place, and they drive every streaming path end to end.
"""

from __future__ import annotations

import inspect
from string import Formatter
from typing import Any

import pytest

from echo.agents import orchestrator as orch
from echo.agents.orchestrator import (
    _SYNTHESIS_TEMPLATE,
    Orchestrator,
    _render_synthesis,
    _select_agents,
)
from echo.core.types import IdentityBelief, MetaState, WorkspaceSnapshot


@pytest.fixture
def context() -> dict[str, Any]:
    """A realistic synthesis context."""
    return {
        "beliefs": [
            IdentityBelief(content="The user's name is Lorenzo", confidence=0.55),
            IdentityBelief(
                content="I can read and write files in my own repository", confidence=0.6
            ),
        ],
        "memories": [],
        "wiki": [],
        "history": [],
    }


class TestTemplateContract:
    """The template and its renderer must never drift apart."""

    def test_renderer_supplies_every_placeholder(self, context: dict[str, Any]) -> None:
        """Adding a placeholder without updating the renderer must fail here."""
        placeholders = {
            name for _, name, _, _ in Formatter().parse(_SYNTHESIS_TEMPLATE) if name
        }
        rendered = _render_synthesis("ciao", context, "")
        assert placeholders, "template has no placeholders — test would be vacuous"
        # A missing key would have raised KeyError above; a stale one would leave
        # its braces behind in the output.
        for name in placeholders:
            assert "{" + name + "}" not in rendered

    def test_template_is_formatted_in_exactly_one_place(self) -> None:
        """Duplicated call sites are how the KeyError shipped."""
        source = inspect.getsource(orch)
        assert source.count("_SYNTHESIS_TEMPLATE.format(") == 1

    def test_renderer_tolerates_missing_context(self) -> None:
        """A turn with no retrieval results must still render."""
        rendered = _render_synthesis("ciao", None, "")
        assert "ciao" in rendered

    def test_beliefs_reach_the_prompt(self, context: dict[str, Any]) -> None:
        rendered = _render_synthesis("come ti chiami?", context, "")
        assert "The user's name is Lorenzo" in rendered
        assert "I can read and write files in my own repository" in rendered


class TestStreamingPaths:
    """Every path through ``Orchestrator.stream`` must render a full prompt."""

    @pytest.fixture
    def captured(self, monkeypatch: pytest.MonkeyPatch) -> list[list[dict[str, str]]]:
        """Capture the messages handed to the LLM without contacting one."""
        calls: list[list[dict[str, str]]] = []

        async def _fake_stream(messages, **_kwargs):  # type: ignore[no-untyped-def]
            calls.append(messages)
            yield "ok"

        monkeypatch.setattr(orch.llm, "stream_chat_with_tools", _fake_stream)
        return calls

    def test_greeting_takes_the_fast_path(self) -> None:
        """Guard: if routing changes, the test below stops covering the bug."""
        assert _select_agents("ciao") == frozenset()

    @pytest.mark.asyncio
    async def test_fast_path_renders_without_keyerror(
        self, context: dict[str, Any], captured: list[list[dict[str, str]]]
    ) -> None:
        """The exact failure the user hit: 'ciao' raised KeyError: 'beliefs'."""
        orchestrator = Orchestrator()
        deltas = [
            d
            async for d in orchestrator.stream(
                "ciao", WorkspaceSnapshot(), MetaState(), context
            )
        ]

        assert "ok" in deltas
        assert len(captured) == 1
        prompt = captured[0][-1]["content"]
        assert "The user's name is Lorenzo" in prompt
        assert "{beliefs}" not in prompt
