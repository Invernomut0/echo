# ECHO Session Dump — 2026-07-13

Use this file to resume work in a new LLM session. Contains full context needed to continue without re-reading the whole history.

---

## Current State

**Version:** 0.5.7 (to be cut)  
**Branch:** main  
**Last commit:** `241e523` — feat: REM cycle consolidates wiki — connect solitary entities  
**Git remote:** `https://github.com/Invernomut0/echo.git`

**Stack:**
- Python 3.12 FastAPI backend (uv) — `src/echo/`
- React 18 + TypeScript + Vite frontend — `frontend/src/`
- SQLAlchemy async + SQLite + ChromaDB
- APScheduler cron + consolidation scheduler
- MCP stdio servers in `scripts/`
- Telegram long-polling bridge

---

## Architecture Map (key files)

```
src/echo/
  core/
    config.py          — all settings (providers, telegram, language, wiki_sync, embedding)
    llm_client.py      — _RateLimiter 1.1s, stream_chat_with_tools, all 9 providers
    pipeline.py        — _interact_lock, advance_turn, web→telegram mirror
  agents/
    orchestrator.py    — keyword routing, _is_simple_query, _AGENT_TIMEOUT_S=60
  consolidation/
    scheduler.py       — light/deep/REM cycles, heartbeat events, wiki consolidation
    sleep_phase.py     — _dedup_episodic returns (count, pruned, pair_snippets) 3-tuple
  memory/
    wiki.py            — WikiStore + consolidate_connections(max_isolated=5)
    wiki_sync.py       — GitHub sync, stops on token_quota_exceeded, max_files=10
  initiative/
    proactive_engine.py — ProactiveEchoEngine, stream_chat_with_tools, 90min cooldown
  self_modification/
    engine.py          — full repo access (4 parents = repo root); forbidden: self_modification/engine.py, .env, data/sqlite, data/chroma
    git_ops.py         — REPO_ROOT = Path(__file__).parent.parent.parent.parent (4 parents)
  cron/
    executor.py        — self_modification task type, file_action support
    scheduler.py       — _migrate_task_types, _auto_achieve_file_goals, skip→no telegram
  curiosity/
    engine.py          — TTL cache, _cycle_counter, force=True, 5-min post-interaction silence
  integrations/
    telegram_bot.py    — _md_to_html, parse_mode=HTML, _bootstrap (deleteWebhook)
    telegram_send.py   — broadcast() centralized
  api/routers/
    setup.py           — _set_env_key patches os.environ + .env; _reload_settings

scripts/
  mcp_echo_workspace.py  — 7 tools: read/write/edit/append/list/git/validate
                           _write_with_validation: ast.parse() → auto-rollback on SyntaxError
                           forbidden: .env, self_modification/engine.py, data/sqlite, data/chroma
  mcp_bash_server.py     — bash_exec, blocked patterns, async stdio_server context manager

data/
  mcp.json               — echo-workspace (first), bash, opencode-mcp, fetch, filesystem, brave_search

notes/
  self_growth.md         — ECHO's autonomous growth journal

frontend/src/
  App.tsx                — mood labels EN, drive labels EN, provider/model badge, sentiment fill bars
  components/
    AnalyticsPanel.tsx   — all labels EN
    IdentityGraph.tsx    — all labels EN; tab GRAPH→MEMORY
```

---

## Critical Constants & Configs

| Setting | Value | Location |
|---------|-------|----------|
| Echo language | `ECHO_LANGUAGE=it` | `.env` |
| LLM rate limit | `1.1s` per call | `_RateLimiter` in `llm_client.py` |
| Agent timeout | `60s` | `_AGENT_TIMEOUT_S` in `orchestrator.py` |
| Proactive cooldown | `90 min` | `_PROACTIVE_COOLDOWN_S` in `proactive_engine.py` |
| Light cycle | `5 min` | `consolidation/scheduler.py` |
| Deep/REM cycle | `12h` | `consolidation/scheduler.py` |
| Wiki sync interval | `24h` | `WIKI_SYNC_INTERVAL_H` |
| Max wiki sync files | `10` | `wiki_sync.py` |
| Max concurrent agents | `1` | `config.py` |
| Embedding dim | `768` | ChromaDB requirement |

---

## What Was Done This Session (full history)

