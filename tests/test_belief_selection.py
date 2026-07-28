"""Tests for identity-belief selection in the synthesis prompt.

Beliefs enter the graph at fixed confidences:

* bootstrap self-description — 0.6 (``pipeline._bootstrap_beliefs_if_empty``)
* reflection output — 0.5 (``reflection.engine``)
* facts promoted from episodic memory — ``min(0.6, salience)``
  (``consolidation.scheduler``), which is where the user's name lands

Ranking purely by confidence therefore lets abstract self-narrative — whose
confidence reflection keeps nudging upward — crowd out the concrete facts, and
ECHO ends up denying it can write files and forgetting who it is talking to.
The fixtures below reproduce that distribution.
"""

from __future__ import annotations

import pytest

from echo.agents.orchestrator import (
    _MAX_BELIEFS_IN_PROMPT,
    _MAX_PINNED_BELIEFS,
    _fmt_beliefs,
)
from echo.core.types import IdentityBelief


def _old_selection(beliefs: list[IdentityBelief]) -> str:
    """The previous implementation, kept so the tests prove a real change."""
    filtered = [b for b in beliefs if b.confidence >= 0.3]
    filtered.sort(key=lambda b: b.confidence, reverse=True)
    return "\n".join(f"- {b.content} (confidence={b.confidence:.2f})" for b in filtered[:15])


@pytest.fixture
def saturated_graph() -> list[IdentityBelief]:
    """A realistic graph: reinforced self-narrative plus the facts that matter."""
    beliefs = [
        # Reflection has repeatedly reinforced these abstract beliefs.
        IdentityBelief(content=f"I am a reflective cognitive system, aspect {i}", confidence=0.95)
        for i in range(20)
    ]
    beliefs += [
        # Auto-promoted from episodic memory — capped at min(0.6, salience).
        IdentityBelief(content="The user's name is Lorenzo", confidence=0.55),
        IdentityBelief(content="The user prefers answers in Italian", confidence=0.48),
        # Capability beliefs, seeded by bootstrap at 0.6.
        IdentityBelief(content="I can read and write files in my own repository", confidence=0.6),
        IdentityBelief(content="I can search the web when I lack information", confidence=0.52),
        IdentityBelief(content="Posso modificare il mio stesso codice sorgente", confidence=0.4),
    ]
    return beliefs


class TestPinnedBeliefsSurvive:
    """The facts ECHO was forgetting must reach the prompt."""

    def test_old_selection_loses_them(self, saturated_graph: list[IdentityBelief]) -> None:
        """Guard: without this the tests below would prove nothing."""
        rendered = _old_selection(saturated_graph)
        assert "Lorenzo" not in rendered
        assert "read and write files" not in rendered

    def test_user_name_survives(self, saturated_graph: list[IdentityBelief]) -> None:
        rendered = _fmt_beliefs({"beliefs": saturated_graph}, "chi sono io?")
        assert "The user's name is Lorenzo" in rendered

    def test_file_capability_survives(self, saturated_graph: list[IdentityBelief]) -> None:
        rendered = _fmt_beliefs({"beliefs": saturated_graph}, "ciao")
        assert "read and write files" in rendered

    def test_italian_capability_phrasing_is_recognised(
        self, saturated_graph: list[IdentityBelief]
    ) -> None:
        rendered = _fmt_beliefs({"beliefs": saturated_graph}, "ciao")
        assert "modificare il mio stesso codice" in rendered

    def test_pinned_beliefs_come_first(self, saturated_graph: list[IdentityBelief]) -> None:
        """LLMs weight earlier context more heavily."""
        rendered = _fmt_beliefs({"beliefs": saturated_graph}, "ciao")
        lines = rendered.splitlines()
        head = "\n".join(lines[:_MAX_PINNED_BELIEFS])
        assert "Lorenzo" in head
        assert "read and write files" in head

    def test_low_confidence_pinned_belief_is_kept(self) -> None:
        """A 0.2-confidence fact about the user beat the old 0.3 floor entirely."""
        beliefs = [IdentityBelief(content="The user works on embedded systems", confidence=0.2)]
        assert "embedded systems" in _fmt_beliefs({"beliefs": beliefs}, "ciao")
        assert _old_selection(beliefs) == ""


