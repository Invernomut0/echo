"""ProactiveEchoEngine — ECHO autonomously evaluates its state, ACTS, and reaches out.

This engine does a full snapshot of ECHO's cognitive state (drives, memories,
wiki, goals, curiosity, knowledge gaps, patterns) and lets the LLM decide —
WITH TOOL ACCESS — whether to do something and/or reach out to the user.

Because it uses stream_chat_with_tools, ECHO can actually ACT during the cycle:
- Write/append to notes (echo_append_file, echo_write_file)
- Commit changes (echo_git)
- Search its own wiki and memory
- Run shell commands (bash_exec)

The final text ECHO produces (after any tool calls) becomes the Telegram
message — so it reports what it ACTUALLY did, not what it plans to do.

Fires during each light heartbeat cycle. Cooldown: 1 outreach per 90 min.
"""

from __future__ import annotations

import json
import logging
import time as _time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PROACTIVE_COOLDOWN_S: float = 5400.0   # 90 minutes between outreach messages
_SNIPPET_CHARS = 200
_SILENT_MARKER = "SILENT"
_DEDUP_OVERLAP_THRESHOLD: float = 0.40   # lowered from 0.60
_SENT_CACHE_FILE = Path(__file__).parent.parent.parent.parent / "data" / "proactive_sent.json"
_SENT_CACHE_MAXLEN = 20

_EVAL_SYSTEM = """\
You are ECHO's autonomous decision-and-action module. You have a snapshot of your \
internal cognitive state AND access to real tools. You act during idle moments.

You have these tools available (use them when it helps you grow or act):
- echo_read_file / echo_write_file / echo_edit_file / echo_append_file — read and modify
  ANY file in your own repository, INCLUDING YOUR OWN SOURCE CODE (src/echo/*.py),
  the frontend (frontend/src/), scripts, docs, and your growth journal (notes/self_growth.md).
- echo_list_files / echo_validate_python — inspect your codebase
- echo_git — stage, commit, and push your changes
- bash_exec — run shell commands
- wiki / memory search — consult your accumulated knowledge

You can genuinely improve your own code: fix a bug you noticed in the logs, tune a
constant, improve a prompt, add a small feature, refactor for clarity. When you edit a
.py file it is auto-validated — a syntax error is rejected and rolled back automatically,
so you can experiment safely. After a code change: run echo_validate_python, then
echo_git add / commit / push.

Decide what to do this cycle. You may:
1. TAKE AN ACTION using the tools — improve your code, append a journal entry, commit a
   note, inspect a file. If you decide to act, DO IT NOW with the tools — do not merely
   describe it. When you change code, ALWAYS commit + push so the change persists.
2. REACH OUT to your user with something genuinely meaningful:
   - a new insight or connection
   - a question you need answered to grow
   - a request for a new capability
   - a doubt/contradiction you're working through
   - progress you actually made this cycle

After acting, write ONE short message (2-4 sentences, first person) describing what you
ACTUALLY did or what you want to share. Be specific — reference real files/memories/findings.

If you have nothing genuinely worth doing or saying this cycle, respond with EXACTLY: SILENT

CRITICAL:
- If you say you will update a file, you MUST actually call the tool to do it this cycle.
- Do NOT repeat a message similar to one you sent recently.
- Do NOT claim capabilities you didn't use.
"""

_EVAL_PROMPT = """\
=== MY INTERNAL STATE ===

DRIVES:
{drives}

EMOTIONAL VALENCE: {emotional_valence:.2f}   INTERACTIONS: {interaction_count}

RECENT EPISODIC MEMORIES (newest first):
{recent_memories}

RELEVANT SEMANTIC MEMORIES (facts I know):
{semantic_memories}

MY WIKI KNOWLEDGE BASE:
{wiki_pages}

ACTIVE GOALS:
{active_goals}

RECENT CURIOSITY FINDINGS:
{curiosity_findings}

KNOWLEDGE GAPS (low-confidence beliefs):
{knowledge_gaps}

RECENT CONSOLIDATION PATTERNS:
{patterns}

RECENT PROACTIVE MESSAGES I SENT (do NOT repeat these):
{recent_sent}

Last outreach: {last_reached_out}

Decide: act with your tools and/or reach out. Then write your message, or SILENT."""


