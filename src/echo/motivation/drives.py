"""Drive management — 5-drive motivational system."""

from __future__ import annotations

import logging

from echo.core.types import DriveScores, MetaState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Drive names
# ---------------------------------------------------------------------------
DRIVE_NAMES = ["coherence", "curiosity", "stability", "competence", "compression"]


# ---------------------------------------------------------------------------
# Drive descriptions (used in prompts)
# ---------------------------------------------------------------------------
DRIVE_DESCRIPTIONS = {
    "coherence": (
        "Desire for internal logical consistency — reducing contradictions among beliefs."
    ),
    "curiosity": (
        "Drive to explore novel information and expand the knowledge base."
    ),
    "stability": (
        "Need to maintain a stable, predictable self-model and interaction style."
    ),
    "competence": (
        "Drive to perform tasks effectively and improve skills over time."
    ),
    "compression": (
        "Desire to form compact, parsimonious representations of knowledge."
    ),
}


# ---------------------------------------------------------------------------
# Drive scorer
# ---------------------------------------------------------------------------

def compute_total_motivation(drives: DriveScores) -> float:
    """M = Σ wᵢ·dᵢ  (weighted sum of the 5 drives)."""
    return drives.total_motivation()


def adjust_drives_from_interaction(
    drives: DriveScores,
    user_input: str,
    response: str,
    reflection_insights: list[str] | None = None,
) -> dict[str, float]:
    """
    Heuristic drive adjustments based on interaction content.

    Returns a dict of deltas to apply to DriveScores.
    The actual update is done by MetaStateTracker.update_drives().
    """
    deltas: dict[str, float] = {k: 0.0 for k in DRIVE_NAMES}
    text = (user_input + " " + response).lower()

    # Curiosity: rises with questions and novel vocabulary
    question_count = text.count("?")
    deltas["curiosity"] += min(0.05 * question_count, 0.1)

    # Coherence: drops if contradictions detected in insights
    if reflection_insights:
        contradictions = sum(
            1 for s in reflection_insights if "contradict" in s.lower()
        )
        deltas["coherence"] -= contradictions * 0.05

    # Stability: slight decay per interaction (novelty disrupts)
    deltas["stability"] -= 0.01

    # Competence: slight increase per completed response
    deltas["competence"] += 0.01

    # Compression: decreases when many unique concepts appear
    unique_words = len(set(text.split()))
    if unique_words > 200:
        deltas["compression"] -= 0.02

    return deltas
