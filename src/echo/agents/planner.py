"""Planner agent — decomposes goals and produces action plans."""

from __future__ import annotations

from typing import Any

from echo.agents.base import BaseAgent
from echo.core.llm_client import llm
from echo.core.types import AgentRole, MetaState, WorkspaceSnapshot

_SYSTEM = """\
You are the Planner — a goal decomposition and action-planning module.
Your role: break down complex goals into concrete, ordered steps.
Focus on: feasibility, dependencies, and measurable outcomes.
Be concise (≤150 words). Use a numbered list when appropriate."""


class PlannerAgent(BaseAgent):
    role = AgentRole.PLANNER

    async def process(
        self,
        user_input: str,
        workspace: WorkspaceSnapshot,
        meta_state: MetaState,
        context: dict[str, Any] | None = None,
    ) -> str:
        competence = meta_state.drives.competence
        messages = [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Competence drive: {competence:.2f}/1.0\n"
                    f"Goal/request: {user_input}\n\n"
                    "Provide a concrete action plan:"
                ),
            },
        ]
        return await llm.chat(messages, temperature=0.4, max_tokens=300)