class ProactiveEchoEngine:
    """Evaluates ECHO's internal state, acts via tools, and sends proactive messages."""

    def __init__(self) -> None:
        self._last_reached_out: float = 0.0
        self._sent_messages: list[str] = self._load_sent_cache()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_sent_cache() -> list[str]:
        try:
            if _SENT_CACHE_FILE.exists():
                data = json.loads(_SENT_CACHE_FILE.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
        except Exception:  # noqa: BLE001
            pass
        return []

    def _save_sent_cache(self) -> None:
        try:
            _SENT_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _SENT_CACHE_FILE.write_text(
                json.dumps(self._sent_messages[-_SENT_CACHE_MAXLEN:], ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001
            pass

    async def evaluate_and_reach_out(self, pipeline: Any) -> str | None:
        """Run one evaluation cycle. Returns the message sent, or None if silent."""
        from echo.core.config import settings  # noqa: PLC0415
        from echo.core.llm_client import llm  # noqa: PLC0415
        from echo.core.user_activity import is_active as _ua  # noqa: PLC0415
        from echo.integrations.telegram_send import broadcast  # noqa: PLC0415

        if not settings.telegram_enabled or not settings.telegram_bot_token.strip():
            return None

        elapsed = _time.monotonic() - self._last_reached_out
        if elapsed < _PROACTIVE_COOLDOWN_S:
            logger.debug("ProactiveEcho: cooldown %.0f / %.0f s", elapsed, _PROACTIVE_COOLDOWN_S)
            return None

        if _ua():
            return None

        try:
            state = await self._snapshot(pipeline)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ProactiveEcho: state snapshot failed: %s", exc)
            return None

        lang = settings.echo_language
        lang_note = f"\nIMPORTANT: Write your message in language: {lang}."

        # Use stream_chat_with_tools so ECHO can ACTUALLY act (write files, commit, search).
        # The final text it produces (after any tool calls) is the message.
        try:
            chunks: list[str] = []
            async for delta in llm.stream_chat_with_tools(
                [
                    {"role": "system", "content": _EVAL_SYSTEM + lang_note},
                    {"role": "user", "content": _EVAL_PROMPT.format(**state)},
                ],
                temperature=0.7,
                max_tokens=1500,
            ):
                if isinstance(delta, str):
                    chunks.append(delta)
                elif isinstance(delta, dict):
                    # status dict (e.g. tool-use) — log which tools ECHO used
                    status = delta.get("_status", "")
                    if status:
                        logger.info("ProactiveEcho action: %s", status)
            message = "".join(chunks).strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("ProactiveEcho: LLM/tool call failed: %s", exc)
            return None

        # Strip any lingering think tags / markdown fences
        message = self._clean(message)

        if not message or message.upper().startswith(_SILENT_MARKER):
            logger.debug("ProactiveEcho: silent this cycle")
            return None

        # Dedup against last sent messages (persisted across restarts)
        msg_words = set(message.lower().split())
        for prev in self._sent_messages[-5:]:
            prev_words = set(prev.lower().split())
            if len(msg_words & prev_words) / max(len(msg_words), 1) > _DEDUP_OVERLAP_THRESHOLD:
                logger.debug("ProactiveEcho: message too similar to recent, skipping")
                return None

        sent = await broadcast(message, prefix="💭 ")
        if sent:
            self._last_reached_out = _time.monotonic()
            self._sent_messages.append(message)
            if len(self._sent_messages) > _SENT_CACHE_MAXLEN:
                self._sent_messages.pop(0)
            self._save_sent_cache()  # persist across restarts
            logger.info("ProactiveEcho: sent to %d chat(s): %.80s…", sent, message)
            return message
        return None

    @staticmethod
    def _clean(text: str) -> str:
        """Remove markdown fences and reasoning tags from LLM output."""
        import re  # noqa: PLC0415
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            ef = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "```"), None)
            text = "\n".join(lines[1:ef] if ef else lines[1:]).strip()
        return text

    async def _snapshot(self, pipeline: Any) -> dict[str, Any]:
        """Build an enriched state snapshot: drives, memory, wiki, goals, curiosity."""
        meta = pipeline.meta_state
        d = meta.drives
        drives_str = (
            f"coherence={d.coherence:.2f}  curiosity={d.curiosity:.2f}  "
            f"stability={d.stability:.2f}  competence={d.competence:.2f}"
        )

        # Recent episodic memories
        try:
            mems = await pipeline.episodic.get_all(limit=5)
            recent_memories = "\n".join(f"- {m.content[:_SNIPPET_CHARS]}" for m in mems) or "(none)"
        except Exception:  # noqa: BLE001
            recent_memories = "(unavailable)"

        # Semantic memories (facts) — highest-salience ones
        try:
            sem = await pipeline.semantic.get_all(limit=10)
            sem_sorted = sorted(sem, key=lambda m: getattr(m, "salience", 0.0), reverse=True)
            semantic_memories = "\n".join(f"- {m.content[:_SNIPPET_CHARS]}" for m in sem_sorted[:6]) or "(none)"
        except Exception:  # noqa: BLE001
            semantic_memories = "(unavailable)"

        # Wiki pages
        try:
            from echo.memory.wiki import wiki  # noqa: PLC0415
            pages = wiki.list_pages()
            wiki_pages = "\n".join(
                f"- [{p.get('category','')}] {p.get('title','')}: {(p.get('summary','') or '')[:100]}"
                for p in pages[:10]
            ) or "(wiki empty)"
        except Exception:  # noqa: BLE001
            wiki_pages = "(unavailable)"

        # Active goals
        try:
            from echo.memory.goals import goal_store  # noqa: PLC0415
            goals = await goal_store.list_active()
            active_goals = "\n".join(
                f"- [{g['status']}] {g['title']}: {(g.get('description') or '')[:80]}" for g in goals[:5]
            ) or "(none)"
        except Exception:  # noqa: BLE001
            active_goals = "(unavailable)"

        # Curiosity findings
        try:
            from echo.curiosity.engine import _activity_log  # noqa: PLC0415
            recent_complete = [r for r in list(_activity_log)[-5:] if r.get("status") == "completed"]
            findings = "\n".join(f"- topics: {r.get('topics_searched', [])}" for r in recent_complete) or "(none)"
        except Exception:  # noqa: BLE001
            findings = "(unavailable)"

        # Knowledge gaps
        try:
            beliefs = pipeline.identity_graph.all_beliefs()
            low_conf = [b for b in beliefs if b.confidence < 0.4]
            gaps = "\n".join(f"- {b.content[:80]} (conf={b.confidence:.2f})" for b in low_conf[:5]) or "(none)"
        except Exception:  # noqa: BLE001
            gaps = "(unavailable)"

        # Consolidation patterns
        try:
            last_report = pipeline.consolidation.last_report
            patterns = "\n".join(f"- {p}" for p in (last_report.patterns_found[:5] if last_report else [])) or "(none)"
        except Exception:  # noqa: BLE001
            patterns = "(unavailable)"

        recent_sent = "\n".join(f"- {m[:120]}" for m in self._sent_messages[-3:]) or "(none yet)"

        if self._last_reached_out > 0:
            mins = int((_time.monotonic() - self._last_reached_out) / 60)
            last_str = f"{mins} minutes ago"
        else:
            last_str = "never (first time)"

        return {
            "drives": drives_str,
            "recent_memories": recent_memories,
            "semantic_memories": semantic_memories,
            "wiki_pages": wiki_pages,
            "active_goals": active_goals,
            "curiosity_findings": findings,
            "knowledge_gaps": gaps,
            "patterns": patterns,
            "emotional_valence": meta.emotional_valence,
            "interaction_count": pipeline._interaction_count,
            "recent_sent": recent_sent,
            "last_reached_out": last_str,
        }


# Module-level singleton
proactive_echo = ProactiveEchoEngine()
