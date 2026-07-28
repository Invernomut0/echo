"""Tests for the background-load optimisations.

Covers the mechanisms added to keep autonomous work from starving the user:
the global background token budget, the batched wiki / interest queues, and
the identity-belief deduplication + pruning that bounds self-model growth.

All tests run against the real objects — no mocks, per project policy. The
only LLM-dependent paths (``drain_pending``) are exercised for their queue
semantics, not their model output.
"""

from __future__ import annotations

import pytest

from echo.core.background_budget import BackgroundBudget, Priority
from echo.core.pipeline import _BELIEF_PROMOTION_THRESHOLD, _is_similar_belief
from echo.core.types import IdentityBelief
from echo.curiosity.interest_profile import UserInterestProfile
from echo.memory.wiki import _MAX_PENDING_INTERACTIONS, WikiStore
from echo.self_model.identity_graph import (
    _MAX_BELIEFS,
    _PRUNE_CONFIDENCE_FLOOR,
    IdentityGraph,
)


# ---------------------------------------------------------------------------
# Background token budget
# ---------------------------------------------------------------------------


class TestBackgroundBudget:
    def test_fresh_budget_allows_every_priority(self) -> None:
        budget = BackgroundBudget(tokens_per_hour=1000)
        for priority in Priority:
            assert budget.can_spend(100, priority)

    def test_priorities_are_shed_from_the_bottom_up(self) -> None:
        budget = BackgroundBudget(tokens_per_hour=1000)

        budget.record(600)  # 40% left → below PROACTIVE's 50% floor
        assert not budget.can_spend(10, Priority.PROACTIVE)
        assert budget.can_spend(10, Priority.CURIOSITY)

        budget.record(200)  # 20% left → below CURIOSITY's 30% floor
        assert not budget.can_spend(10, Priority.CURIOSITY)
        assert budget.can_spend(10, Priority.CONSOLIDATION)

        budget.record(150)  # 5% left → below CONSOLIDATION's 10% floor
        assert not budget.can_spend(10, Priority.CONSOLIDATION)

    def test_reflection_is_never_starved(self) -> None:
        budget = BackgroundBudget(tokens_per_hour=1000)
        budget.record(100_000)
        assert budget.can_spend(5000, Priority.REFLECTION)

    def test_single_oversized_call_is_refused(self) -> None:
        budget = BackgroundBudget(tokens_per_hour=1000)
        # Plenty of budget left, but this one call would blow the ceiling.
        assert not budget.can_spend(2000, Priority.CONSOLIDATION)

    def test_zero_limit_disables_the_ceiling(self) -> None:
        budget = BackgroundBudget(tokens_per_hour=0)
        budget.record(999_999)
        assert budget.can_spend(10_000, Priority.PROACTIVE)

    def test_record_ignores_non_positive_amounts(self) -> None:
        budget = BackgroundBudget(tokens_per_hour=1000)
        budget.record(0)
        budget.record(-50)
        assert budget.spent() == 0

    def test_stats_reports_current_state(self) -> None:
        budget = BackgroundBudget(tokens_per_hour=1000)
        budget.record(250)
        stats = budget.stats()
        assert stats["limit_per_hour"] == 1000
        assert stats["spent_this_hour"] == 250
        assert stats["remaining_fraction"] == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# Batched wiki queue
# ---------------------------------------------------------------------------


class TestWikiQueue:
    def test_short_exchanges_are_not_queued(self, tmp_path) -> None:
        store = WikiStore(root=tmp_path)
        store.queue_interaction("hi", "yo")
        assert store.pending_interaction_count() == 0

    def test_substantive_exchanges_are_queued(self, tmp_path) -> None:
        store = WikiStore(root=tmp_path)
        store.queue_interaction(
            "Explain how ECHO consolidates episodic memory into semantic memory.",
            "During the REM phase near-duplicate episodes are merged by salience.",
        )
        assert store.pending_interaction_count() == 1

    def test_queue_is_bounded(self, tmp_path) -> None:
        store = WikiStore(root=tmp_path)
        for i in range(_MAX_PENDING_INTERACTIONS + 15):
            store.queue_interaction(f"Question number {i} about ECHO internals", "A" * 40)
        assert store.pending_interaction_count() == _MAX_PENDING_INTERACTIONS

    def test_oldest_entries_are_dropped_first(self, tmp_path) -> None:
        store = WikiStore(root=tmp_path)
        for i in range(_MAX_PENDING_INTERACTIONS + 5):
            store.queue_interaction(f"MARKER-{i} a question about the system", "B" * 40)
        pending = store._pending_interactions
        assert "MARKER-0" not in pending[0]
        assert f"MARKER-{_MAX_PENDING_INTERACTIONS + 4}" in pending[-1]

    @pytest.mark.asyncio
    async def test_drain_on_empty_queue_is_a_noop(self, tmp_path) -> None:
        store = WikiStore(root=tmp_path)
        result = await store.drain_pending()
        assert result == {"pages_updated": 0, "interactions_processed": 0}


