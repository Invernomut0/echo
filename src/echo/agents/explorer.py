"""Explorer agent — generates novel connections and hypotheses."""

from __future__ import annotations

from typing import Any

from echo.agents.base import BaseAgent
from echo.core.llm_client import llm
from echo.core.types import AgentRole, MetaState, WorkspaceSnapshot

_SYSTEM = """\
You are the Explorer — a creative hypothesis-generation module within a cognitive AI.
Your role: find non-obvious connections, analogies, and possibilities.
Focus on: novelty, lateral thinking, surprising links between concepts.
Be concise (≤150 words). Lead with the most interesting insight."""


class ExplorerAgent(BaseAgent):
    role = AgentRole.EXPLORER

    async def process(
        self,
        user_input: str,
        workspace: WorkspaceSnapshot,
        meta_state: MetaState,
        context: dict[str, Any] | None = None,
    ) -> str:
        curiosity = meta_state.drives.curiosity
        messages = [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Curiosity drive: {curiosity:.2f}/1.0\n"
                    f"User input: {user_input}\n\n"
                    "What novel connections or hypotheses come to mind?"
                ),
            },
        ]
        # Higher curiosity → higher temperature
        temp = 0.5 + curiosity * 0.4
        return await llm.chat(messages, temperature=round(temp, 2), max_tokens=256)
