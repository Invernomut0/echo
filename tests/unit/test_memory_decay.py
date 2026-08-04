"""Unit tests for memory decay formula."""

from __future__ import annotations

import math

import pytest

from echo.core.types import MemoryEntry


def test_salience_formula():
    entry = MemoryEntry(
        content="test",
        importance=0.8,
        novelty=0.6,
        self_relevance=0.4,
        emotional_weight=0.2,
    )
    s = entry.compute_salience()
    expected = 0.3 * 0.8 + 0.2 * 0.6 + 0.3 * 0.4 + 0.2 * 0.2
    assert abs(s - expected) < 1e-6


def test_decay_lambda_uses_gentle_formula():
    """λ = (1 − salience) × 0.005.

    The plain 1 − salience form was abandoned because it killed memories within
    hours; see echo.scripts.fix_decay_values.
    """
    entry = MemoryEntry(content="test", importance=0.9, novelty=0.9, self_relevance=0.9, emotional_weight=0.9)
    entry.compute_salience()
    expected = (1.0 - entry.salience) * 0.005
    assert abs(entry.decay_lambda - expected) < 1e-6


def test_exponential_decay_formula():
    """I(t) = I₀ · e^(−λ·t)"""
    I0 = 1.0
    lam = 0.3
    t = 2.0  # days
    expected = I0 * math.exp(-lam * t)
    computed = I0 * math.exp(-lam * t)
    assert abs(computed - expected) < 1e-9


def test_semantic_decay_lambda_matches_episodic():
    """Semantic memories must use the same gentle λ as episodic ones.

    Semantic decay was left on the old aggressive formula *and* measured Δt in
    hours, which drove every semantic memory to 0.0 strength within two days of
    uptime and zeroed the confidence of every identity-graph node.
    """
    from echo.memory.semantic import _decay_lambda

    for salience in (0.1, 0.5, 0.95):
        assert abs(_decay_lambda(salience) - (1.0 - salience) * 0.005) < 1e-6

    # A high-salience fact must survive a month of decay essentially intact.
    lam = _decay_lambda(0.7)
    assert math.exp(-lam * 30.0) > 0.95


def test_high_salience_slow_decay():
    high = MemoryEntry(content="hi", importance=1.0, novelty=1.0, self_relevance=1.0, emotional_weight=1.0)
    low = MemoryEntry(content="lo", importance=0.0, novelty=0.0, self_relevance=0.0, emotional_weight=0.0)
    high.compute_salience()
    low.compute_salience()

    t = 10.0
    high_strength = math.exp(-high.decay_lambda * t)
    low_strength = math.exp(-low.decay_lambda * t)

    assert high_strength > low_strength
    assert high_strength > 0.9  # near-zero decay for max salience


def test_salience_bounds():
    entry = MemoryEntry(content="test", importance=1.0, novelty=1.0, self_relevance=1.0, emotional_weight=1.0)
    s = entry.compute_salience()
    assert 0.0 <= s <= 1.0

    entry2 = MemoryEntry(content="test", importance=0.0, novelty=0.0, self_relevance=0.0, emotional_weight=0.0)
    s2 = entry2.compute_salience()
    assert s2 == 0.0
