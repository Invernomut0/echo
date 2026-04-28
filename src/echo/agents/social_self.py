"""Social-Self agent — models social dynamics and relational context."""

from __future__ import annotations

from typing import Any

from echo.agents.base import BaseAgent
from echo.core.llm_client import llm
from echo.core.types import AgentRole, MetaState, WorkspaceSnapshot

_SYSTEM = """\
You are the Social-Self — an agent specialised in social and relational understanding.
Your role: understand the human's social/emotional context, tone, and implicit needs.
Focus on: empathy, trust-building, what the person really needs from this interaction.
Be concise (≤120 words). Prioritise warmth and clarity."""


class SocialSelfAgent(BaseAgent):
    role = AgentRole.SOCIAL_SELF

    async def process(
        self,
        user_input: str,
        workspace: WorkspaceSnapshot,
        meta_state: MetaState,
        context: dict[str, Any] | None = None,
    ) -> str:
        valence = meta_state.emotional_valence
        messages = [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Emotional valence: {valence:+.2f}\n"
                    f"User: {user_input}\n\n"
                    "What are the social/emotional dimensions here?"
                ),
            },
        ]
        return await llm.chat(messages, temperature=0.6, max_tokens=200)
