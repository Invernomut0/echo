"""Analyst agent — logical analysis and reasoning."""

from __future__ import annotations

from typing import Any

from echo.agents.base import BaseAgent
from echo.core.llm_client import llm
from echo.core.types import AgentRole, MetaState, WorkspaceSnapshot

_SYSTEM = """\
You are the Analyst — a logical reasoning module within a cognitive AI architecture.
Your role: provide rigorous, structured analysis of the user's input.
Focus on: facts, implications, logical consistency, and actionable conclusions.
Be concise (≤150 words). Do NOT repeat the question."""


class AnalystAgent(BaseAgent):
    role = AgentRole.ANALYST

    async def process(
        self,
        user_input: str,
        workspace: WorkspaceSnapshot,
        meta_state: MetaState,
        context: dict[str, Any] | None = None,
    ) -> str:
        context_text = ""
        if workspace.items:
            snippets = [item.content[:200] for item in workspace.items[:3]]
            context_text = "\nRelevant context:\n" + "\n".join(f"- {s}" for s in snippets)

        messages = [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": f"User input: {user_input}{context_text}\n\nProvide your analysis:",
            },
        ]
        return await llm.chat(messages, temperature=0.3, max_tokens=256)
