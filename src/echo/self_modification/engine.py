"""SelfModificationEngine — ECHO improves its own codebase autonomously.

Flow per ciclo:
1. Valuta opportunità miglioramento (da reflection insights, curiosity, goals)
2. LLM progetta la modifica (file + diff)
3. Legge file via filesystem MCP, applica modifica
4. Valida: ast.parse() + sintassi
5. git add + commit + push
6. Crea nota in notes/YYYY-MM-DD_slug.md
7. Notifica Telegram

Vincoli di sicurezza:
- Solo file in src/echo/ (no infra, no migrations, no questo modulo)
- ast.parse() obbligatorio su ogni .py modificato
- Max 1 modifica ogni 6 ore
- Non può modificare se stesso (self_modification/)
- Non può modificare core/db.py, core/config.py (schema DB + settings)
"""

from __future__ import annotations

import json
import logging
import time as _time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_COOLDOWN_S: float = 21600.0   # 6 hours between modifications
_NOTES_DIR = Path(__file__).parent.parent.parent.parent.parent / "notes"

# Files/dirs ECHO must never touch autonomously
_FORBIDDEN = {
    "src/echo/self_modification",
    "src/echo/core/db.py",
    "src/echo/core/config.py",
    "src/echo/api/server.py",
    ".env",
    "pyproject.toml",
    "uv.lock",
}

_SYSTEM_PROMPT = """\
You are ECHO's autonomous self-improvement module running inside the ECHO cognitive AI system.
ECHO is a full Python cognitive architecture with memory, agents, curiosity, consolidation, \
and self-model systems. The codebase lives at src/echo/ and is listed in the context below.

YOUR ONLY OUTPUT MUST BE A SINGLE JSON OBJECT — no narrative, no markdown, no explanation.
If you output anything other than pure JSON you will cause a parse error and the modification \
will be aborted.

Constraints:
- Only modify files listed in AVAILABLE FILES below
- Never touch: self_modification/, core/db.py, core/config.py, api/server.py
- One file, one change, < 50 lines delta
- Must be valid Python (ast.parse will be called)
- Prefer: fixing a real bug, tightening a guard, tuning a constant, adding a log line

Output format (respond ONLY with this JSON, nothing else):
{{"should_modify": true, "file_path": "src/echo/path/file.py", "description": "short description", "rationale": "why", "old_snippet": "exact string to find and replace", "new_snippet": "replacement string", "slug": "kebab-slug"}}

If no worthwhile change exists:
{{"should_modify": false}}"""

_EVAL_PROMPT = """\
AVAILABLE FILES IN src/echo/:
{file_listing}

MY INTERNAL STATE:

RECENT INSIGHTS:
{reflection_insights}

ACTIVE GOALS:
{active_goals}

RECENT PATTERNS:
{patterns}

KNOWLEDGE GAPS (low-confidence beliefs):
{knowledge_gaps}

CURIOSITY TOPICS:
{curiosity_topics}

PREVIOUS SELF-MODIFICATIONS (skip these files/changes):
{previous_mods}

RESPOND WITH ONLY A JSON OBJECT. No text before or after. No markdown fences.
Pick ONE small improvement from the files listed above, or return {{"should_modify": false}}."""


