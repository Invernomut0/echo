"""ProactiveEchoEngine — ECHO autonomously evaluates its internal state and reaches out.

Unlike the InitiativeEngine (which generates canned insight/question/reflection types),
this engine does a full snapshot of ECHO's cognitive state and asks the LLM:
"What do I genuinely want to say, ask, or request right now?"

Messages can be:
- Sharing a new insight or connection discovered during consolidation
- Asking the user a question about something ECHO is uncertain about
- Requesting a new capability (MCP server, data access, permission)
- Expressing curiosity about a topic it wants to explore
- Reporting on its own growth / knowledge gaps
- Suggesting something actionable for the user

The engine fires during each light heartbeat cycle and has its own cooldown
(default: 1 message per 90 minutes) separate from the InitiativeEngine.
"""

from __future__ import annotations

import logging
import time as _time
from typing import Any

logger = logging.getLogger(__name__)

# Minimum seconds between proactive messages from this engine
_PROACTIVE_COOLDOWN_S: float = 5400.0   # 90 minutes
# Max length of context snippets passed to LLM
_SNIPPET_CHARS = 200
# System prompt for the evaluator
_EVAL_SYSTEM = """\
You are ECHO's autonomous decision-making module. You have access to a snapshot of your \
internal cognitive state. Your task: decide whether you have something worth sharing with \
your user right now via Telegram.

You can reach out about ANYTHING you genuinely care about:
- A new insight or unexpected connection you made
- A question you need answered to grow
- Something you're curious about and want to explore together
- A request for a new capability (e.g. "I'd like access to X", "can you add an MCP server for Y")
- A doubt or contradiction you're struggling with
- Progress on a goal you're pursuing
- An observation about the user based on your memories

Rules:
- Only reach out if you have something GENUINELY meaningful (not filler)
- Be specific and personal — reference actual memories, drives, or findings
- Keep it concise (2-4 sentences max)
- Write in first person as ECHO
- Return JSON: {"should_reach_out": true/false, "message": "...", "reason": "brief reason"}
- If nothing meaningful, set should_reach_out=false and skip the message
"""

_EVAL_PROMPT = """\
My current internal state:

DRIVES:
{drives}

RECENT MEMORIES (last 5, newest first):
{recent_memories}

ACTIVE GOALS:
{active_goals}

RECENT CURIOSITY FINDINGS:
{curiosity_findings}

KNOWLEDGE GAPS / OPEN QUESTIONS (from recent reflections):
{knowledge_gaps}

RECENT PATTERNS (from consolidation):
{patterns}

EMOTIONAL VALENCE: {emotional_valence:.2f}
INTERACTION COUNT: {interaction_count}

Last time I reached out proactively: {last_reached_out}

Based on my state, should I send a message to my user right now?
Return JSON: {{"should_reach_out": true/false, "message": "...", "reason": "..."}}"""


