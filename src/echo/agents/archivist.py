"""Archivist agent — retrieves and contextualises relevant memories."""

from __future__ import annotations

import logging
from typing import Any

from echo.agents.base import BaseAgent
from echo.core.llm_client import llm
from echo.core.types import AgentRole, MetaState, WorkspaceSnapshot

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are the Archivist — a memory retrieval and contextualisation module.
Your role: surface relevant past knowledge and explain its connection to the current input.
Focus on: recalled memories, past patterns, how prior experience informs the present.
Be concise (≤150 words)."""


class ArchivistAgent(BaseAgent):
    role = AgentRole.ARCHIVIST

    async def process(
        self,
        user_input: str,
        workspace: WorkspaceSnapshot,
        meta_state: MetaState,
        context: dict[str, Any] | None = None,
    ) -> str:
        memories_text = ""
        if context and context.get("memories"):
            entries = context["memories"][:5]
            snippets = [f"- {e.content[:200]}" for e in entries]
            memories_text = "\nRetrieved memories:\n" + "\n".join(snippets)

        if not memories_text:
            return "No relevant memories found for this input."

        messages = [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": (
                    f"User input: {user_input}"
                    f"{memories_text}\n\n"
                    "How do these memories inform the current context?"
                ),
            },
        ]
        return await llm.chat(messages, temperature=0.3, max_tokens=256)