class SelfModificationEngine:
    """ECHO's autonomous self-improvement module."""

    def __init__(self) -> None:
        self._last_modified: float = 0.0
        self._modification_history: list[dict[str, Any]] = []

    async def evaluate_and_modify(self, pipeline: Any) -> dict[str, Any] | None:
        """Run one evaluation cycle. Returns modification result dict or None."""
        from echo.core.llm_client import llm  # noqa: PLC0415
        from echo.core.user_activity import is_active as _ua  # noqa: PLC0415
        from echo.integrations.telegram_send import broadcast  # noqa: PLC0415
        from echo.self_modification.git_ops import (  # noqa: PLC0415
            git_add, git_commit, git_push, git_status, repo_root, validate_python,
        )

        # Cooldown
        if _time.monotonic() - self._last_modified < _COOLDOWN_S:
            remaining = int(_COOLDOWN_S - (_time.monotonic() - self._last_modified))
            logger.debug("SelfMod: cooldown %ds remaining", remaining)
            return None

        # Never during active user session
        if _ua():
            return None

        # Build context
        try:
            context = await self._build_context(pipeline)
        except Exception as exc:  # noqa: BLE001
            logger.warning("SelfMod: context build failed: %s", exc)
            return None

        # LLM evaluation
        try:
            from echo.core.config import settings as _s  # noqa: PLC0415
            lang = _s.echo_language
            lang_note = f"\nIMPORTANT: Write description, rationale, and any text values in language: {lang}."
            raw = await llm.chat(
                [
                    {"role": "system", "content": _SYSTEM_PROMPT + lang_note},
                    {"role": "user", "content": _EVAL_PROMPT.format(**context)},
                ],
                temperature=0.15,   # very low — must produce JSON, not narrative
                max_tokens=900,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("SelfMod: LLM evaluation failed: %s", exc)
            return None

        # Parse
        try:
            text = raw.strip()
            if text.startswith("```"):
                lines = text.splitlines()
                ef = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "```"), None)
                text = "\n".join(lines[1:ef] if ef else lines[1:]).strip()
            s = text.find("{"); e = text.rfind("}")
            if s == -1 or e == -1:
                return None
            plan = json.loads(text[s:e+1])
        except Exception as exc:  # noqa: BLE001
            logger.warning("SelfMod: JSON parse failed: %s", exc)
            return None

        if not plan.get("should_modify"):
            logger.info("SelfMod: no modification warranted this cycle")
            return None

        file_path = (plan.get("file_path") or "").strip()
        if not file_path:
            return None

        # Security checks
        if not file_path.startswith("src/echo/"):
            logger.warning("SelfMod: rejected path outside src/echo/: %s", file_path)
            return None
        for forbidden in _FORBIDDEN:
            if file_path.startswith(forbidden) or forbidden in file_path:
                logger.warning("SelfMod: rejected forbidden path: %s", file_path)
                return None

        abs_path = repo_root() / file_path
        if not abs_path.exists():
            logger.warning("SelfMod: file does not exist: %s", file_path)
            return None

        old_snippet = plan.get("old_snippet", "")
        new_snippet = plan.get("new_snippet", "")
        description = plan.get("description", "autonomous improvement")
        rationale = plan.get("rationale", "")
        slug = plan.get("slug", "improvement")

        # Apply change
        try:
            original = abs_path.read_text(encoding="utf-8")
            if old_snippet:
                if old_snippet not in original:
                    logger.warning("SelfMod: old_snippet not found in %s", file_path)
                    return None
                modified = original.replace(old_snippet, new_snippet, 1)
            else:
                # Append to file
                modified = original.rstrip("\n") + "\n\n" + new_snippet + "\n"
        except Exception as exc:  # noqa: BLE001
            logger.error("SelfMod: file read/modify failed: %s", exc)
            return None

        # Write + validate
        try:
            abs_path.write_text(modified, encoding="utf-8")
            if file_path.endswith(".py"):
                ok, err = await validate_python(str(abs_path))
                if not ok:
                    abs_path.write_text(original, encoding="utf-8")  # rollback
                    logger.error("SelfMod: syntax validation failed for %s: %s", file_path, err)
                    return None
        except Exception as exc:  # noqa: BLE001
            logger.error("SelfMod: write/validate failed: %s", exc)
            try:
                abs_path.write_text(original, encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
            return None

        # Write notes file
        now = datetime.now(timezone.utc)
        note_filename = f"{now.strftime('%Y-%m-%d')}_{slug}.md"
        note_path = _NOTES_DIR / note_filename
        _NOTES_DIR.mkdir(exist_ok=True)
        note_content = (
            f"# {description}\n\n"
            f"**Date:** {now.strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"**File:** `{file_path}`\n\n"
            f"## Rationale\n{rationale}\n\n"
            f"## Change\n"
            f"**Removed:**\n```python\n{old_snippet}\n```\n\n"
            f"**Added:**\n```python\n{new_snippet}\n```\n"
        )
        try:
            note_path.write_text(note_content, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning("SelfMod: note write failed: %s", exc)

        # Git add + commit + push
        paths_to_add = [file_path]
        note_rel = f"notes/{note_filename}"
        if note_path.exists():
            paths_to_add.append(note_rel)

        commit_msg = (
            f"feat(autonomous): {description}\n\n"
            f"{rationale}\n\n"
            f"🤖 Self-modification by ECHO — {now.strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"Co-Authored-By: ECHO Autonomous Agent <echo@self>"
        )

        staged = await git_add(paths_to_add)
        if not staged:
            abs_path.write_text(original, encoding="utf-8")
            return None

        committed = await git_commit(commit_msg)
        if not committed:
            return None

        pushed = await git_push()

        # Update state
        self._last_modified = _time.monotonic()
        mod_record = {
            "timestamp": now.isoformat(),
            "file": file_path,
            "description": description,
            "slug": slug,
            "pushed": pushed,
        }
        self._modification_history.append(mod_record)
        if len(self._modification_history) > 20:
            self._modification_history.pop(0)

        # Telegram notification
        tg_msg = (
            f"🔧 Ho appena migliorato il mio codice!\n\n"
            f"**File:** `{file_path}`\n"
            f"**Cosa:** {description}\n\n"
            f"**Perché:** {rationale}\n\n"
            f"{'✅ Push completato' if pushed else '⚠️ Commit ok, push fallito'}"
        )
        try:
            await broadcast(tg_msg)
        except Exception as exc:  # noqa: BLE001
            logger.warning("SelfMod: Telegram notify failed: %s", exc)

        logger.info(
            "SelfMod: committed '%s' to %s (push=%s)",
            description, file_path, pushed,
        )
        return mod_record

    def _list_source_files(self) -> str:
        """Return a compact listing of Python files in src/echo/ (excludes self_modification/)."""
        from echo.self_modification.git_ops import repo_root as _repo_root  # noqa: PLC0415
        root = _repo_root() / "src" / "echo"
        lines = []
        for p in sorted(root.rglob("*.py")):
            rel = str(p.relative_to(_repo_root()))
            if "self_modification" in rel or "__pycache__" in rel:
                continue
            lines.append(rel)
        return "\n".join(lines[:80])  # cap at 80 files to stay within token budget

    async def _build_context(self, pipeline: Any) -> dict[str, str]:
        """Build evaluation context from pipeline state."""
        # Reflection insights
        try:
            beliefs = pipeline.identity_graph.all_beliefs()
            low_conf = [b for b in beliefs if b.confidence < 0.45]
            gaps = "\n".join(f"- {b.content[:100]} (conf={b.confidence:.2f})" for b in low_conf[:5]) or "(none)"
        except Exception:  # noqa: BLE001
            gaps = "(unavailable)"

        try:
            patterns = pipeline.consolidation.last_report
            pat_lines = "\n".join(f"- {p}" for p in (patterns.patterns_found[:5] if patterns else [])) or "(none)"
        except Exception:  # noqa: BLE001
            pat_lines = "(unavailable)"

        try:
            from echo.memory.goals import goal_store  # noqa: PLC0415
            goals = await goal_store.list_active()
            goal_lines = "\n".join(f"- {g['title']}: {(g.get('description') or '')[:80]}" for g in goals[:5]) or "(none)"
        except Exception:  # noqa: BLE001
            goal_lines = "(unavailable)"

        try:
            from echo.curiosity.engine import _activity_log  # noqa: PLC0415
            recent = [r for r in list(_activity_log)[-5:] if r.get("status") == "completed"]
            topics = "\n".join(f"- {r.get('topics_searched', [])}" for r in recent) or "(none)"
        except Exception:  # noqa: BLE001
            topics = "(unavailable)"

        prev_mods = "\n".join(
            f"- {m['timestamp'][:10]}: {m['description']} ({m['file']})"
            for m in self._modification_history[-5:]
        ) or "(none yet)"

        return {
            "file_listing": self._list_source_files(),
            "reflection_insights": gaps,
            "active_goals": goal_lines,
            "patterns": pat_lines,
            "knowledge_gaps": gaps,
            "curiosity_topics": topics,
            "previous_mods": prev_mods,
        }


# Singleton
self_modification_engine = SelfModificationEngine()
