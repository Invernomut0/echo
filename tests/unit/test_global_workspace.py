"""Unit tests for the global workspace competition."""

from __future__ import annotations

import pytest

from echo.workspace.global_workspace import GlobalWorkspace


def test_capacity_eviction():
    ws = GlobalWorkspace(max_slots=3)
    for i in range(5):
        ws.broadcast(f"item {i}", f"agent_{i}", salience=float(i) / 4)
    assert len(ws.snapshot.items) == 3


def test_highest_score_retained():
    ws = GlobalWorkspace(max_slots=2)
    ws.broadcast("low", "agent_low", salience=0.1)
    ws.broadcast("mid", "agent_mid", salience=0.5)
    ws.broadcast("high", "agent_high", salience=0.9)
    contents = [item.content for item in ws.snapshot.items]
    assert "high" in contents
    assert "mid" in contents
    assert "low" not in contents


def test_competition_scores_present():
    ws = GlobalWorkspace(max_slots=5)
    ws.broadcast("test item", "analyst", salience=0.7, routing_weight=1.5)
    scores = ws.competition_scores()
    assert "analyst" in scores
    assert scores["analyst"] > 0.7


def test_clear():
    ws = GlobalWorkspace()
    ws.broadcast("item", "agent", salience=0.5)
    ws.clear()
    assert len(ws.snapshot.items) == 0
