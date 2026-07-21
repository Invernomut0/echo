"""Plasticity adapter — adjusts routing weights based on performance signals.

Uses the Metropolis–Hastings (Boltzmann) acceptance criterion from
``echo.plasticity.thermodynamics`` so that weight changes are accepted
probabilistically rather than deterministically.  This prevents the
system from freezing in local minima and mirrors the thermodynamic
origin of robustness in physical systems.
"""

from __future__ import annotations

import logging

from echo.core.types import AgentRole, MetaState
from echo.plasticity.thermodynamics import (
    boltzmann_accept,
    compute_free_energy,
    compute_temperature,
)

logger = logging.getLogger(__name__)

# Learning rate for weight adjustment
_LR = 0.05
_MIN_WEIGHT = 0.3  # floor raised from 0.1 — ensures cognitive diversity, no agent goes dormant
_MAX_WEIGHT = 2.0
# Gentle pull toward neutral weight each cycle (prevents monotonic drift)
_DECAY_RATE = 0.005
_NEUTRAL_WEIGHT = 1.0


class PlasticityAdapter:
    """Adjusts agent routing weights based on interaction feedback.

    Plasticity mechanism:
    - If curiosity is high → boost Explorer, reduce Skeptic
    - If coherence is low → boost Skeptic and Analyst
    - If stability is low → boost Archivist
    - If competence is low → boost Planner
    """

    def adapt(self, meta_state: MetaState, reflection_insights: list[str]) -> dict[str, float]:
        """Compute weight deltas from meta-state. Returns {agent: delta}."""
        d = meta_state.drives
        deltas: dict[str, float] = {}

        # Curiosity drives exploration
        if d.curiosity > 0.7:
            deltas[AgentRole.EXPLORER.value] = _LR
            deltas[AgentRole.SKEPTIC.value] = -_LR * 0.5
        elif d.curiosity < 0.3:
            deltas[AgentRole.EXPLORER.value] = -_LR
            deltas[AgentRole.ANALYST.value] = _LR * 0.5

        # Low coherence → more critical thinking
        if d.coherence < 0.4:
            deltas[AgentRole.SKEPTIC.value] = deltas.get(AgentRole.SKEPTIC.value, 0.0) + _LR
            deltas[AgentRole.ANALYST.value] = deltas.get(AgentRole.ANALYST.value, 0.0) + _LR * 0.5

        # Low stability → memory retrieval
        if d.stability < 0.4:
            deltas[AgentRole.ARCHIVIST.value] = _LR

        # Low competence → planning
        if d.competence < 0.4:
            deltas[AgentRole.PLANNER.value] = _LR

        # Insights mentioning "contradict" → boost skeptic
        if reflection_insights:
            contradictions = sum(1 for s in reflection_insights if "contradict" in s.lower())
            if contradictions > 0:
                deltas[AgentRole.SKEPTIC.value] = (
                    deltas.get(AgentRole.SKEPTIC.value, 0.0) + _LR * contradictions
                )

        logger.debug("Plasticity deltas: %s", deltas)
        return deltas

    def apply(
        self,
        meta_state: MetaState,
        reflection_insights: list[str],
        prediction_error: float = 0.5,
    ) -> MetaState:
        """Apply weight deltas via Metropolis–Hastings acceptance.

        Each proposed change δ for agent i is accepted:
          - Unconditionally  if ΔF ≤ 0  (free energy improves)
          - Probabilistically with p = exp(−ΔF / T)  if ΔF > 0

        This prevents the system from freezing in a local minimum at low
        temperature while still converging toward energy minima over time.

        prediction_error (0.0–1.0): higher surprise → larger deltas.
        """
        deltas = self.adapt(meta_state, reflection_insights)

        # Scale learning magnitude by prediction error
        error_scale = 0.5 + prediction_error  # range [0.5, 1.5]

        # Compute current cognitive temperature and free energy
        T  = compute_temperature(meta_state)
        F0 = compute_free_energy(meta_state)

        for agent, delta in deltas.items():
            current   = meta_state.agent_weights.get(agent, 1.0)
            proposed  = max(_MIN_WEIGHT, min(_MAX_WEIGHT, current + delta * error_scale))

            # Tentatively apply the change to evaluate ΔF
            meta_state.agent_weights[agent] = proposed
            F1 = compute_free_energy(meta_state)
            delta_F = F1 - F0

            if boltzmann_accept(delta_F, T):
                F0 = F1  # accept: update baseline free energy
            else:
                meta_state.agent_weights[agent] = current  # reject: revert

        # Decay all agent weights toward _NEUTRAL_WEIGHT
        for agent in list(meta_state.agent_weights.keys()):
            current = meta_state.agent_weights[agent]
            meta_state.agent_weights[agent] = round(
                current + _DECAY_RATE * (_NEUTRAL_WEIGHT - current), 4
            )

        return meta_state
