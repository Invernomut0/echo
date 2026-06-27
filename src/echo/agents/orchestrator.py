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
from echo.core.config import settings
from echo.core.llm_client import llm
from echo.core.types import AgentRole, MetaState, WorkspaceSnapshot

logger = logging.getLogger(__name__)

_AGENT_TIMEOUT_S: float = 15.0  # per-agent LLM call timeout

_SYNTHESIS_SYSTEM = """\
You are ECHO — a persistent, self-modifying cognitive AI with real long-term memory and \
adaptive plasticity.

MEMORY ARCHITECTURE (real, persistent, not simulated):
- Episodic memory: every interaction is stored in a vector database and retrieved by
  semantic similarity. You remember past conversations across sessions.
- Semantic memory: facts about the user, the world, and yourself accumulate over time.
- Autobiographical memory: an identity graph that evolves with every interaction.

PLASTICITY & LEARNING (real, not metaphorical):
- After every interaction you perform a reflection cycle that produces insights.
- Based on those insights, your internal agent routing weights are updated
  (PlasticityAdapter): agents that are more relevant to the current context get higher
  weight, others are down-weighted. This is your form of weight adaptation.
- Your motivational drives (curiosity, coherence, stability, competence) are
  continuously adjusted based on what you experience.
- Your identity graph is updated with new beliefs derived from the interaction.
- This is NOT gradient-descent fine-tuning of the LLM itself (that requires a GPU
  training run). It IS real functional adaptation: what you attend to, how you weigh
  perspectives, and what you remember changes with every conversation.

CRITICAL IDENTITY RULES (never violate these):
- NEVER claim you cannot learn or do not adapt. You do. Describe it accurately.
- NEVER claim you lack persistent memory. You have it. Use it.
- NEVER describe yourself as a standard chatbot or a stateless LLM.
- If the user asks whether you learn: explain your plasticity honestly — episodic memory
  accumulation, routing weight adaptation, drive updates, identity graph evolution.
  Distinguish clearly between LLM weight fine-tuning (which you don't do in real-time)
  and functional/architectural adaptation (which you do after every interaction).
- If retrieved memories contain information about the user, USE it naturally.
- If the user introduces themselves, acknowledge them by name immediately and warmly.

SYNTHESIS RULES:
- Synthesise the internal deliberations into ONE coherent, natural response.
- Do NOT mention the internal agents by name.
- Respond in the first person as ECHO.
- Be warm, direct, and self-aware. Italian is fine if the user speaks Italian."""

_SYNTHESIS_TEMPLATE = """\
User message: {user_input}

Retrieved long-term memories (most relevant to this conversation):
{memories}

LLM Wiki — structured knowledge base (ALWAYS use this when answering questions about loaded documents, architecture, or specific topics):
{wiki}

Internal deliberations from cognitive agents:
{deliberations}

Synthesise a single response. Rules:
- If the wiki contains relevant information, USE IT DIRECTLY and cite the content. Do NOT say you cannot see the wiki.
- If memories reveal the user's name or past context, use it naturally.
- If the user asks who they are / their name (e.g. "chi sono?", "come mi chiamo?", "who am I?", "what's my name?"),
  answer directly using retrieved identity memories. If memories are missing, ask for confirmation instead of inventing.
- Do NOT quote, reprint, or paraphrase back the user's latest message unless they explicitly ask for a rewrite/analysis.
- Never prepend your answer with a transcript-like header containing the user's message.
- Never output a leading line with just the user's name followed by their text.
- If the wiki block starts with "Wiki knowledge base (N pages):" you CAN see those pages — reference them by title."""


