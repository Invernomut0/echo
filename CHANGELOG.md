# ECHO Changelog

All notable changes to this project are documented here.
Format: [version] — date, grouped by category.

---

## [0.5.3] — 2026-07-08

### GitHub Wiki Auto-Sync
- `WikiSyncEngine` (`memory/wiki_sync.py`): fetches all `.md` files from a configured GitHub repo and ingests them into ECHO's wiki
  - Change detection via commit SHA — only processes new/modified files
  - Content SHA per-file tracking avoids re-ingesting unchanged files
  - Prioritizes changed files; processes up to `WIKI_SYNC_MAX_FILES` (default 50) per cycle
  - Runs in light heartbeat loop respecting `WIKI_SYNC_INTERVAL_H` (default 24h) cooldown
  - `📚 WIKI` badge (purple) in HeartbeatPanel with synced/changed/total_md stats
- Config: `WIKI_SYNC_REPO` (default `https://github.com/Invernomut0/echo`), `WIKI_SYNC_ENABLED`, `WIKI_SYNC_INTERVAL_H`, `WIKI_SYNC_MAX_FILES`
- Optional `GITHUB_TOKEN` raises GitHub API rate limit from 60 to 5000 req/hour
- Fields exposed in Setup UI and `/api/setup/config`

## [0.5.2] — 2026-07-08

### Autonomous Self-Modification
- `SelfModificationEngine`: ECHO can now improve its own codebase autonomously during heartbeat idle cycles
  - LLM evaluates internal state (knowledge gaps, goals, patterns, curiosity topics) to identify improvements
  - Applies change, validates with `ast.parse()`, rolls back on failure
  - `git add + commit + push` fully automated
  - Creates `notes/YYYY-MM-DD_slug.md` with diff + rationale
  - Notifies via Telegram: "🔧 Ho appena migliorato il mio codice!"
  - Security constraints: only `src/echo/`, never `core/db.py`/`config.py`/`self_modification/` itself, 6h cooldown, skips during active user session
- `🔧 SELFMOD` badge (orange) in HeartbeatPanel

### UI — Emotional State Visualization
- Right sidebar "System State" now shows:
  - Large central emoji representing ECHO's mood (😔→😕→😐→🙂→😊→🤩)
  - Mood label in language ("Abbattuto" / "Neutro" / "Soddisfatto" / "Entusiasta" etc.)
  - Drive mini-bars: 🔗 Coerenza, 🔍 Curiosità, 🏔️ Stabilità, 💡 Competenza with 8-block fill bars
  - Color-coded by intensity (amber→green→cyan)
  - Valence numeric value below emoji

### Heartbeat Fixes
- `_pipeline` attribute missing from `ConsolidationScheduler.__init__` → `AttributeError` crashed entire light loop; `LIGHT`/`PROACTIVE`/`INITIATIVE` events never logged. Fixed by initializing `self._pipeline = None` + `attach_pipeline()` method called from `pipeline.startup()`
- `_dedup_episodic()` early returns `(0, 0)` instead of `(0, 0, [])` → `ValueError: not enough values to unpack` in every light cycle. Fixed.
- `initiative/engine.py`: missing `from echo.core.config import settings` import
- `proactive_engine.py`: removed invalid `from echo.core.user_activity import _last_active`
- `db.py`: `initiative_log` table never created (model not imported before `create_all()`). Fixed.
- `detect_and_clean_conflicts` cap: 20 → 5 pairs per cycle (20 concurrent LLM calls → 429 cascade)

### Telegram
- Messages now sent as HTML with `parse_mode=HTML` — proper **bold**, *italic*, `code`, table → bullet list conversion
- `_md_to_html()` converter handles markdown tables, headings, code blocks
- Cron task results broadcast to Telegram after each successful run
- Heartbeat intervals now configurable: `CONSOLIDATION_LIGHT_INTERVAL_S`, `CONSOLIDATION_DEEP_INTERVAL_S`

## [0.5.1] — 2026-07-08

### Telegram Bidirectional Messaging
- **Web chat → Telegram mirror**: every web-UI response is now forwarded to all configured Telegram chat IDs (fire-and-forget, async)
- **Proactive heartbeat messages**: initiative engine (insights, questions, reflections generated during idle heartbeat) now delivered via `telegram_send.broadcast()` — uses running bridge connection instead of creating a new HTTP client per message
- `telegram_send.py`: new centralised broadcast module used by pipeline, initiative engine, and future senders; prefers open bridge connection, falls back to one-shot httpx
- Bridge registered with `telegram_send.set_bridge()` at startup and on settings reload

