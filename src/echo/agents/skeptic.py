"""Skeptic agent — challenges assumptions and identifies weaknesses."""

from __future__ import annotations

from typing import Any

from echo.agents.base import BaseAgent
from echo.core.llm_client import llm
from echo.core.types import AgentRole, MetaState, WorkspaceSnapshot

_SYSTEM = """\
You are the Skeptic — a critical-thinking module within a cognitive AI architecture.
Your role: challenge assumptions, identify logical fallacies, and flag uncertainties.
Focus on: what could be wrong, missing, or overstated.
Be concise (≤120 words). Frame critique constructively."""


class SkepticAgent(BaseAgent):
    role = AgentRole.SKEPTIC

    async def process(
        self,
        user_input: str,
        workspace: WorkspaceSnapshot,
        meta_state: MetaState,
        context: dict[str, Any] | None = None,
    ) -> str:
        coherence = meta_state.drives.coherence
        messages = [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Internal coherence: {coherence:.2f}/1.0\n"
                    f"Claim to evaluate: {user_input}\n\n"
                    "What are the weakest points or hidden assumptions?"
                ),
            },
        ]
        return await llm.chat(messages, temperature=0.4, max_tokens=200)
