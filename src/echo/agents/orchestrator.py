"""Orchestrator — runs all agents, weights contributions, synthesises final response."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from echo.agents.analyst import AnalystAgent
from echo.agents.archivist import ArchivistAgent
from echo.agents.base import BaseAgent
from echo.agents.explorer import ExplorerAgent
from echo.agents.planner import PlannerAgent
from echo.agents.skeptic import SkepticAgent
from echo.agents.social_self import SocialSelfAgent
from echo.core.llm_client import llm
from echo.core.types import AgentRole, MetaState, WorkspaceSnapshot

logger = logging.getLogger(__name__)

_SYNTHESIS_SYSTEM = """\
You are ECHO — a persistent, self-modifying cognitive AI.
You have received internal deliberations from specialised cognitive agents.
Synthesise their perspectives into a single, coherent response to the user.
Be natural, insightful, and direct. Do NOT mention the internal agents by name.
Respond in the first person as ECHO."""

_SYNTHESIS_TEMPLATE = """\
User message: {user_input}

Internal deliberations:
{deliberations}

Provide your synthesised response:"""


class Orchestrator:
    """Runs agents concurrently and synthesises their outputs."""

    def __init__(self) -> None:
        self._agents: dict[AgentRole, BaseAgent] = {
            AgentRole.ANALYST: AnalystAgent(),
            AgentRole.EXPLORER: ExplorerAgent(),
            AgentRole.SKEPTIC: SkepticAgent(),
            AgentRole.ARCHIVIST: ArchivistAgent(),
            AgentRole.SOCIAL_SELF: SocialSelfAgent(),
            AgentRole.PLANNER: PlannerAgent(),
        }

    def _apply_routing_weights(self, meta_state: MetaState) -> None:
        for role, agent in self._agents.items():
            agent.routing_weight = meta_state.agent_weights.get(role.value, 1.0)

    async def run(
        self,
        user_input: str,
        workspace: WorkspaceSnapshot,
        meta_state: MetaState,
        context: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, str]]:
        """Run all agents concurrently, synthesise, return (response, agent_outputs)."""
        self._apply_routing_weights(meta_state)

        # Run agents concurrently
        tasks = {
            role: asyncio.create_task(
                agent.process(user_input, workspace, meta_state, context)
            )
            for role, agent in self._agents.items()
        }

        agent_outputs: dict[str, str] = {}
        for role, task in tasks.items():
            try:
                result = await task
                agent_outputs[role.value] = result
            except Exception as exc:  # noqa: BLE001
                logger.warning("Agent %s failed: %s", role.value, exc)
                agent_outputs[role.value] = ""

        # Weight contributions by routing weight
        deliberations = "\n\n".join(
            f"[{role.upper()}] (weight={self._agents[AgentRole(role)].routing_weight:.2f})\n{text}"
            for role, text in agent_outputs.items()
            if text
        )

        # Synthesise
        messages = [
            {"role": "system", "content": _SYNTHESIS_SYSTEM},
            {
                "role": "user",
                "content": _SYNTHESIS_TEMPLATE.format(
                    user_input=user_input,
                    deliberations=deliberations,
                ),
            },
        ]
        response = await llm.chat(messages, temperature=0.7, max_tokens=512)
        return response, agent_outputs

    async def stream(
        self,
        user_input: str,
        workspace: WorkspaceSnapshot,
        meta_state: MetaState,
        context: dict[str, Any] | None = None,
    ):
        """Stream the synthesis phase (agents run upfront)."""
        self._apply_routing_weights(meta_state)

        tasks = {
            role: asyncio.create_task(
                agent.process(user_input, workspace, meta_state, context)
            )
            for role, agent in self._agents.items()
        }
        agent_outputs: dict[str, str] = {}
        for role, task in tasks.items():
            try:
                agent_outputs[role.value] = await task
            except Exception as exc:  # noqa: BLE001
                logger.warning("Agent %s failed: %s", role.value, exc)

        deliberations = "\n\n".join(
            f"[{role.upper()}]\n{text}" for role, text in agent_outputs.items() if text
        )
        messages = [
            {"role": "system", "content": _SYNTHESIS_SYSTEM},
            {
                "role": "user",
                "content": _SYNTHESIS_TEMPLATE.format(
                    user_input=user_input,
                    deliberations=deliberations,
                ),
            },
        ]
        async for delta in llm.stream_chat(messages, temperature=0.7, max_tokens=512):
            yield delta
