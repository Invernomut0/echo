"""Tests for the ``echo__list_beliefs`` introspection tool.

Asked "give me the list of all the beliefs you have", ECHO could only answer
from the bounded selection in its prompt — a partial, silently truncated view.
This tool gives it real access to the identity graph.
"""

from __future__ import annotations

import json

import pytest

from echo.core.types import IdentityBelief
from echo.self_model.identity_graph import IdentityGraph
from echo.self_model.tools import _TOOLS, _make_handlers


@pytest.fixture
def graph() -> IdentityGraph:
    """A graph holding more beliefs than the prompt would ever show."""
    g = IdentityGraph()
    beliefs = [
        IdentityBelief(content=f"I am a reflective cognitive system, aspect {i}", confidence=0.95)
        for i in range(30)
    ] + [
        IdentityBelief(content="The user's name is Lorenzo", confidence=0.55),
        IdentityBelief(content="I can read and write files in my own repository", confidence=0.6),
        IdentityBelief(content="A weak hunch I am not sure about", confidence=0.12),
    ]
    for b in beliefs:
        g.graph.add_node(b.id, belief=b)
    return g


@pytest.fixture
def list_beliefs(graph: IdentityGraph):  # type: ignore[no-untyped-def]
    return _make_handlers(graph)["echo__list_beliefs"]


class TestToolDefinition:
    def test_registered_under_the_echo_namespace(self) -> None:
        names = [t["function"]["name"] for t in _TOOLS]
        assert names == ["echo__list_beliefs"]

    def test_takes_no_required_arguments(self) -> None:
        """A local model must be able to call it with '{}'."""
        assert _TOOLS[0]["function"]["parameters"]["required"] == []


class TestListBeliefs:
    @pytest.mark.asyncio
    async def test_returns_more_than_the_prompt_shows(self, list_beliefs) -> None:  # type: ignore[no-untyped-def]
        from echo.agents.orchestrator import _MAX_BELIEFS_IN_PROMPT

        result = json.loads(await list_beliefs({}))
        assert result["ok"] is True
        assert result["total_in_graph"] == 33
        assert result["returned"] > _MAX_BELIEFS_IN_PROMPT

    @pytest.mark.asyncio
    async def test_sorted_by_confidence(self, list_beliefs) -> None:  # type: ignore[no-untyped-def]
        result = json.loads(await list_beliefs({}))
        confidences = [b["confidence"] for b in result["beliefs"]]
        assert confidences == sorted(confidences, reverse=True)

    @pytest.mark.asyncio
    async def test_query_filters_by_substring(self, list_beliefs) -> None:  # type: ignore[no-untyped-def]
        result = json.loads(await list_beliefs({"query": "lorenzo"}))
        assert [b["content"] for b in result["beliefs"]] == ["The user's name is Lorenzo"]

    @pytest.mark.asyncio
    async def test_min_confidence_drops_weak_beliefs(self, list_beliefs) -> None:  # type: ignore[no-untyped-def]
        result = json.loads(await list_beliefs({"min_confidence": 0.5}))
        contents = [b["content"] for b in result["beliefs"]]
        assert "A weak hunch I am not sure about" not in contents
        assert "The user's name is Lorenzo" in contents

    @pytest.mark.asyncio
    async def test_limit_is_capped(self, list_beliefs) -> None:  # type: ignore[no-untyped-def]
        result = json.loads(await list_beliefs({"limit": 5}))
        assert result["returned"] == 5
        assert result["total_in_graph"] == 33

    @pytest.mark.asyncio
    async def test_empty_graph_is_not_an_error(self) -> None:
        handler = _make_handlers(IdentityGraph())["echo__list_beliefs"]
        result = json.loads(await handler({}))
        assert result == {"ok": True, "total_in_graph": 0, "returned": 0, "beliefs": []}
