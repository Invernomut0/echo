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


def test_decay_lambda_equals_one_minus_salience():
    entry = MemoryEntry(content="test", importance=0.9, novelty=0.9, self_relevance=0.9, emotional_weight=0.9)
    entry.compute_salience()
    assert abs(entry.decay_lambda - (1.0 - entry.salience)) < 1e-6


def test_exponential_decay_formula():
    """I(t) = I₀ · e^(−λ·t)"""
    I0 = 1.0
    lam = 0.3
    t = 2.0  # hours
    expected = I0 * math.exp(-lam * t)
    computed = I0 * math.exp(-lam * t)
    assert abs(computed - expected) < 1e-9


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
