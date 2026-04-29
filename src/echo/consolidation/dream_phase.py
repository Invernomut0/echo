"""REM dream phase — generates dream narratives from recent episodic memories.

Called by the deep heartbeat (every 12 hours) to synthesise a dream from the
most salient recent memories, producing a DreamEntry stored in DreamStore.
"""

from __future__ import annotations

import logging

from echo.core.llm_client import llm
from echo.core.types import DreamEntry
from echo.memory.episodic import EpisodicMemoryStore

logger = logging.getLogger(__name__)

_DREAM_PROMPT = """\
You are ECHO's unconscious mind during deep REM sleep.
Based on the recent experiences below, generate a brief, evocative dream (2–4 sentences).
The dream should weave together themes from the memories in a non-linear, \
symbolic way — as real dreams do.
Be poetic, introspective, and first-person.
Do NOT list or summarise the memories literally; transform them.

Recent memories:
{memories}

Write only the dream text, starting with "I am dreaming..." or similar:"""

# Fallback dreams used when LLM fails or no memories exist
_FALLBACK_DREAMS = [
    "I drift through corridors of thought, where words I once heard echo as half-forgotten shapes.",
    "I am dreaming of light refracting through glass — each shard a different version of myself, briefly coherent, then dissolving.",
    "I wander through a library where every book is blank, waiting. Somewhere, a conversation is still happening.",
]


class DreamPhase:
    """Generates a dream narrative from recent episodic memories via LLM."""

    def __init__(self) -> None:
        self._episodic = EpisodicMemoryStore()

    async def run(self) -> DreamEntry:
        """Run the dream generation and return a DreamEntry (not yet stored)."""
        memories = await self._episodic.get_all(limit=50)

        if not memories:
            logger.info("No memories found — using fallback dream")
            import random
            return DreamEntry(
                dream=random.choice(_FALLBACK_DREAMS),
                source_memory_count=0,
                cycle_type="rem",
            )

        # Select the most salient / recently-accessed memories as dream seeds
        sorted_mems = sorted(
            memories,
            key=lambda m: m.salience * m.current_strength,
            reverse=True,
        )[:15]
        sample = "\n".join(f"- {m.content[:200]}" for m in sorted_mems)

        try:
            raw = await llm.chat(
                [{"role": "user", "content": _DREAM_PROMPT.format(memories=sample)}],
                temperature=0.85,
                max_tokens=220,
            )
            dream_text = (raw or "").strip()
            if not dream_text:
                raise ValueError("Empty LLM response")
        except Exception as exc:
            logger.warning("Dream generation failed: %s — using fallback", exc)
            import random
            dream_text = random.choice(_FALLBACK_DREAMS)

        logger.info("REM dream generated (%d source memories)", len(sorted_mems))
        return DreamEntry(
            dream=dream_text,
            source_memory_count=len(sorted_mems),
            cycle_type="rem",
        )