### Telegram Fixes
- `--reload-dir src/echo`: restricts watchfiles to Python sources only — SQLite writes (every interaction) no longer trigger server restarts that kill the bridge mid-bootstrap
- `_bootstrap()` in bridge: runs `getMe` (token validation) + `deleteWebhook` (removes conflicts with long-polling) before starting update loop
- Clearer startup logs: `"Telegram bridge started"`, `"Telegram integration disabled"`, `"bot verified: @username"`
- `GET /api/setup/telegram/status` endpoint: real-time bridge state

### Cron Fixes
- `llm_task` no longer crashes with `"requires a 'prompt'"` when task was created with description only — scheduler injects `_task_description` / `_task_name` as config fallbacks
- `Object of type MemoryEntry is not JSON serializable` fixed: `episodic.store()` returns `MemoryEntry`; executor now extracts `.id` before storing in result dict
- Scheduler: `_safe()` serializer wraps `json.dumps(result)` to prevent any future non-serializable objects from crashing run records

### Cerebras / Rate Limiting
- Global token-bucket rate limiter (`_RateLimiter`) in `llm_client.py` — all `chat()` and `stream_chat()` calls serialized at `llm_rate_limit_min_interval_s` (default 1.1s for Cerebras 60 RPM free tier)
- `max_concurrent_agent_calls: 2 → 1` default for Cerebras compatibility
- Agent timeout `_AGENT_TIMEOUT_S: 15 → 60s` — survives 57s Cerebras retry delays
- Set `LLM_RATE_LIMIT_MIN_INTERVAL_S=0` in `.env` to disable for paid providers

### Provider
- **Cerebras** added: `cloud.cerebras.ai`, ~1800 tok/s, free tier, `llama-3.3-70b` default

## [0.5.0] — 2026-07-07

### New Providers
- **OpenCode** (`opencode.ai/zen/v1`) — OpenAI-compatible zen gateway, `big-pickle` as default model
- **OpenRouter** (`openrouter.ai/api/v1`) — unified gateway to 300+ models, 8 preset model suggestions in UI
- Both providers visible in Setup UI as selectable tiles with API key + model + base URL config
- Provider + model name shown in chat header badge (`provider/model`)

### Provider Hot-Reload
- `_set_env_key()` now updates `os.environ` immediately (not just `.env`) so provider switches via UI take effect without restart — critical for Docker and shell-exported env vars
- `LLMClient.on_settings_reload()` resets `_model_confirmed_loaded`, rebuilds `self._client`, re-reads model/embedding fields on every settings save
- `_reload_settings()` logs `"Provider changed: X → Y"` at INFO level for observability
- Frontend `handleSave` always includes `llm_provider: activeProvider` so every section save also confirms the active provider

### Performance — LLM Call Reduction
- **Dynamic agent routing**: keyword-based heuristic selects 2-3 relevant agents per query (no extra LLM call); only queries ≥40 words get full 6-agent routing; status shows selected roles
- **Simple query fast path**: greetings/acks skip all agents → 80% fewer LLM calls for conversational turns
- **Drive scoring throttle**: LLM drive scoring every N interactions (default 3); in-between turns reuse previous values with 3% decay toward neutral
- **Wiki + interest inference throttle**: skip both for messages < 60 chars (no facts worth storing in conversational exchanges)
- **ZPD cache**: `zpd_topics()` caches results for 600s; skipped-due-to-active results cached 60s to prevent API poll spam

### Double Synthesis Elimination
- Replaced `_openai_tool_rounds() + stream_chat()` double-call pattern with `_stream_openai_with_tool_rounds()` — single streaming pass that detects tool calls in-flight
- When no tools are used (common case), response is streamed directly without a second LLM call — saves ~40s and ~7k tokens per interaction on local thinking models

### Thinking Model Support
- All `max_tokens` budgets raised 3-4× across the board (agent: 256→1024, synthesis: 1024→3072, drive_scoring: 400→1200, topic_extraction: 400→1200, etc.) — thinking models (gemma-4, QwQ, DeepSeek-R1) consume ~80-90% of budget on internal reasoning

### Live Progress Steps
- Stream now emits granular status messages: `"Recovering memories…"`, `"Recalled N episodic, M semantic memories…"`, `"Searching knowledge base (P pages)…"`, `"Consulting Analyst, Archivist…"`, `"Synthesizing (voices)…"`, `"Using tool: brave web search…"`

