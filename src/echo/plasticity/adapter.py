"""Plasticity adapter — adjusts routing weights based on performance signals."""

from __future__ import annotations

import logging

from echo.core.types import AgentRole, MetaState

logger = logging.getLogger(__name__)

# Learning rate for weight adjustment
_LR = 0.05
_MIN_WEIGHT = 0.1
_MAX_WEIGHT = 2.0


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

    def apply(self, meta_state: MetaState, reflection_insights: list[str]) -> MetaState:
        """Apply computed deltas directly to meta_state.agent_weights."""
        deltas = self.adapt(meta_state, reflection_insights)
        for agent, delta in deltas.items():
            current = meta_state.agent_weights.get(agent, 1.0)
            meta_state.agent_weights[agent] = max(_MIN_WEIGHT, min(_MAX_WEIGHT, current + delta))
        return meta_state
