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

_AGENT_TIMEOUT_S: float = 60.0  # per-agent LLM call timeout — must survive provider 429 retries

# ---------------------------------------------------------------------------
# Dynamic agent routing — select only relevant agents per query
# ---------------------------------------------------------------------------

# Simple/conversational queries skip agents entirely (fast path)
_SIMPLE_PREFIXES: frozenset[str] = frozenset({
    "ciao", "hello", "hi", "hey", "salve", "buongiorno", "buonasera", "buonanotte",
    "grazie", "thanks", "thank you", "ok", "okay", "bene", "sì", "si", "no",
    "come stai", "come ti senti", "come va", "how are you", "what's up",
})

# Keyword signals → agent roles.  Each tuple: (keywords, [roles])
# Order matters for overlap resolution — more specific patterns first.
_ROUTING_SIGNALS: list[tuple[frozenset[str], list[str]]] = [
    # Memory / past / personal history → archivist essential
    (frozenset({"ricordi", "ricordo", "remember", "memory", "memori", "passato",
                "prima", "abbiamo", "parlato", "detto", "scorso", "ieri", "storia"}),
     ["archivist", "social_self"]),
    # Emotional / relational / personal wellbeing
    (frozenset({"senti", "sento", "feel", "feeling", "emozione", "emotion",
                "preoccupo", "felice", "triste", "paura", "amore", "relazione",
                "worried", "happy", "sad", "lonely", "relationship", "provo"}),
     ["social_self", "analyst"]),
    # Planning / action / goal / task
    (frozenset({"piano", "plan", "obiettivo", "goal", "fare", "devo", "dovresti",
                "come posso", "how can", "how do", "steps", "passi", "azione",
                "todo", "task", "progetto", "project", "implementa", "implement"}),
     ["planner", "analyst"]),
    # Critical / verify / doubt / contradiction
    (frozenset({"vero", "falso", "true", "false", "verifica", "verify", "prova",
                "prove", "dubbio", "doubt", "sbagliato", "wrong", "errore", "error",
                "sicuro", "sure", "certain", "davvero", "really", "contraddici"}),
     ["skeptic", "analyst"]),
    # Creative / hypothetical / imagination / novel connections
    (frozenset({"immagina", "imagine", "ipotesi", "hypothesis", "se fosse", "what if",
                "potrebbe", "could", "creativo", "creative", "idea", "novel",
                "connect", "connetti", "analogia", "analogy", "sogno", "dream"}),
     ["explorer", "analyst"]),
    # Factual / explain / definition / logical analysis
    (frozenset({"cos'è", "cosa è", "what is", "spiega", "explain", "definisci",
                "define", "perché", "why", "how", "come funziona", "analizza",
                "analyze", "differenza", "difference", "confronta", "compare"}),
     ["analyst", "archivist"]),
]

_ALL_ROLES: frozenset[str] = frozenset({"analyst", "explorer", "skeptic", "archivist", "social_self", "planner"})
# Queries above this word count always get full routing (complex enough to warrant it)
_FULL_ROUTING_WORD_THRESHOLD: int = 40


def _select_agents(text: str) -> frozenset[str] | None:
    """Return set of agent role names to activate, or None for full routing.

    No LLM call — pure keyword heuristic. Returns None when the query is
    complex/ambiguous enough that all agents should run.
    """
    stripped = text.strip().lower()
    words = stripped.split()

    # Simple greeting / ack → no agents (fast path handled in stream())
    if len(words) <= 18 and any(stripped.startswith(p) for p in _SIMPLE_PREFIXES):
        return frozenset()  # empty = fast path

    # Long/complex queries → full routing
    if len(words) >= _FULL_ROUTING_WORD_THRESHOLD:
        return None

    selected: list[str] = []
    word_set = frozenset(w.rstrip("?!.,;:") for w in words)

    for keywords, roles in _ROUTING_SIGNALS:
        if word_set & keywords:
            for r in roles:
                if r not in selected:
                    selected.append(r)

    if not selected:
        # No signal matched — medium query, use analyst + archivist as baseline
        return frozenset({"analyst", "archivist"})

    # Cap at 3 roles to keep latency low; return as frozenset
    return frozenset(selected[:3])

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


def _language_instruction() -> str:
    """Return a language directive based on settings.echo_language."""
    try:
        from echo.core.config import settings as _s  # noqa: PLC0415
        lang = _s.echo_language.strip().lower()
        if lang == "it":
            return "\nRispondi SEMPRE in italiano, indipendentemente dalla lingua del messaggio."
        if lang == "en":
            return "\nAlways respond in English."
        return f"\nAlways respond in {lang}."
    except Exception:  # noqa: BLE001
        return ""