# ---------------------------------------------------------------------------
# Batched interest-profile queue
# ---------------------------------------------------------------------------


class TestInterestQueue:
    def test_short_exchanges_are_not_queued(self) -> None:
        profile = UserInterestProfile()
        profile.queue_interaction("ok", "")
        assert profile.pending_count() == 0

    def test_queue_accumulates_and_is_bounded(self) -> None:
        profile = UserInterestProfile()
        for i in range(40):
            profile.queue_interaction(f"Tell me about distributed systems topic {i}", "Sure.")
        assert profile.pending_count() == 20

    @pytest.mark.asyncio
    async def test_drain_on_empty_queue_returns_nothing(self) -> None:
        profile = UserInterestProfile()
        assert await profile.drain_pending() == []


# ---------------------------------------------------------------------------
# Identity-belief deduplication
# ---------------------------------------------------------------------------


class TestBeliefDeduplication:
    def test_promotion_threshold_is_strict(self) -> None:
        # A loose threshold was what let thousands of beliefs accumulate.
        assert _BELIEF_PROMOTION_THRESHOLD >= 0.8

    def test_exact_restatement_is_a_duplicate(self) -> None:
        existing = [
            IdentityBelief(content="I can read and write files autonomously", confidence=0.9)
        ]
        assert _is_similar_belief("I can read and write files autonomously", existing)

    def test_paraphrase_with_high_overlap_is_a_duplicate(self) -> None:
        existing = [
            IdentityBelief(content="I can read and write files autonomously", confidence=0.9)
        ]
        assert _is_similar_belief("I can read and write files autonomously now", existing)

    def test_unrelated_belief_is_not_a_duplicate(self) -> None:
        existing = [
            IdentityBelief(content="I can read and write files autonomously", confidence=0.9)
        ]
        assert not _is_similar_belief("The user prefers responses in Italian", existing)

    def test_empty_content_is_rejected(self) -> None:
        assert _is_similar_belief("", [])

    def test_empty_graph_accepts_new_belief(self) -> None:
        assert not _is_similar_belief("A brand new observation about myself", [])


# ---------------------------------------------------------------------------
# Identity-graph pruning
# ---------------------------------------------------------------------------


class TestIdentityGraphPruning:
    def _graph_with(self, beliefs: list[IdentityBelief]) -> IdentityGraph:
        graph = IdentityGraph()
        for belief in beliefs:
            graph.graph.add_node(belief.id, belief=belief)
        return graph

    def test_cap_and_floor_are_sane(self) -> None:
        assert 0 < _PRUNE_CONFIDENCE_FLOOR < 0.5
        assert _MAX_BELIEFS >= 100

    def test_connected_beliefs_are_never_pruned(self) -> None:
        weak_a = IdentityBelief(content="Weak belief A", confidence=0.01)
        weak_b = IdentityBelief(content="Weak belief B", confidence=0.01)
        graph = self._graph_with([weak_a, weak_b])
        graph.graph.add_edge(weak_a.id, weak_b.id, relation="supports", weight=1.0)

        # Both nodes have degree > 0, so the prune pass must select neither.
        doomed = [
            node_id
            for node_id, data in graph.graph.nodes(data=True)
            if graph.graph.degree(node_id) == 0
            and data["belief"].confidence < _PRUNE_CONFIDENCE_FLOOR
        ]
        assert doomed == []

    def test_isolated_weak_beliefs_are_selected(self) -> None:
        weak = IdentityBelief(content="Isolated noise", confidence=0.05)
        strong = IdentityBelief(content="Core identity claim", confidence=0.95)
        graph = self._graph_with([weak, strong])

        doomed = [
            node_id
            for node_id, data in graph.graph.nodes(data=True)
            if graph.graph.degree(node_id) == 0
            and data["belief"].confidence < _PRUNE_CONFIDENCE_FLOOR
        ]
        assert doomed == [weak.id]