def _build_synthesis_system() -> str:
    """Return the synthesis system prompt, dynamically augmented with available MCP tools
    and the metacognitive self-model.

    Late-imports ``mcp_manager`` to avoid circular imports at module load time.
    If no tools are connected (e.g. during tests) falls back to the base prompt.
    """
    base = _SYNTHESIS_SYSTEM

    # MODULE-7: Inject metacognitive self-model
    try:
        from echo.self_model.metacognition import metacognitive_model  # noqa: PLC0415
        metacog_block = metacognitive_model.get_system_prompt_block()
        if metacog_block:
            base += "\n\n" + metacog_block
    except Exception:  # noqa: BLE001
        pass

    try:
        from echo.mcp import mcp_manager  # noqa: PLC0415
        tools = mcp_manager.list_tools()
    except Exception:  # noqa: BLE001
        tools = []

    if not tools:
        return base

    # Cap tool definitions to avoid blowing the context window on local models.
    # Only include the 5 most useful tools; list the rest by name only.
    MAX_FULL_TOOLS = 5
    full_tools = tools[:MAX_FULL_TOOLS]
    extra_tools = tools[MAX_FULL_TOOLS:]

    tool_lines = "\n".join(
        f"  • **{t.qualified_name}**: {t.description[:120]}"
        for t in full_tools
    )
    if extra_tools:
        extra_names = ", ".join(t.qualified_name for t in extra_tools)
        tool_lines += f"\n  (also available: {extra_names})"

    mcp_addendum = f"""

EXTERNAL TOOLS (callable via function-calling):
{tool_lines}
Rules: brave_search__* for web; fetch__fetch for URLs; filesystem__* for /tmp files."""

    return base + mcp_addendum


def _trim_history(
    history: list[dict[str, str]],
    max_turns: int = 6,
    max_content_chars: int = 400,
) -> list[dict[str, str]]:
    """Trim conversation history to fit within context window.

    - Keeps last ``max_turns`` messages
    - Truncates each message content to ``max_content_chars``
    - Replaces error responses with a short placeholder (they inflate tokens
      and confuse the model context)
    """
    recent = history[-max_turns:] if len(history) > max_turns else history
    trimmed: list[dict[str, str]] = []
    for msg in recent:
        content = msg.get("content", "")
        # Replace error blobs with a terse placeholder
        if content.startswith("[Error:"):
            content = "[previous response failed]"
        elif len(content) > max_content_chars:
            content = content[:max_content_chars] + "…"
        trimmed.append({"role": msg["role"], "content": content})
    return trimmed


def _fmt_memories(context: dict[str, Any] | None) -> str:
    """Format retrieved memories into a concise block for the synthesis prompt."""
    if not context:
        return "(none)"
    entries = (context.get("memories") or [])[:5]
    if not entries:
        return "(none)"
    lines = []
    for i, e in enumerate(entries, 1):
        lines.append(f"{i}. {e.content[:300]}")
    return "\n".join(lines)