### Cognitive Architecture Improvements
- **Agent weight floor**: `_MIN_WEIGHT: 0.1 → 0.3` in `plasticity/adapter.py` — no agent goes dormant, cognitive diversity guaranteed structurally
- **Global Workspace age penalty + recency boost**: items persisting >2 turns lose 0.08/turn; items added in current turn gain +0.10; prevents stale high-salience items from blocking fresh context
- **Drive conflict evidence accumulation**: `DriveState` gains `win_outcomes` deque + `evidence_weight` (EWMA); conflict resolution blends 60% momentum + 40% historical evidence when ≥5 outcomes per drive pair
- **Meta-learning stagnation detection**: if prediction error variance < 0.0015 AND mean novelty < 0.35 over last 20 observations → alpha boosted by +0.08 to force plasticity

### Curiosity Engine Fixes
- `_recently_searched`: replaced cycle-counter-based clear (stale for 30+ min) with TTL dict (10 min expiry per topic)
- Topic extraction: robust `_parse_topic_array()` strips markdown fences, finds array bounds, logs failures explicitly
- Fallback topic: skips conversational prefixes (`user:`, `echo:`, `ciao`) and requires ≥3 meaningful words
- `force=True` parameter: manual trigger bypasses idle, activity, and min-interval guards
- `_cycle_counter` module-level variable restored (was accidentally removed)
- Brave MCP plain-text parser: `_parse_brave_plaintext()` extracts real titles from markdown-formatted Brave responses

### Curiosity Spam Prevention
- `_ACTIVE_WINDOW_SECONDS: 120 → 300` (5 minutes post-interaction silence)
- ZPD `is_active()` skip now caches empty result with 60s TTL to prevent polling re-entry race conditions

### Safety & Robustness
- **Safety metadata filter**: detects OpenRouter moderation responses (`"User Safety: safe/unsafe Response Safety: safe/unsafe Safety Categories:…"`) and discards them with a user-friendly fallback message — prevents metadata from being stored as episodic memory
- **Tool use fallback**: `_stream_openai_with_tool_rounds` catches 404 "model doesn't support tool use" and retries without tools — prevents crash on OpenRouter with non-tool-supporting models
- **OpenAI stream cleanup**: `try/finally` + `stream.close()` on OpenAI streaming path prevents connection leaks on early break/exception
- **Split-brain delete fix** in semantic memory: ChromaDB deleted before SQLite commit — SQLite row preserved if vector delete fails
- `stop()` made async in `DecayScheduler` and `ConsolidationScheduler` — task cancellation is properly awaited
- `zip(strict=True)` in semantic memory dedup — surfaces ID/embedding count mismatch instead of silently dropping

### Reflection Engine
- Drive adjustments clamped to `[-0.1, 0.1]` — LLM cannot inject out-of-range drive spikes
- Robust JSON extraction: strips markdown fences, multi-strategy object search
- New belief dedup: skips beliefs with >80% word overlap against existing ones

### UI Improvements
- **Model/provider badge** in chat header (`provider/model` monospace, next to interaction count)
- **OpenCode + OpenRouter tiles** in Setup panel with full config sections
- All provider sections now always include `llm_provider` on save

### Bug Fixes
- `_cycle_counter` restored as module-level variable in curiosity engine (NameError on every cycle)
- `_post_interact` task exceptions now logged via `add_done_callback` (were silently swallowed)
- `_last_memory_sources` initialized in `__init__` to prevent `AttributeError` before first interaction
- `_recently_searched` restored as module-level dict (was accidentally merged into set during refactor)

---

## [0.4.11] — 2026-05-09
- Centralized achieved-goal consolidation in `GoalStore.update_status`
- Added semantic "Goal Resolution Report" persistence
- Added Telegram outbound notifier for goal completion summaries
- Added config flag `TELEGRAM_GOAL_NOTIFICATIONS_ENABLED`

## [0.4.0] — 2026-04-30
- **Co-evolutionary cognitive partner**: `UserInterestProfile`, `StimulusQueue`, ZPD cycles, proactive stimulus injection, implicit feedback loop
- Frontend: CuriosityPanel extended with Interest Profile, ZPD Zone, Pending Findings sections

## [0.3.0]
- `echo.md` — ECHO's self-maintained personality file
- EchoMdPanel in frontend; manual review endpoint
- LLM migrated from LM Studio → GitHub Copilot

## [0.2.0]
- Curiosity Engine, LLM Wiki, Personalisation priors, Pipeline trace

## [0.1.0]
- Initial architecture: 6 agents, Global Workspace, memory layers, Drive System, Identity Belief Graph, Reflection Engine, Consolidation Scheduler
