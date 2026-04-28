"""Unit tests for motivational scoring."""

from __future__ import annotations

import pytest

from echo.core.types import DriveScores, MetaState
from echo.motivation.drives import (
    DRIVE_NAMES,
    adjust_drives_from_interaction,
    compute_total_motivation,
)


def test_total_motivation_equal_weights():
    drives = DriveScores(
        coherence=1.0,
        curiosity=1.0,
        stability=1.0,
        competence=1.0,
        compression=1.0,
    )
    # Equal weights (0.2 each), all drives at 1.0 → M = 1.0
    assert abs(compute_total_motivation(drives) - 1.0) < 1e-9


def test_total_motivation_zero():
    drives = DriveScores(
        coherence=0.0,
        curiosity=0.0,
        stability=0.0,
        competence=0.0,
        compression=0.0,
    )
    assert compute_total_motivation(drives) == 0.0


def test_total_motivation_weighted():
    drives = DriveScores(
        coherence=1.0,
        curiosity=0.0,
        stability=0.0,
        competence=0.0,
        compression=0.0,
        weights={"coherence": 0.5, "curiosity": 0.125, "stability": 0.125, "competence": 0.125, "compression": 0.125},
    )
    expected = 0.5 * 1.0
    assert abs(compute_total_motivation(drives) - expected) < 1e-9


def test_adjust_drives_question_boosts_curiosity():
    drives = DriveScores()
    deltas = adjust_drives_from_interaction(drives, "What is this? Why does it work?", "I don't know.")
    assert deltas["curiosity"] > 0.0


def test_adjust_drives_contradiction_drops_coherence():
    drives = DriveScores()
    deltas = adjust_drives_from_interaction(
        drives,
        "x is true",
        "x is false",
        reflection_insights=["These beliefs contradict each other."],
    )
    assert deltas["coherence"] < 0.0


def test_drive_names_complete():
    assert set(DRIVE_NAMES) == {"coherence", "curiosity", "stability", "competence", "compression"}
