"""Self-prediction — ECHO predicts its own next response before generating."""

from __future__ import annotations

import logging

from echo.core.llm_client import llm
from echo.core.types import MetaState

logger = logging.getLogger(__name__)

_PREDICTION_PROMPT = """\
You are a meta-cognitive monitor for an AI cognitive architecture called ECHO.
Given the user's message and ECHO's current internal state, predict (in 1-2 sentences)
what kind of response ECHO will most likely generate — the *theme* and *tone*, not the
full content.

Current drives:
  coherence={coherence:.2f}  curiosity={curiosity:.2f}  stability={stability:.2f}
  competence={competence:.2f}  compression={compression:.2f}
Emotional valence: {valence:.2f}

User message: {user_input}

Prediction (1-2 sentences):"""


async def predict_response(user_input: str, meta_state: MetaState) -> str:
    """Generate a self-prediction of the upcoming response."""
    d = meta_state.drives
    prompt = _PREDICTION_PROMPT.format(
        coherence=d.coherence,
        curiosity=d.curiosity,
        stability=d.stability,
        competence=d.competence,
        compression=d.compression,
        valence=meta_state.emotional_valence,
        user_input=user_input,
    )
    try:
        prediction = await llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=128,
        )
        return prediction.strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Self-prediction failed: %s", exc)
        return ""