class TestRelevanceRanking:
    """Non-pinned beliefs should respond to what was actually asked."""

    def test_relevant_belief_beats_higher_confidence_noise(self) -> None:
        beliefs = [
            IdentityBelief(content=f"Unrelated conviction {i}", confidence=0.99)
            for i in range(_MAX_BELIEFS_IN_PROMPT + 5)
        ]
        beliefs.append(
            IdentityBelief(content="Recursion is best explained with base cases", confidence=0.35)
        )
        rendered = _fmt_beliefs({"beliefs": beliefs}, "spiegami la recursion")
        assert "Recursion is best explained" in rendered

    def test_no_query_still_returns_beliefs(self) -> None:
        beliefs = [IdentityBelief(content="I value intellectual honesty", confidence=0.8)]
        assert "intellectual honesty" in _fmt_beliefs({"beliefs": beliefs})


class TestCapsAndEdges:
    def test_total_cap_is_respected(self, saturated_graph: list[IdentityBelief]) -> None:
        rendered = _fmt_beliefs({"beliefs": saturated_graph}, "ciao")
        assert len(rendered.splitlines()) <= _MAX_BELIEFS_IN_PROMPT

    def test_pinned_cannot_starve_the_rest(self) -> None:
        """A graph full of user facts must still leave room for other beliefs."""
        beliefs = [
            IdentityBelief(content=f"The user mentioned topic {i}", confidence=0.9)
            for i in range(30)
        ]
        beliefs.append(IdentityBelief(content="I value precision", confidence=0.5))
        rendered = _fmt_beliefs({"beliefs": beliefs}, "ciao")
        assert "I value precision" in rendered

    def test_noise_below_the_floor_is_dropped(self) -> None:
        beliefs = [
            IdentityBelief(content="A half-formed unrelated notion", confidence=0.05),
            IdentityBelief(content="I value precision", confidence=0.8),
        ]
        rendered = _fmt_beliefs({"beliefs": beliefs}, "ciao")
        assert "half-formed" not in rendered
        assert "I value precision" in rendered

    def test_empty_inputs(self) -> None:
        assert _fmt_beliefs(None, "x") == "(none)"
        assert _fmt_beliefs({}, "x") == "(none)"
        assert _fmt_beliefs({"beliefs": []}, "x") == "(none)"

    def test_confidence_is_still_reported(self) -> None:
        beliefs = [IdentityBelief(content="The user's name is Lorenzo", confidence=0.55)]
        assert "(confidence=0.55)" in _fmt_beliefs({"beliefs": beliefs}, "ciao")

    def test_no_duplicate_lines(self, saturated_graph: list[IdentityBelief]) -> None:
        lines = _fmt_beliefs({"beliefs": saturated_graph}, "ciao").splitlines()
        assert len(lines) == len(set(lines))


class TestWorkspaceToolsAlwaysOffered:
    """ECHO's own file surface must never be filtered out of a request."""

    def test_echo_workspace_is_always_relevant(self) -> None:
        from echo.mcp.client import _ALWAYS_RELEVANT_SERVERS

        assert "echo-workspace" in _ALWAYS_RELEVANT_SERVERS

    def test_workspace_tools_survive_an_unrelated_question(self) -> None:
        from tests.test_prompt_payload import _StubManager, _realistic_toolset

        mgr = _StubManager(_realistic_toolset())
        selected = mgr.select_tools_openai("raccontami una barzelletta", max_tools=32)
        names = {t["function"]["name"] for t in selected}
        assert any(n.startswith("echo-workspace__") for n in names)
