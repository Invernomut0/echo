# ECHO Changelog

All notable changes to this project are documented here.
Format: [version] — date, grouped by category.

---

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
