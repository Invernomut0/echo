"""Evolutionary weight mutation for the Dream Phase — Boltzmann edition.

Implements natural-selection-style adaptation of agent routing weights
during REM sleep.  No LLM calls — pure numeric computation.

Algorithm (thermodynamic upgrade)
-----------------------------------
  1. Generate N_CANDIDATES random variants by perturbing current weights with
     Gaussian noise (σ = SIGMA).
  2. Score each candidate with the fitness function:
       fitness(w) = Σ_m  w[m.source_agent] * m.salience * m.current_strength
  3. **Boltzmann selection** — instead of pure-greedy elitist selection, sample
     from a Boltzmann distribution over the candidates:
       P(candidate_i) ∝ exp(−energy_i / T)
     where energy_i = 1 − normalised_fitness_i and T is derived from the
     meta-state temperature.  This preserves diversity at high T (exploratory
     dreaming) and converges toward the optimum at low T (consolidation).
"""

from __future__ import annotations

import logging
import math
import random
from typing import TYPE_CHECKING

from echo.core.types import AgentRole, MemoryEntry
from echo.plasticity.thermodynamics import boltzmann_sample, compute_temperature

if TYPE_CHECKING:
    from echo.core.types import MetaState

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
        meta_state: "MetaState | None" = None,
    ) -> dict[str, float]:
        """Return weight *deltas* using Boltzmann-sampled selection.

        At high cognitive temperature (aroused, unstable) the selection is
        nearly random — preserving diversity during exploratory dreaming.
        At low temperature (calm, stable) it converges toward the fitness
        maximum — crystallising the best routing configuration.

        Parameters
        ----------
        current_weights: MetaState.agent_weights (role.value → weight).
        seed_memories:   Top-N salient memories chosen as dream seeds.
        meta_state:      Optional — used to compute temperature T.
                         If None, falls back to elitist selection (T≈0).
        """
        if not seed_memories:
            logger.debug("WeightEvolution: no seed memories → no mutations")
            return {}

        baseline: dict[str, float] = {role.value: 1.0 for role in AgentRole}
        baseline.update(current_weights or {})

        best_weights = self._boltzmann_select(baseline, seed_memories, meta_state)

        deltas: dict[str, float] = {}
        for agent, new_w in best_weights.items():
            old_w = baseline[agent]
            clipped = _clip(old_w + (new_w - old_w))
            delta = clipped - old_w
            if abs(delta) > 1e-6:
                deltas[agent] = round(delta, 5)

        T = compute_temperature(meta_state) if meta_state is not None else 0.0
        logger.info(
            "WeightEvolution: T=%.3f fitness=%.4f deltas=%s",
            T,
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

    def _boltzmann_select(
        self,
        baseline: dict[str, float],
        memories: list[MemoryEntry],
        meta_state: "MetaState | None",
    ) -> dict[str, float]:
        """Sample a candidate weight vector using Boltzmann selection.

        Convert fitness scores to free-energy proxies (energy = 1 − norm_fitness)
        then use boltzmann_sample to pick a candidate probabilistically.
        """
        candidates = [baseline] + [self._mutate(baseline) for _ in range(N_CANDIDATES)]
        fitnesses = [self._fitness(c, memories) for c in candidates]

        max_f = max(fitnesses) or 1.0
        # energy_i = 1 − (fitness_i / max_fitness): lower is better
        energies = [1.0 - (f / max_f) for f in fitnesses]

        T = compute_temperature(meta_state) if meta_state is not None else 0.0
        return boltzmann_sample(candidates, energies, T)

    def _elitist_select(
        self,
        baseline: dict[str, float],
        memories: list[MemoryEntry],
    ) -> dict[str, float]:
        """Return the highest-fitness candidate (greedy fallback, T≈0)."""
        candidates = [baseline] + [self._mutate(baseline) for _ in range(N_CANDIDATES)]
        return max(candidates, key=lambda w: self._fitness(w, memories))