def _build_synthesis_system() -> str:
    """Return the synthesis system prompt, dynamically augmented with available tools
    (both external MCP servers and ECHO's own internal tools such as cron management)
    and the metacognitive self-model.

    Late-imports ``mcp_manager`` to avoid circular imports at module load time.
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
        all_tools = mcp_manager.list_tools()
    except Exception:  # noqa: BLE001
        all_tools = []

    # Separate external MCP tools from ECHO's internal tools (server_name="echo")
    external_tools = [t for t in all_tools if t.server_name != "echo"]
    internal_tools = [t for t in all_tools if t.server_name == "echo"]

    if not external_tools and not internal_tools:
        return base

    # Cap external tool definitions to avoid blowing the context window.
    MAX_FULL_TOOLS = 5
    full_external = external_tools[:MAX_FULL_TOOLS]
    extra_external = external_tools[MAX_FULL_TOOLS:]

    addendum_parts: list[str] = []

    if external_tools:
        ext_lines = "\n".join(
            f"  • **{t.qualified_name}**: {t.description[:120]}"
            for t in full_external
        )
        if extra_external:
            extra_names = ", ".join(t.qualified_name for t in extra_external)
            ext_lines += f"\n  (also available: {extra_names})"
        addendum_parts.append(
            f"EXTERNAL TOOLS (callable via function-calling):\n{ext_lines}\n"
            "Rules: brave_search__* for web; fetch__fetch for URLs; "
            "filesystem__* for /tmp files."
        )

    if internal_tools:
        int_lines = "\n".join(
            f"  • **{t.qualified_name}**: {t.description[:140]}"
            for t in internal_tools
        )
        addendum_parts.append(
            f"ECHO INTERNAL TOOLS (your own cognitive scheduling system):\n{int_lines}\n"
            "Rules for echo__cron_* tools:\n"
            "- Use echo__cron_create_task when the user asks you to schedule a "
            "recurring activity, or when you decide to autonomously repeat a "
            "cognitive task (reflection, curiosity cycles, memory consolidation, etc.).\n"
            "- Use echo__cron_list_tasks to show or review current scheduled tasks.\n"
            "- Use echo__cron_update_task / echo__cron_delete_task to manage existing tasks.\n"
            "- Use echo__cron_trigger_task to run a task immediately on demand.\n"
            "- schedule_type='interval' takes seconds (e.g. '3600' = every hour). "
            "schedule_type='cron' takes a 5-field cron expression (min hour dom month dow)."
        )

    return base + "\n\n" + "\n\n".join(addendum_parts) + _language_instruction()


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
        role_filter: frozenset[str] | None = None,
    ) -> dict[str, str]:
        """Run selected agents with bounded concurrency; return {role: text}.

        Args:
            role_filter: if set, only run agents whose role.value is in this set.
                         None means run all active (routing_weight > 0.01) agents.
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

        # Apply role filter and weight gate
        pairs = [
            (role, agent)
            for role, agent in self._agents.items()
            if agent.routing_weight > 0.01
            and (role_filter is None or role.value in role_filter)
        ]
        results = await asyncio.gather(*(_run_one(role, agent) for role, agent in pairs))
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

        # Trim history and build base messages (shared by both paths)
        hist: list[dict[str, str]] = (context or {}).get("history", [])
        messages: list[dict[str, str]] = [{"role": "system", "content": _build_synthesis_system()}]
        for msg in _trim_history(hist):
            messages.append({"role": msg["role"], "content": msg["content"]})

        # Dynamic routing: select only relevant agents based on query content.
        # No extra LLM call — pure keyword heuristic.
        selected_roles = _select_agents(user_input)

        # Fast path: simple greeting/ack → no agents
        if selected_roles is not None and len(selected_roles) == 0:
            yield {"_status": "Formulating response…"}
            messages.append({
                "role": "user",
                "content": _SYNTHESIS_TEMPLATE.format(
                    user_input=user_input,
                    memories=_fmt_memories(context),
                    wiki=_fmt_wiki(context),
                    deliberations="",
                ),
            })
            async for delta in llm.stream_chat_with_tools(
                messages, temperature=0.7, max_tokens=settings.llm_max_tokens_synthesis
            ):
                yield delta
            return

        # Restrict agents to the selected subset (None = full routing)
        if selected_roles is not None:
            active_roles_label = ", ".join(r.capitalize() for r in sorted(selected_roles))
            yield {"_status": f"Consulting {active_roles_label}…"}
        else:
            active_count = sum(1 for a in self._agents.values() if a.routing_weight > 0.01)
            yield {"_status": f"Consulting {active_count} specialists…"}

        agent_outputs = await self._run_agents_bounded(
            user_input, workspace, meta_state, context,
            role_filter=selected_roles,
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
        messages.append({
            "role": "user",
            "content": _SYNTHESIS_TEMPLATE.format(
                user_input=user_input,
                memories=_fmt_memories(context),
                wiki=_fmt_wiki(context),
                deliberations=deliberations,
            ),
        })
        async for delta in llm.stream_chat_with_tools(
            messages, temperature=0.7, max_tokens=settings.llm_max_tokens_synthesis
        ):
            yield delta
