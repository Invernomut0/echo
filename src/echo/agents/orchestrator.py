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

Internal deliberations from cognitive agents:
{deliberations}

Synthesise a single response. If memories reveal the user's name or past context, use it naturally."""


def _build_synthesis_system() -> str:
    """Return the synthesis system prompt, dynamically augmented with available MCP tools.

    Late-imports ``mcp_manager`` to avoid circular imports at module load time.
    If no tools are connected (e.g. during tests) falls back to the base prompt.
    """
    try:
        from echo.mcp import mcp_manager  # noqa: PLC0415
        tools = mcp_manager.list_tools()
    except Exception:  # noqa: BLE001
        tools = []

    if not tools:
        return _SYNTHESIS_SYSTEM

    tool_lines = "\n".join(
        f"  • **{t.qualified_name}**: {t.description}"
        for t in tools
    )
    mcp_addendum = f"""

EXTERNAL TOOLS (real, callable NOW via function-calling):
You have access to the following MCP tools. Use them proactively whenever the request
benefits from live data, web searches, URL fetching, or file operations.
Do NOT claim you cannot access external resources — you can, via these tools.

{tool_lines}

Tool usage rules:
- brave_search__* : web search, local business search, current events.
- fetch__fetch : fetch the content of any URL.
- filesystem__* : read/write files in /tmp.
- Always share what you found with the user. Report errors honestly."""

    return _SYNTHESIS_SYSTEM + mcp_addendum


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

        # BUG-9: Sort deliberations by routing weight (descending) so the LLM
        # synthesis stage naturally gives more attention to high-weight agents
        # (LLMs exhibit primacy bias — earlier context gets more weight).
        sorted_outputs = sorted(
            ((role, text) for role, text in agent_outputs.items() if text),
            key=lambda kv: self._agents[AgentRole(kv[0])].routing_weight,
            reverse=True,
        )
        deliberations = "\n\n".join(
            f"[{role.upper()}] (weight={self._agents[AgentRole(role)].routing_weight:.2f})\n{text}"
            for role, text in sorted_outputs
        )

        # Synthesise — include recent conversation history for multi-turn coherence.
        # History comes from context["history"] (set by pipeline.stream_interact).
        hist: list[dict[str, str]] = (context or {}).get("history", [])
        # Build system prompt dynamically (injects available MCP tool descriptions)
        messages: list[dict[str, str]] = [{"role": "system", "content": _build_synthesis_system()}]
        for msg in hist[-10:]:  # cap at 10 messages to stay within token limits
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({
            "role": "user",
            "content": _SYNTHESIS_TEMPLATE.format(
                user_input=user_input,
                memories=_fmt_memories(context),
                deliberations=deliberations,
            ),
        })
        # Use chat_with_tools so the LLM can invoke MCP tools (web search, fetch, fs)
        response = await llm.chat_with_tools(messages, temperature=0.7, max_tokens=1024)
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
                agent_outputs[role.value] = ""

        # Sort by routing weight (descending) — same primacy-bias fix as run()
        sorted_outputs = sorted(
            ((role, text) for role, text in agent_outputs.items() if text),
            key=lambda kv: self._agents[AgentRole(kv[0])].routing_weight,
            reverse=True,
        )
        deliberations = "\n\n".join(
            f"[{role.upper()}]\n{text}" for role, text in sorted_outputs
        )
        # Synthesise — include recent conversation history for multi-turn coherence.
        hist: list[dict[str, str]] = (context or {}).get("history", [])
        # Build system prompt dynamically (injects available MCP tool descriptions)
        messages: list[dict[str, str]] = [{"role": "system", "content": _build_synthesis_system()}]
        for msg in hist[-10:]:  # cap at 10 messages to stay within token limits
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({
            "role": "user",
            "content": _SYNTHESIS_TEMPLATE.format(
                user_input=user_input,
                memories=_fmt_memories(context),
                deliberations=deliberations,
            ),
        })
        # Use stream_chat_with_tools: streams normally when no tools are needed;
        # runs the agentic tool-call loop and yields the final text when tools are used.
        async for delta in llm.stream_chat_with_tools(messages, temperature=0.7, max_tokens=1024):
            yield delta
