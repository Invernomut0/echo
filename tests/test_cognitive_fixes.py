"""Tests for the v0.5.10 cognitive-subsystem fixes.

Each class covers one defect found during the optimisation audit, asserting the
behaviour that was previously wrong rather than merely exercising the new code.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone

import pytest

from echo.core.types import BeliefRelation, IdentityBelief, MemoryEntry, MemoryType
from echo.curiosity.engine import _dedup_tokens, _is_duplicate_text, _source_url
from echo.memory.wiki import WikiStore
from echo.self_model.identity_graph import IdentityGraph


def _memory(content: str) -> MemoryEntry:
    return MemoryEntry(content=content, memory_type=MemoryType.SEMANTIC)


class TestCuriosityDeduplication:
    """The old window-based check both missed and invented duplicates.

    The previous heuristic compared only words 2–12 of each finding. Since every
    finding starts with ``Title:`` and ends that window with ``Summary:``, two
    free matches were guaranteed, and three more shared title words were enough
    to discard a genuinely new result.
    """

    def _old_heuristic(self, new_content: str, existing: list[MemoryEntry]) -> bool:
        """The pre-0.5.10 implementation, kept to prove the tests discriminate."""
        new_words = set(new_content.lower().split()[2:12])
        return any(
            len(new_words & set(m.content.lower().split()[2:12])) >= 5 for m in existing
        )

    def test_distinct_surveys_are_no_longer_false_positives(self) -> None:
        stored = _memory(
            "[Curiosity: ml] Title: A survey of deep learning for medical imaging\n"
            "Summary: Reviews convolutional architectures applied to radiology datasets.\n"
            "Source: https://arxiv.org/abs/1111"
        )
        candidate = (
            "[Curiosity: ml] Title: A survey of deep learning for speech recognition\n"
            "Summary: Reviews recurrent architectures applied to phoneme transcription.\n"
            "Source: https://arxiv.org/abs/2222"
        )
        assert self._old_heuristic(candidate, [stored]) is True, "test no longer discriminates"
        assert _is_duplicate_text(candidate, [stored]) is False

    def test_same_page_under_another_topic_is_now_caught(self) -> None:
        stored = _memory(
            "[Curiosity: rust] Title: Ownership model\n"
            "Summary: Borrow checker fundamentals explained for newcomers.\n"
            "Source: https://example.org/rust/ownership"
        )
        candidate = (
            "[Curiosity: memory safety] Title: Completely unrelated phrasing chosen here\n"
            "Summary: Nothing lexically common whatsoever between these two entries.\n"
            "Source: https://example.org/rust/ownership/"
        )
        assert self._old_heuristic(candidate, [stored]) is False, "test no longer discriminates"
        assert _is_duplicate_text(candidate, [stored]) is True

    def test_identical_finding_under_a_longer_prefix_is_caught(self) -> None:
        body = (
            "Title: Sparse attention reduces cost\n"
            "Summary: Blocks of sparse attention cut quadratic scaling substantially.\n"
            "Source: https://a.example/one"
        )
        stored = _memory(f"[Curiosity: transformers] {body}")
        candidate = f"[Curiosity: efficiency and long context windows] {body}"
        assert _is_duplicate_text(candidate, [stored]) is True

    def test_unrelated_findings_are_not_duplicates(self) -> None:
        stored = _memory(
            "[Curiosity: gardening] Title: Companion planting basics\n"
            "Summary: Pairing vegetables to deter pests without pesticides.\n"
            "Source: https://g.example/a"
        )
        candidate = (
            "[Curiosity: databases] Title: Write-ahead logging explained\n"
            "Summary: Durability achieved by journalling before mutation of pages.\n"
            "Source: https://d.example/b"
        )
        assert _is_duplicate_text(candidate, [stored]) is False

    def test_structural_noise_is_excluded_from_tokens(self) -> None:
        tokens = _dedup_tokens(
            "[Curiosity: a very long topic name] Title: quantum annealing\n"
            "Source: https://example.org/quantum"
        )
        assert "quantum" in tokens
        assert "curiosity" not in tokens
        assert "title" not in tokens
        assert "example" not in tokens, "the Source line must not feed lexical overlap"

    def test_source_url_extraction(self) -> None:
        assert _source_url("Source: https://a.example/x/") == "https://a.example/x"
        assert _source_url("no source line here") is None

    def test_empty_candidate_is_never_duplicate(self) -> None:
        assert _is_duplicate_text("", [_memory("[Curiosity: x] Title: y")]) is False


class TestContradictionRetirement:
    """A belief beaten down by contradictions must actually be removed."""

    @pytest.fixture
    def graph(self) -> IdentityGraph:
        g = IdentityGraph()
        g._loaded = True
        return g

    def _add(self, graph: IdentityGraph, belief: IdentityBelief) -> None:
        graph.graph.add_node(belief.id, belief=belief)

    @pytest.mark.asyncio
    async def test_losing_belief_is_retired(self, graph: IdentityGraph, monkeypatch) -> None:
        old = IdentityBelief(content="ECHO prefers terse answers", confidence=0.18)
        old.created_at = datetime.now(timezone.utc) - timedelta(days=5)
        new = IdentityBelief(content="ECHO prefers detailed answers", confidence=0.8)

        self._add(graph, old)
        self._add(graph, new)
        graph.graph.add_edge(new.id, old.id, relation=BeliefRelation.CONTRADICTS.value)

        async def _fake_update(belief_id: str, delta: float) -> bool:
            graph.graph.nodes[belief_id]["belief"].confidence += delta
            return True

        deleted: list[list[str]] = []

        async def _fake_retire(ids: list[str]) -> None:
            deleted.append(list(ids))
            for i in ids:
                if graph.graph.has_node(i):
                    graph.graph.remove_node(i)

        monkeypatch.setattr(graph, "update_belief_confidence", _fake_update)
        monkeypatch.setattr(graph, "_retire_beliefs", _fake_retire)

        await graph.resolve_contradictions()

        assert deleted == [[old.id]], "contradicted belief was not retired"
        assert not graph.graph.has_node(old.id)
        assert graph.graph.has_node(new.id), "the winning belief must survive"

    @pytest.mark.asyncio
    async def test_load_bearing_belief_is_kept(self, graph: IdentityGraph, monkeypatch) -> None:
        """A weak belief that still supports another is structure, not noise."""
        old = IdentityBelief(content="ECHO prefers terse answers", confidence=0.18)
        old.created_at = datetime.now(timezone.utc) - timedelta(days=5)
        new = IdentityBelief(content="ECHO prefers detailed answers", confidence=0.8)
        third = IdentityBelief(content="ECHO adapts to context", confidence=0.6)

        for b in (old, new, third):
            self._add(graph, b)
        graph.graph.add_edge(new.id, old.id, relation=BeliefRelation.CONTRADICTS.value)
        graph.graph.add_edge(old.id, third.id, relation=BeliefRelation.SUPPORTS.value)

        async def _fake_update(belief_id: str, delta: float) -> bool:
            graph.graph.nodes[belief_id]["belief"].confidence += delta
            return True

        retired: list[list[str]] = []

        async def _fake_retire(ids: list[str]) -> None:
            retired.append(list(ids))

        monkeypatch.setattr(graph, "update_belief_confidence", _fake_update)
        monkeypatch.setattr(graph, "_retire_beliefs", _fake_retire)

        await graph.resolve_contradictions()

        assert retired == []
        assert graph.graph.has_node(old.id)

    def test_only_contradicted_detects_supporting_edges(self, graph: IdentityGraph) -> None:
        a = IdentityBelief(content="a", confidence=0.5)
        b = IdentityBelief(content="b", confidence=0.5)
        for x in (a, b):
            self._add(graph, x)

        graph.graph.add_edge(a.id, b.id, relation=BeliefRelation.CONTRADICTS.value)
        assert graph._only_contradicted(a.id) is True

        graph.graph.add_edge(b.id, a.id, relation=BeliefRelation.SUPPORTS.value)
        assert graph._only_contradicted(a.id) is False


class TestSemanticEdgeCache:
    """to_dict() polling must not recompute an O(n^2) similarity matrix."""

    def _graph_with(self, n: int) -> IdentityGraph:
        g = IdentityGraph()
        g._loaded = True
        for i in range(n):
            b = IdentityBelief(
                content=f"ECHO values structured reasoning about topic number {i}",
                confidence=0.5,
            )
            g.graph.add_node(b.id, belief=b)
        return g

    def test_second_call_is_served_from_cache(self, monkeypatch) -> None:
        g = self._graph_with(12)
        calls = {"n": 0}
        original = g._compute_semantic_edges_uncached

        def _counting():
            calls["n"] += 1
            return original()

        monkeypatch.setattr(g, "_compute_semantic_edges_uncached", _counting)

        first = g.compute_semantic_edges()
        second = g.compute_semantic_edges()

        assert calls["n"] == 1
        assert first == second

    def test_cache_invalidates_when_a_belief_changes(self, monkeypatch) -> None:
        g = self._graph_with(6)
        calls = {"n": 0}
        original = g._compute_semantic_edges_uncached

        def _counting():
            calls["n"] += 1
            return original()

        monkeypatch.setattr(g, "_compute_semantic_edges_uncached", _counting)

        g.compute_semantic_edges()
        node_id = next(iter(g.graph.nodes))
        g.graph.nodes[node_id]["belief"].confidence = 0.99
        g.compute_semantic_edges()

        assert calls["n"] == 2, "cache did not notice a confidence change"

    def test_cache_invalidates_when_a_belief_is_added(self, monkeypatch) -> None:
        g = self._graph_with(4)
        calls = {"n": 0}
        original = g._compute_semantic_edges_uncached

        def _counting():
            calls["n"] += 1
            return original()

        monkeypatch.setattr(g, "_compute_semantic_edges_uncached", _counting)

        g.compute_semantic_edges()
        extra = IdentityBelief(content="ECHO values something entirely new", confidence=0.4)
        g.graph.add_node(extra.id, belief=extra)
        g.compute_semantic_edges()

        assert calls["n"] == 2


class TestWikiLogAppend:
    """log.md must be appended to, not rewritten, and read from the tail."""

    def test_append_does_not_rewrite_the_file(self, tmp_path) -> None:
        store = WikiStore(root=tmp_path)
        store.startup()

        store._append_log("op", "first entry")
        after_first = store._log.read_text(encoding="utf-8")
        store._append_log("op", "second entry")
        after_second = store._log.read_text(encoding="utf-8")

        assert after_second.startswith(after_first), "existing content was rewritten"
        assert "first entry" in after_second
        assert "second entry" in after_second

    def test_get_log_returns_recent_entries(self, tmp_path) -> None:
        store = WikiStore(root=tmp_path)
        store.startup()
        for i in range(40):
            store._append_log("op", f"entry-{i}")

        tail = store.get_log(last_n=5)

        assert "entry-39" in tail
        assert "entry-0" not in tail

    def test_get_log_handles_a_log_larger_than_the_tail_window(self, tmp_path) -> None:
        store = WikiStore(root=tmp_path)
        store.startup()
        for i in range(400):
            store._append_log("op", f"padding-{i} " + "x" * 500)

        tail = store.get_log(last_n=3)

        assert "padding-399" in tail
        assert len(tail) < store._log.stat().st_size


class TestBoundedBuffers:
    """Pending queues are deques, so overflow is O(1) and bounded."""

    def test_wiki_queue_is_a_bounded_deque(self, tmp_path) -> None:
        store = WikiStore(root=tmp_path)
        assert isinstance(store._pending_interactions, deque)
        assert store._pending_interactions.maxlen == 20

    def test_wiki_queue_drops_oldest_on_overflow(self, tmp_path) -> None:
        store = WikiStore(root=tmp_path)
        for i in range(25):
            store.queue_interaction(f"question number {i} with enough text", "a reply that is long enough")

        assert store.pending_interaction_count() == 20
        joined = "\n".join(store._pending_interactions)
        assert "question number 24" in joined
        assert "question number 0 " not in joined
