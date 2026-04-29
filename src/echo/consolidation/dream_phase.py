"""REM dream phase — generates dream narratives from recent episodic memories.

Called by the deep heartbeat (every 12 hours) to synthesise a dream from the
most salient recent memories, producing a DreamEntry stored in DreamStore.

v0.2.13: Integrates three cognitive extensions that run in parallel alongside
the base LLM dream:
  - WeightEvolution    — fitness-guided agent weight mutation
  - CreativeSynthesis  — bridge insights from distant memory pairs
  - SwarmDream         — 4 parallel personas with elitist winner selection
"""

from __future__ import annotations

import asyncio
import logging

from echo.core.llm_client import llm
from echo.core.types import DreamEntry, MetaState
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
    """Generates a dream narrative from recent episodic memories via LLM.

    Now also runs WeightEvolution, CreativeSynthesis and SwarmDream in
    parallel to enrich the returned DreamEntry.
    """

    def __init__(self) -> None:
        self._episodic = EpisodicMemoryStore()

    async def run(self, meta_state: MetaState | None = None) -> DreamEntry:
        """Run the dream generation and return a DreamEntry (not yet stored).

        Parameters
        ----------
        meta_state:
            Current MetaState; used by WeightEvolution to read current agent
            weights.  If None the evolver uses default weights (1.0 each).
        """
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

        # ── Phase v0.2.13 extensions ──────────────────────────────────────────
        # Import here to keep module loading fast and avoid circular imports
        from echo.consolidation.creative_synthesis import CreativeSynthesis
        from echo.consolidation.swarm_dream import SwarmDream
        from echo.consolidation.weight_evolution import WeightEvolution

        # Run base LLM dream + CreativeSynthesis + SwarmDream in parallel
        async def _base_dream() -> str:
            try:
                raw = await llm.chat(
                    [{"role": "user", "content": _DREAM_PROMPT.format(memories=sample)}],
                    temperature=0.85,
                    max_tokens=220,
                )
                text = (raw or "").strip()
                if not text:
                    raise ValueError("Empty LLM response")
                return text
            except Exception as exc:
                logger.warning("Dream generation failed: %s — using fallback", exc)
                import random
                return random.choice(_FALLBACK_DREAMS)

        (
            dream_text,
            synthetic_insights,
            swarm_result,
        ) = await asyncio.gather(
            _base_dream(),
            CreativeSynthesis().run(sorted_mems),
            SwarmDream().run(sorted_mems),
        )

        # Weight evolution is sync — run after gather
        current_weights = meta_state.agent_weights if meta_state else {}
        weight_mutations = WeightEvolution().evolve(current_weights, sorted_mems)

        # Use SwarmDream winner as dream text if it scored well enough
        # (non-empty and not fallback) — richer than the base prompt
        final_dream_text = swarm_result.winner if swarm_result.winner_persona != "fallback" else dream_text
        if not final_dream_text:
            final_dream_text = dream_text

        logger.info(
            "REM dream generated (seeds=%d, insights=%d, swarm_winner=%s, mutations=%d)",
            len(sorted_mems),
            len(synthetic_insights),
            swarm_result.winner_persona,
            len(weight_mutations),
        )

        return DreamEntry(
            dream=final_dream_text,
            source_memory_count=len(sorted_mems),
            cycle_type="rem",
            weight_mutations=weight_mutations or None,
            synthesis_count=len(synthetic_insights),
            synthetic_insights=synthetic_insights,
            swarm_fragments=list(swarm_result.fragments.values()),
            selected_persona=swarm_result.winner_persona,
        )
