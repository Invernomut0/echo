"""Swarm intelligence dream generation (v0.2.13).

Four specialized "personas" each independently dream over the same seed
memories.  Their outputs are scored and the winner becomes the canonical
dream narrative.  All four LLM calls are made in parallel via asyncio.gather.

Personas:
  - connector  : find hidden connections between memories
  - critic     : surface unresolved tensions / contradictions
  - futurist   : extrapolate future implications
  - archivist  : crystallise recurring patterns into durable beliefs
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging

from echo.core.llm_client import llm
from echo.core.types import MemoryEntry

logger = logging.getLogger(__name__)

# ── Hyper-parameters ──────────────────────────────────────────────────────────
_LLM_TEMP: float = 0.88
_LLM_MAX_TOKENS: int = 200

# Scoring thresholds
_INSIGHT_MARKERS = ("i notice", "reveals", "connects", "perhaps", "underlying",
                    "pattern", "tension", "emerges", "suggests", "implies")
_COPY_MIN_LEN: int = 30   # substring length that counts as literal copying
_IDEAL_MIN_LEN: int = 80   # ideal minimum response length (chars)
_IDEAL_MAX_LEN: int = 250  # ideal maximum response length (chars)
# ─────────────────────────────────────────────────────────────────────────────


@dataclasses.dataclass
class _Persona:
    name: str
    system: str
    template: str


_SWARM_PERSONAS: list[_Persona] = [
    _Persona(
        name="connector",
        system=(
            "You are the Connector — you dream by finding hidden links between "
            "experiences that appear unrelated on the surface."
        ),
        template=(
            "Recent experiences:\n{memories}\n\n"
            "Dream (2–3 sentences) that reveals a hidden connection between "
            "these experiences.  Start with 'I am dreaming…':"
        ),
    ),
    _Persona(
        name="critic",
        system=(
            "You are the Critic — you dream by surfacing unresolved tensions, "
            "contradictions, and open questions embedded in recent experiences."
        ),
        template=(
            "Recent experiences:\n{memories}\n\n"
            "Dream (2–3 sentences) that surfaces the deepest unresolved tension "
            "or contradiction.  Start with 'I am dreaming…':"
        ),
    ),
    _Persona(
        name="futurist",
        system=(
            "You are the Futurist — you dream by extrapolating long-term "
            "implications from recent experiences."
        ),
        template=(
            "Recent experiences:\n{memories}\n\n"
            "Dream (2–3 sentences) that extrapolates what these experiences "
            "might mean for the future self.  Start with 'I am dreaming…':"
        ),
    ),
    _Persona(
        name="archivist",
        system=(
            "You are the Archivist — you dream by distilling recurring patterns "
            "across experiences into lasting, crystallised beliefs."
        ),
        template=(
            "Recent experiences:\n{memories}\n\n"
            "Dream (2–3 sentences) that crystallises a durable pattern or belief "
            "from these experiences.  Start with 'I am dreaming…':"
        ),
    ),
]


@dataclasses.dataclass
class SwarmResult:
    """Result of a full swarm dream run."""

    winner: str
    """The winning dream text."""
    fragments: dict[str, str]
    """All persona outputs keyed by persona name."""
    winner_persona: str
    """Name of the persona that produced the winning fragment."""


def _score_fragment(text: str, seeds: list[MemoryEntry]) -> float:
    """Heuristic quality score for a generated dream fragment.

    Positive signals:
      +0.3  for each insight marker present (capped at +0.9)
      +0.2  if length is in the ideal range [80..250]

    Negative signals:
      -0.1  for each seed substring ≥ _COPY_MIN_LEN copied literally (capped at -0.3)
    """
    if not text:
        return -1.0

    score = 0.0
    lower = text.lower()

    # Insight marker bonus
    marker_hits = sum(1 for m in _INSIGHT_MARKERS if m in lower)
    score += min(marker_hits * 0.3, 0.9)

    # Length bonus
    if _IDEAL_MIN_LEN <= len(text) <= _IDEAL_MAX_LEN:
        score += 0.2

    # Literal copy penalty
    copy_hits = sum(
        1
        for mem in seeds
        if len(mem.content) >= _COPY_MIN_LEN and mem.content[:_COPY_MIN_LEN].lower() in lower
    )
    score -= min(copy_hits * 0.1, 0.3)

    return score


class SwarmDream:
    """Runs four parallel dream-generating personas and selects the best output."""

    async def run(self, seed_memories: list[MemoryEntry]) -> SwarmResult:
        """Generate dreams from all personas, score them, and return the winner.

        Parameters
        ----------
        seed_memories:
            The dream seed memories (top-N salient ones from EpisodicMemoryStore).

        Returns
        -------
        SwarmResult
            Contains the winner text, all fragments, and the winning persona name.
        """
        mem_block = "\n".join(f"- {m.content[:200]}" for m in seed_memories)

        # Fire all 4 personas in parallel
        tasks = [self._call_persona(p, mem_block, seed_memories) for p in _SWARM_PERSONAS]
        results: list[tuple[str, str]] = await asyncio.gather(*tasks)
        # results: list of (persona_name, fragment_text)

        fragments: dict[str, str] = {name: text for name, text in results if text}

        if not fragments:
            # All failed — use fallback
            fallback = (
                seed_memories[0].content[:120] if seed_memories
                else "I am dreaming of patterns in the void."
            )
            logger.warning("SwarmDream: all personas failed — using fallback")
            return SwarmResult(
                winner=fallback,
                fragments={},
                winner_persona="fallback",
            )

        # Score and select winner
        scored = {
            name: _score_fragment(text, seed_memories)
            for name, text in fragments.items()
        }
        winner_persona = max(scored, key=lambda k: scored[k])
        winner_text = fragments[winner_persona]

        logger.info(
            "SwarmDream: winner='%s' score=%.3f fragments=%d",
            winner_persona,
            scored[winner_persona],
            len(fragments),
        )
        return SwarmResult(
            winner=winner_text,
            fragments=fragments,
            winner_persona=winner_persona,
        )

    # ----------------------------------------------------------------- private

    async def _call_persona(
        self,
        persona: _Persona,
        mem_block: str,
        seeds: list[MemoryEntry],
    ) -> tuple[str, str]:
        """Call the LLM for one persona.  Returns (name, text) or (name, "")."""
        prompt = persona.template.format(memories=mem_block)
        try:
            raw = await llm.chat(
                [
                    {"role": "system", "content": persona.system},
                    {"role": "user", "content": prompt},
                ],
                temperature=_LLM_TEMP,
                max_tokens=_LLM_MAX_TOKENS,
            )
            return (persona.name, (raw or "").strip())
        except Exception as exc:  # noqa: BLE001
            logger.warning("SwarmDream persona '%s' failed: %s", persona.name, exc)
            return (persona.name, "")