### Bug Fixes
- `_dedup_episodic` early returns all changed to return `(0, 0, [])` (was returning 2-tuple, caller expected 3)
- `_pipeline` AttributeError in light loop → added `self._pipeline: Any | None = None` in `ConsolidationScheduler.__init__`
- `GlobalWorkspace.get_top_items()` doesn't exist → fixed to `workspace.snapshot.items[:3]`
- `_NOTES_DIR` pointed wrong (5 parents) → `_notes_dir()` uses `_repo_root() / "notes"` (4 parents)
- `REPO_ROOT` had 5 parents → fixed to 4
- `stdio_server(server)` is async ctx manager not coroutine → `async with stdio_server() as (r,w): await server.run(...)`
- `settings.telegram_enabled` never updated on provider change → `_set_env_key()` patches `os.environ`
- Re-promotion of same memory every cycle → direct DB query `WHERE content = ?` instead of set comparison
- `opencode-mcp` JSON parse errors from npm output → `2>/dev/null` in bash -c wrapper
- Cerebras `token_quota_exceeded` → wiki sync stops immediately, `max_files=10`
- Self-modification notes path wrong → `_notes_dir()` uses `_repo_root()`
- Proactive engine said but didn't act → rewritten to use `stream_chat_with_tools()`
- Goal "Create self_growth.md" infinite loop → `_auto_achieve_file_goals()` + `file_action` in goal pursue
- Return statement before weight mutations in `_run_deep` → wiki consolidation moved AFTER weight mutations

### Features Added
- **9 LLM providers**: OpenCode, OpenRouter, Cerebras, Unsloth Studio, LM Studio, Ollama, OpenAI, Groq, Anthropic
- **echo-workspace MCP server** (`scripts/mcp_echo_workspace.py`): full repo file access with Python validation + rollback
- **bash MCP server** (`scripts/mcp_bash_server.py`): sandboxed shell for ECHO
- **Self-code-modification**: ECHO edits src/echo/*.py, commits, pushes autonomously
- **REM wiki consolidation**: `wiki.consolidate_connections()` finds degree-0 nodes, appends `## Related` with `[[wikilinks]]`
- **Dynamic agent routing**: keyword heuristic, simple-query fast path, ≥40 words → full 6-agent
- **Proactive engine real agency**: uses `stream_chat_with_tools()`, semantic+wiki snapshot, ACTS not declares
- **Telegram HTML formatting**: `_md_to_html()`, fallback to plain on 400, `deleteWebhook` on startup
- **Cerebras rate limiter**: global 1.1s/call token bucket, `max_concurrent_agent_calls=1`
- **Heartbeat event log**: light/deep/REM/proactive/curiosity events logged to DB, shown in frontend panel
- **Sentiment UI**: mood emoji + color-coded drive fill bars in System State sidebar
- **All UI labels English**: AnalyticsPanel, IdentityGraph, WikiGraph, tab GRAPH→MEMORY
- **Embedding config UI**: 3-tier chain (Ollama→LM Studio→HuggingFace) in Setup
- **GitHub wiki auto-sync**: `WikiSyncEngine` fetches .md files from GitHub repo every 24h
- **OpenCode provider**: big-pickle default model
- **Cron skip suppression**: skipped tasks don't send Telegram notification
- **`ECHO_LANGUAGE`**: all generated text respects language setting

### Security Constraints (NEVER change)
- `self_modification/engine.py` — PROTECTED (cannot be modified by ECHO itself)
- `.env` — PROTECTED
- `data/sqlite/`, `data/chroma/` — PROTECTED
- Git blocked: `push --force`, `reset --hard`, `clean -f`, `branch -D`

---

## Known Issues / Potential Next Work

1. **Proactive engine cooldown 90min** — may be too long; could make configurable
2. **wiki consolidation LLM call** — if Cerebras quota exceeded during REM, consolidation silently skips (fine, but not logged distinctly)
3. **No test coverage** for new MCP servers, proactive engine, wiki consolidation
4. **Frontend HeartbeatPanel** — verify events show after light cycle fires
5. **Self-modification** — ECHO hasn't yet autonomously committed real improvements; needs observation

---

## How to Resume a Session

1. Read this file first
2. Read `MEMORY.md` for persistent user preferences
3. Key files to check if debugging: `src/echo/consolidation/scheduler.py`, `src/echo/initiative/proactive_engine.py`, `scripts/mcp_echo_workspace.py`
4. Run `git log --oneline -10` to see latest changes
5. Check logs: `uvicorn echo.api.server:app --host 0.0.0.0 --port 8000`

---

## User Preferences (from memory)

- **Caveman mode** active (terse responses, fragments OK)
- **Language**: Italian for ECHO responses, English for UI
- **Commit style**: descriptive prefix (feat/fix/docs/chore)
- **No Docker** on this machine
- **Server**: `0.0.0.0:8000`
- **Telegram** enabled for outbound notifications + bidirectional chat