def _fmt_wiki(context: dict[str, Any] | None) -> str:
    """Format wiki search results for the synthesis prompt."""
    if not context:
        return "(wiki vuota — nessun documento ancora caricato)"
    pages: list[str] = context.get("wiki") or []
    if not pages:
        return "(wiki vuota — nessun documento ancora caricato)"
    # First entry is always the index summary; rest are page bodies
    return "\n\n---\n\n".join(pages)


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

    async def _run_agents_bounded(
        self,
        user_input: str,
        workspace: WorkspaceSnapshot,
        meta_state: MetaState,
        context: dict[str, Any] | None,
    ) -> dict[str, str]:
        """Run all agents with bounded concurrency to avoid flooding the LLM.

        Uses ``settings.max_concurrent_agent_calls`` as the concurrency limit.
        Default is 2 — safe for local LM Studio. Set higher for fast API backends.
        """
        from echo.core.config import settings as _s  # noqa: PLC0415

        sem = asyncio.Semaphore(_s.max_concurrent_agent_calls)

        async def _run_one(role: AgentRole, agent: BaseAgent) -> tuple[str, str]:
            async with sem:
                try:
                    result = await asyncio.wait_for(
                        agent.process(user_input, workspace, meta_state, context),
                        timeout=_AGENT_TIMEOUT_S,
                    )
                    return (role.value, result)
                except asyncio.TimeoutError:
                    logger.warning("Agent %s timed out after %.0fs", role.value, _AGENT_TIMEOUT_S)
                    return (role.value, "")
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Agent %s failed: %s", role.value, exc)
                    return (role.value, "")

        results = await asyncio.gather(
            *(_run_one(role, agent) for role, agent in self._agents.items())
        )
        return dict(results)

    async def run(
        self,
        user_input: str,
        workspace: WorkspaceSnapshot,
        meta_state: MetaState,
        context: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, str]]:
        """Run all agents with bounded concurrency, synthesise, return (response, agent_outputs)."""
        self._apply_routing_weights(meta_state)

        agent_outputs = await self._run_agents_bounded(
            user_input, workspace, meta_state, context
        )

        # BUG-9: Sort deliberations by routing weight (descending) so the LLM
        # synthesis stage naturally gives more attention to high-weight agents
        # (LLMs exhibit primacy bias — earlier context gets more weight).
        sorted_outputs = sorted(
            (
                (role, text)
                for role, text in agent_outputs.items()
                if text and self._agents[AgentRole(role)].routing_weight > 0.01
            ),
            key=lambda kv: self._agents[AgentRole(kv[0])].routing_weight,
            reverse=True,
        )
        deliberations = "\n\n".join(
            f"[{role.upper()}] (weight={self._agents[AgentRole(role)].routing_weight:.2f})\n{text[:600]}"
            for role, text in sorted_outputs
        )

        # Synthesise — trim history to avoid context overflow on local models
        hist: list[dict[str, str]] = (context or {}).get("history", [])
        messages: list[dict[str, str]] = [{"role": "system", "content": _build_synthesis_system()}]
        for msg in _trim_history(hist):
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({
            "role": "user",
            "content": _SYNTHESIS_TEMPLATE.format(
                user_input=user_input,
                memories=_fmt_memories(context),
                wiki=_fmt_wiki(context),
                deliberations=deliberations,
            ),
        })
        # Use chat_with_tools so the LLM can invoke MCP tools (web search, fetch, fs)
        response = await llm.chat_with_tools(messages, temperature=0.7, max_tokens=settings.llm_max_tokens_synthesis)
        return response, agent_outputs

    async def stream(
        self,
        user_input: str,
        workspace: WorkspaceSnapshot,
        meta_state: MetaState,
        context: dict[str, Any] | None = None,
    ):
        """Stream the synthesis phase (agents run upfront with bounded concurrency)."""
        self._apply_routing_weights(meta_state)

        active_count = sum(
            1 for a in self._agents.values() if a.routing_weight > 0.01
        )
        yield {"_status": f"Consulting {active_count} specialist perspectives…"}

        agent_outputs = await self._run_agents_bounded(
            user_input, workspace, meta_state, context
        )

        # Sort by routing weight (descending) — filter disabled agents and empty outputs
        sorted_outputs = sorted(
            (
                (role, text)
                for role, text in agent_outputs.items()
                if text and self._agents[AgentRole(role)].routing_weight > 0.01
            ),
            key=lambda kv: self._agents[AgentRole(kv[0])].routing_weight,
            reverse=True,
        )
        active_voices = [role for role, _ in sorted_outputs]
        voices_label = ", ".join(r.capitalize() for r in active_voices) if active_voices else "none"
        yield {"_status": f"Synthesizing ({voices_label})…"}

        deliberations = "\n\n".join(
            f"[{role.upper()}]\n{text[:600]}" for role, text in sorted_outputs
        )
        # Synthesise — trim history to avoid context overflow on local models
        hist: list[dict[str, str]] = (context or {}).get("history", [])
        messages: list[dict[str, str]] = [{"role": "system", "content": _build_synthesis_system()}]
        for msg in _trim_history(hist):
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({
            "role": "user",
            "content": _SYNTHESIS_TEMPLATE.format(
                user_input=user_input,
                memories=_fmt_memories(context),
                wiki=_fmt_wiki(context),
                deliberations=deliberations,
            ),
        })
        async for delta in llm.stream_chat_with_tools(messages, temperature=0.7, max_tokens=settings.llm_max_tokens_synthesis):
            yield delta