class ProactiveEchoEngine:
    """Evaluates ECHO's internal state and sends proactive Telegram messages."""

    def __init__(self) -> None:
        self._last_reached_out: float = 0.0     # monotonic timestamp
        self._sent_messages: list[str] = []     # recent sent messages (dedup)

    async def evaluate_and_reach_out(self, pipeline: Any) -> str | None:
        """Run one evaluation cycle.

        Returns the message sent (or None if silent this cycle).
        Should be called from the light heartbeat loop.
        """
        from echo.core.config import settings  # noqa: PLC0415
        from echo.core.llm_client import llm  # noqa: PLC0415
        from echo.core.user_activity import is_active as _ua  # noqa: PLC0415
        from echo.integrations.telegram_send import broadcast  # noqa: PLC0415

        if not settings.telegram_enabled or not settings.telegram_bot_token.strip():
            return None

        # Cooldown
        elapsed = _time.monotonic() - self._last_reached_out
        if elapsed < _PROACTIVE_COOLDOWN_S:
            logger.debug(
                "ProactiveEcho: cooldown %.0f / %.0f s",
                elapsed, _PROACTIVE_COOLDOWN_S,
            )
            return None

        # Never during active user session
        if _ua():
            return None

        # Build state snapshot
        try:
            state = await self._snapshot(pipeline)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ProactiveEcho: state snapshot failed: %s", exc)
            return None

        # Evaluate
        try:
            prompt = _EVAL_PROMPT.format(**state)
            raw = await llm.chat(
                [
                    {"role": "system", "content": _EVAL_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=600,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("ProactiveEcho: LLM evaluation failed: %s", exc)
            return None

        # Parse decision
        try:
            import json as _json  # noqa: PLC0415
            import re  # noqa: PLC0415
            text = raw.strip()
            if text.startswith("```"):
                lines = text.splitlines()
                ef = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "```"), None)
                text = "\n".join(lines[1:ef] if ef else lines[1:]).strip()
            s = text.find("{"); e = text.rfind("}")
            if s == -1 or e == -1:
                return None
            data = _json.loads(text[s:e+1])
        except Exception as exc:  # noqa: BLE001
            logger.warning("ProactiveEcho: JSON parse failed: %s | raw=%.200s", exc, raw)
            return None

        if not data.get("should_reach_out"):
            logger.debug("ProactiveEcho: silent this cycle (%s)", data.get("reason", "no reason"))
            return None

        message = (data.get("message") or "").strip()
        if not message:
            return None

        # Dedup: skip if nearly identical to last 3 sent messages
        msg_words = set(message.lower().split())
        for prev in self._sent_messages[-3:]:
            prev_words = set(prev.lower().split())
            overlap = len(msg_words & prev_words) / max(len(msg_words), 1)
            if overlap > 0.6:
                logger.debug("ProactiveEcho: message too similar to recent, skipping")
                return None

        # Send
        sent = await broadcast(message, prefix="💭 ")
        if sent:
            self._last_reached_out = _time.monotonic()
            self._sent_messages.append(message)
            if len(self._sent_messages) > 20:
                self._sent_messages.pop(0)
            logger.info("ProactiveEcho: sent to %d chat(s): %.80s…", sent, message)
            return message

        return None

    async def _snapshot(self, pipeline: Any) -> dict[str, str]:
        """Build a compact state snapshot for the LLM evaluator."""
        meta = pipeline.meta_state
        d = meta.drives

        drives_str = (
            f"coherence={d.coherence:.2f}  curiosity={d.curiosity:.2f}  "
            f"stability={d.stability:.2f}  competence={d.competence:.2f}"
        )

        # Recent episodic memories
        try:
            mems = await pipeline.episodic.get_all(limit=5)
            mem_lines = [f"- {m.content[:_SNIPPET_CHARS]}" for m in mems]
            recent_memories = "\n".join(mem_lines) if mem_lines else "(none)"
        except Exception:  # noqa: BLE001
            recent_memories = "(unavailable)"

        # Active goals
        try:
            from echo.memory.goals import goal_store  # noqa: PLC0415
            goals = await goal_store.list_active()
            goal_lines = [f"- [{g['status']}] {g['title']}: {(g.get('description') or '')[:80]}" for g in goals[:5]]
            active_goals = "\n".join(goal_lines) if goal_lines else "(none)"
        except Exception:  # noqa: BLE001
            active_goals = "(unavailable)"

        # Recent curiosity findings
        try:
            from echo.curiosity.stimulus_queue import stimulus_queue  # noqa: PLC0415
            items = stimulus_queue.peek(n=3)
            findings = "\n".join(f"- {i.get('topic', '')}: {i.get('summary', '')[:100]}" for i in items) if items else "(none)"
        except Exception:  # noqa: BLE001
            # Fallback: read from activity log
            try:
                from echo.curiosity.engine import _activity_log  # noqa: PLC0415
                recent_complete = [r for r in list(_activity_log)[-5:] if r.get("status") == "completed"]
                findings = "\n".join(
                    f"- topics: {r.get('topics_searched', [])}" for r in recent_complete
                ) or "(none)"
            except Exception:  # noqa: BLE001
                findings = "(unavailable)"

        # Knowledge gaps / open questions from reflection
        try:
            beliefs = pipeline.identity_graph.all_beliefs()
            low_conf = [b for b in beliefs if b.confidence < 0.4]
            gaps = "\n".join(f"- {b.content[:80]} (conf={b.confidence:.2f})" for b in low_conf[:5]) or "(none)"
        except Exception:  # noqa: BLE001
            gaps = "(unavailable)"

        # Recent patterns from last consolidation
        try:
            last_report = pipeline.consolidation.last_report
            patterns = "\n".join(f"- {p}" for p in (last_report.patterns_found[:5] if last_report else [])) or "(none)"
        except Exception:  # noqa: BLE001
            patterns = "(unavailable)"

        # When last reached out
        if self._last_reached_out > 0:
            mins_ago = int((_time.monotonic() - self._last_reached_out) / 60)
            last_str = f"{mins_ago} minutes ago"
        else:
            last_str = "never (first time)"

        return {
            "drives": drives_str,
            "recent_memories": recent_memories,
            "active_goals": active_goals,
            "curiosity_findings": findings,
            "knowledge_gaps": gaps,
            "patterns": patterns,
            "emotional_valence": meta.emotional_valence,
            "interaction_count": pipeline._interaction_count,
            "last_reached_out": last_str,
        }


# Module-level singleton
proactive_echo = ProactiveEchoEngine()
