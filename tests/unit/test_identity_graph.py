"""Unit tests for the identity graph."""

from __future__ import annotations

import pytest

from echo.core.types import BeliefEdge, BeliefRelation, IdentityBelief
from echo.self_model.identity_graph import IdentityGraph


@pytest.mark.asyncio
async def test_add_belief(db):
    graph = IdentityGraph()
    belief = IdentityBelief(content="I value honesty above all.")
    added = await graph.add_belief(belief)
    assert added.id == belief.id
    assert graph.get_belief(belief.id) is not None


@pytest.mark.asyncio
async def test_update_confidence(db):
    graph = IdentityGraph()
    belief = IdentityBelief(content="I am curious.", confidence=0.5)
    await graph.add_belief(belief)
    ok = await graph.update_belief_confidence(belief.id, 0.2)
    assert ok
    updated = graph.get_belief(belief.id)
    assert abs(updated.confidence - 0.7) < 1e-6


@pytest.mark.asyncio
async def test_confidence_clamped(db):
    graph = IdentityGraph()
    belief = IdentityBelief(content="test", confidence=0.9)
    await graph.add_belief(belief)
    await graph.update_belief_confidence(belief.id, 0.5)
    updated = graph.get_belief(belief.id)
    assert updated.confidence <= 1.0


@pytest.mark.asyncio
async def test_add_edge(db):
    graph = IdentityGraph()
    b1 = IdentityBelief(content="I learn from mistakes.")
    b2 = IdentityBelief(content="I improve over time.")
    await graph.add_belief(b1)
    await graph.add_belief(b2)
    edge = BeliefEdge(source_id=b1.id, target_id=b2.id, relation=BeliefRelation.SUPPORTS)
    await graph.add_edge(edge)
    assert graph.graph.has_edge(b1.id, b2.id)


@pytest.mark.asyncio
async def test_coherence_score_all_supports(db):
    graph = IdentityGraph()
    beliefs = [IdentityBelief(content=f"Belief {i}") for i in range(3)]
    for b in beliefs:
        await graph.add_belief(b)
    for i in range(len(beliefs) - 1):
        edge = BeliefEdge(
            source_id=beliefs[i].id,
            target_id=beliefs[i + 1].id,
            relation=BeliefRelation.SUPPORTS,
        )
        await graph.add_edge(edge)
    score = graph.coherence_score()
    assert score == 1.0


@pytest.mark.asyncio
async def test_coherence_score_mixed(db):
    graph = IdentityGraph()
    b1 = IdentityBelief(content="A")
    b2 = IdentityBelief(content="B")
    b3 = IdentityBelief(content="C")
    for b in [b1, b2, b3]:
        await graph.add_belief(b)
    await graph.add_edge(BeliefEdge(source_id=b1.id, target_id=b2.id, relation=BeliefRelation.SUPPORTS))
    await graph.add_edge(BeliefEdge(source_id=b1.id, target_id=b3.id, relation=BeliefRelation.CONTRADICTS))
    score = graph.coherence_score()
    assert abs(score - 0.5) < 1e-6


def test_to_dict_empty():
    graph = IdentityGraph()
    d = graph.to_dict()
    assert d == {"nodes": [], "edges": []}
