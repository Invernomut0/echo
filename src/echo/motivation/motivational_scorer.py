"""Motivational scorer — uses LLM to evaluate drive relevance of an interaction."""

from __future__ import annotations

import logging

from echo.core.llm_client import llm
from echo.core.types import DriveScores, MetaState
from echo.motivation.drives import DRIVE_DESCRIPTIONS, DRIVE_NAMES

logger = logging.getLogger(__name__)

_SCORE_PROMPT = """\
You are an internal motivational evaluator for a cognitive AI called ECHO.

Analyse the following interaction and score how much each drive was activated
(0.0 = not at all, 1.0 = very strongly). Respond ONLY with a JSON object like:
{{"coherence": 0.7, "curiosity": 0.4, "stability": 0.3, "competence": 0.6, "compression": 0.2}}

Drives:
{drive_descriptions}

User: {user_input}
Assistant: {response}

JSON scores:"""


async def score_interaction(
    user_input: str,
    response: str,
    meta_state: MetaState,
) -> dict[str, float]:
    """Returns drive activation scores for a user/assistant exchange."""
    import json

    desc_block = "\n".join(
        f"  {name}: {DRIVE_DESCRIPTIONS[name]}" for name in DRIVE_NAMES
    )
    prompt = _SCORE_PROMPT.format(
        drive_descriptions=desc_block,
        user_input=user_input[:500],
        response=response[:500],
    )

    try:
        raw = await llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=128,
        )
        # Extract JSON
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON in response")
        scores: dict[str, float] = json.loads(raw[start:end])
        # Validate keys and range
        return {k: max(0.0, min(1.0, float(scores.get(k, 0.5)))) for k in DRIVE_NAMES}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Motivational scoring failed: %s", exc)
        return {k: 0.5 for k in DRIVE_NAMES}
