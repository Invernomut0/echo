"""Evolutionary weight mutation for the Dream Phase (v0.2.13).

Implements natural-selection-style adaptation of agent routing weights
during REM sleep.  No LLM calls — pure numeric computation.

Algorithm:
  1. Generate N_CANDIDATES random variants by perturbing current weights with
     Gaussian noise (σ = SIGMA).
  2. Score each candidate: F(w) = Σ_m  w[m.source_agent] * m.salience * m.current_strength
     — this rewards agents whose past outputs produced the most salient memories.
  3. Keep the elitist winner (highest F).  Return *deltas* so the caller
     decides if/how to apply them.
"""

from __future__ import annotations

import logging
import math
import random

from echo.core.types import AgentRole, MemoryEntry

logger = logging.getLogger(__name__)

# ── Hyper-parameters ──────────────────────────────────────────────────────────
N_CANDIDATES: int = 5        # number of weight variants to evaluate
SIGMA: float = 0.08          # Gaussian std-dev for mutations
WEIGHT_MIN: float = 0.10     # clip lower bound (matches PlasticityAdapter)
WEIGHT_MAX: float = 2.00     # clip upper bound
# ─────────────────────────────────────────────────────────────────────────────


def _clip(value: float) -> float:
    return max(WEIGHT_MIN, min(WEIGHT_MAX, value))


class WeightEvolution:
    """Evolves ``MetaState.agent_weights`` through fitness-guided mutation."""

    # ------------------------------------------------------------------ public

    def evolve(
        self,
        current_weights: dict[str, float],
        seed_memories: list[MemoryEntry],
    ) -> dict[str, float]:
        """Return weight *deltas* — add to current weights to apply evolution.

        Parameters
        ----------
        current_weights:
            The ``MetaState.agent_weights`` dict (role.value → weight).
            May be empty; defaults are filled from AgentRole.
        seed_memories:
            The memories selected as dream seeds (the top-N salient ones).

        Returns
        -------
        dict[str, float]
            Mapping ``agent_name → delta`` (positive or negative float).
            All delta values are clipped so that
            ``current + delta`` stays within [WEIGHT_MIN, WEIGHT_MAX].
        """
        if not seed_memories:
            logger.debug("WeightEvolution: no seed memories → no mutations")
            return {}

        # Ensure we have a baseline for every known role
        baseline: dict[str, float] = {
            role.value: 1.0 for role in AgentRole
        }
        baseline.update(current_weights or {})

        best_weights = self._elitist_select(baseline, seed_memories)

        # Compute deltas and clip so final values stay in bounds
        deltas: dict[str, float] = {}
        for agent, new_w in best_weights.items():
            old_w = baseline[agent]
            # Clamp the final weight then recompute delta
            clipped = _clip(old_w + (new_w - old_w))
            delta = clipped - old_w
            if abs(delta) > 1e-6:
                deltas[agent] = round(delta, 5)

        logger.info(
            "WeightEvolution: winner fitness=%.4f deltas=%s",
            self._fitness(best_weights, seed_memories),
            {k: f"{v:+.4f}" for k, v in deltas.items()},
        )
        return deltas

    # ----------------------------------------------------------------- private

    def _fitness(
        self,
        weights: dict[str, float],
        memories: list[MemoryEntry],
    ) -> float:
        """F(w) = Σ_m  w[m.source_agent] * m.salience * m.current_strength."""
        total = 0.0
        for m in memories:
            w = weights.get(m.source_agent, 1.0) if m.source_agent else 1.0
            total += w * m.salience * m.current_strength
        return total

    def _mutate(self, weights: dict[str, float]) -> dict[str, float]:
        """Produce a perturbed copy using Gaussian noise."""
        return {
            agent: _clip(w + random.gauss(0.0, SIGMA))
            for agent, w in weights.items()
        }

    def _elitist_select(
        self,
        baseline: dict[str, float],
        memories: list[MemoryEntry],
    ) -> dict[str, float]:
        """Return the highest-fitness candidate (including baseline)."""
        candidates = [baseline] + [self._mutate(baseline) for _ in range(N_CANDIDATES)]
        best = max(candidates, key=lambda w: self._fitness(w, memories))
        return best
