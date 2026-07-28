# ECHO Changelog

All notable changes to this project are documented here.
Format: [version] — date, grouped by category.

---

## [0.5.14] — 2026-07-28

### Fixed — ZPD topic generation fired an LLM request every few seconds

`GET /api/curiosity/profile` called `zpd_topics()`, and the curiosity panel polls
that endpoint every 8 s. The TTL cache only ever recorded *successful*
generations, so as soon as the backend started returning empty completions every
single poll launched a fresh `/v1/chat/completions` request — with nothing to
cache, there was nothing to stop it.

Three changes:

- **Every outcome is cached**, not just successes: empty completions, malformed
  arrays, LLM exceptions and "no interests recorded yet" all back off for
  `_ZPD_FAILURE_TTL` (5 min) instead of retrying on the next poll. Successes keep
  the 10 min TTL; the user-active skip keeps its short 60 s TTL so ZPD resumes
  promptly once the user goes idle.
- **Generation is serialised behind a lock.** On a local model prompt processing
  routinely outlasts the 8 s poll interval, so concurrent callers each started
  their own request rather than sharing one.
- **The profile endpoint no longer generates.** It reads the cache via the new
  `zpd_topics_cached()`; displaying the panel must not cost inference. The
  curiosity engine refreshes the cache on its own cycle.

---

## [0.5.13] — 2026-07-28

### Fixed — every greeting crashed with `KeyError: 'beliefs'`

`_SYNTHESIS_TEMPLATE` was formatted inline at three separate call sites.
`str.format` only reports a missing placeholder at runtime, so when `{beliefs}`
was added to the template the greeting fast path in `Orchestrator.stream` was
silently left behind: "ciao", "grazie" and every other short message routed to
the no-agent path raised `KeyError: 'beliefs'` and the UI rendered
`[Error: 'beliefs']`.

All three call sites now go through a single `_render_synthesis()` helper, so a
future placeholder cannot desynchronise them. A regression test asserts the
template is formatted in exactly one place and drives the fast path end to end.

### Fixed — corrupt `data/mcp.json` disabled every tool

A previous self-modification wrote `"feedback_enabled": false` into the middle
of an `env` block, leaving the file unparseable. ECHO validated `.py` edits with
`ast.parse` but wrote every other file unchecked, so the broken config committed
cleanly — and with the MCP config unreadable **no server loaded at all**, which
is why ECHO genuinely had no file access or web search while still believing it
did.

- Repaired `data/mcp.json` (7 servers parse again).
- Added `git_ops.validate_structured()`: `.json` and `.yaml`/`.yml` edits are
  parsed after writing and rolled back on failure, alongside the existing Python
  check. Other extensions pass through untouched.

### Added — `echo__list_beliefs`

Asked "give me the list of all the beliefs you have", ECHO could only answer
from the bounded selection in its prompt — at most 20 of up to 300 beliefs — so
any list it gave was a guess. The new internal tool reads the identity graph
directly, with optional `limit`, `min_confidence` and `query` filters. It lives
in the `echo__*` namespace and is therefore never dropped by the tool-payload
cap. The synthesis system prompt now instructs the model to call it rather than
answer from the partial block.

---

## [0.5.12] — 2026-07-28

### Identity Beliefs Reach the Prompt Again

ECHO was denying it could read or write files and forgetting the user's name.
Both are beliefs it holds — they simply never reached the model.

#### Belief selection was a pure confidence sort

`_fmt_beliefs()` filtered at confidence 0.3, sorted descending and took the top
15. But beliefs enter the graph at *fixed* confidences: the bootstrap
self-description at 0.6, reflection output at 0.5, and facts auto-promoted from
episodic memory — where the user's name lands — at `min(0.6, salience)`.
Reflection then keeps nudging abstract self-narrative upward. Once more than
fifteen beliefs sit above 0.6, every concrete fact is ranked below them and is
never rendered. Verified on a saturated graph: the old selection returned
fifteen variations of "I am a reflective cognitive system" and neither "The
user's name is Lorenzo" nor "I can read and write files".

Selection now runs in three tiers — pinned (beliefs about the user, and beliefs
describing ECHO's own capabilities), then beliefs relevant to the current
message, then a highest-confidence fill. Pinned beliefs take the first 8 of 20
slots and are admitted from confidence 0.15, since being about the user or about
ECHO's own capabilities is itself evidence the belief matters. They are rendered
first because LLMs weight earlier context more heavily.

#### Workspace tools could be filtered out of a request

`LLM_MAX_TOOLS` (added in 0.5.11) could drop `echo-workspace__*` — ECHO's own
file surface — whenever the message did not mention files, making "I cannot
write files" briefly true. `echo-workspace` joins the always-kept set and the
default cap rises 24 → 32 to keep room for relevance-ranked tools. Payload
reduction on the captured 112-tool setup is now 74.5 %.

#### The system prompt described the wrong tools

The tool addendum described the first five external tools *in connection order*
— whichever server happened to connect first — then dumped the remaining 100+ as
a comma-separated blob of bare names. That blob was pure noise crowding out the
entries that mattered. It now describes up to 12 tools, prioritising the ones
ECHO actually relies on, states plainly that ECHO does have file access, and
reports the remainder as a count rather than naming them.

### Added

- `tests/test_belief_selection.py` — 16 tests, including a guard that asserts
  the previous implementation loses the very beliefs at issue.

### Changed

- `LLM_MAX_TOOLS` default 24 → 32.

---

## [0.5.11] — 2026-07-28

### Request Payload — Prompt Size & Timeouts

A single chat turn was shipping a **19,765-token prompt** to the local backend.
LM Studio logs show prompt processing crawling from 270 to 160 tok/s, stalling at
41 % after two minutes, and the request dying with `httpx.ReadTimeout` before a
single token was generated. Three compounding causes.

#### Tool payload no longer unbounded

`list_tools_openai()` returned **every** connected tool — 112 schemas across eight
MCP servers, 80 of them from `opencode-mcp` alone (TUI controls, OAuth flows,
provider and session management), none of which help answer a user's question.
The synthesis system prompt already capped tool *descriptions* at five, but the
`tools=` array sent to the API was never filtered, so the cap saved nothing.

New `MCPClientManager.select_tools_openai()` ranks tools against the current
message and caps the result at `LLM_MAX_TOOLS` (default 24). ECHO's own `echo__*`
tools and the small, broadly useful servers (`brave_search`, `fetch`, `datetime`)
are always kept, so no capability is lost. Remaining slots go to the tools whose
name and description overlap the message, smaller schemas winning ties.
Measured on the captured 112-tool setup: **80.9 % smaller tool payload**.

#### Read timeout now covers prompt processing

The shared HTTP client used a flat 120 s timeout. A backend sends nothing while it
ingests the prompt, so that budget was exhausted by prompt processing alone — the
observed failure mode. Replaced with `httpx.Timeout(connect=10, read=…, write=60,
pool=10)` where read is `LLM_READ_TIMEOUT_S` (default 300). An unreachable backend
still fails in 10 s.

#### Failed turns no longer replayed

`_trim_history()` rewrote error responses to `[previous response failed]` and kept
them. Each retry therefore consumed a slot in the six-turn window *and* showed the
model a transcript in which its own last three answers were failures — a pattern it
imitates. Failed and empty assistant turns are now dropped outright, and a question
the user retried verbatim is collapsed to one turn. The trim window is applied
after cleaning, so errors no longer displace real context.

### Added

- `LLM_MAX_TOOLS` (default 24, `0` disables) — ceiling on tool schemas per request.
- `LLM_READ_TIMEOUT_S` (default 300) — read timeout for LLM HTTP calls.
- `tests/test_prompt_payload.py` — 17 tests covering tool selection, history
  hygiene and the timeout floor, built on a reconstruction of the captured payload.

---

## [0.5.10] — 2026-07-28

### Cognitive Subsystem Audit — Correctness & Throughput

A follow-up audit of the memory, curiosity, reflection and self-model modules.
Eight defects, ordered by what they cost ECHO.

#### Correctness

- **Curiosity deduplication rewritten.** The check compared only words 2–12 of a
  finding. Every finding begins with `Title:` and ends that window with
  `Summary:`, so two matches were free and three shared title words were enough
  to discard a genuinely new result — while a page re-found under another topic
  slipped through. It now compares the whole finding (field labels and the
  `Source:` line excluded) by Jaccard overlap, treats an identical source URL as
  decisive, and inspects 12 neighbours instead of 3. Measured on realistic
  findings, the old heuristic was wrong on 2 of 4 cases, the new one on none.
- **Contradicted beliefs are now retired.** `resolve_contradictions()` attenuated
  a losing belief and merely logged it below 0.15 confidence. `prune()` spares
  connected beliefs, so such a belief was unreachable by every cleanup path and
  its `CONTRADICTS` edge depressed `coherence_score()` permanently. A belief
  driven below the floor is deleted when only contradictions attach to it;
  one that still supports another belief is kept as structure.
- **Reflection no longer stores paraphrases.** Duplicate detection divided the
  overlap by the *new* belief's length at a >0.8 threshold, so a reworded belief
  scored ~0.6 and was added again. Overlap is now measured against the shorter
  of the two beliefs at 0.7.

#### Throughput

- **Curiosity topics are searched concurrently.** Topic searches are independent
  and network-bound; running them in sequence multiplied cycle latency by the
  topic count. Storing stays sequential so novelty checks remain correct.
- **Semantic edges are cached.** `to_dict()` recomputed an O(n²) Jaccard matrix
  (~45k comparisons at the 300-belief cap) on every frontend graph poll. It now
  reruns only when a belief is added, removed, reworded or re-scored.
- **Metacognitive model refreshed on the light heartbeat.** Feeding learning data
  into the self-model costs no LLM call, yet ran only in the 12 h REM cycle, so
  ECHO spent nearly the whole day reasoning from stale competence and engagement
  figures. The LLM-based `deep_review()` now also runs at most every 4 h, gated
  by the background token budget.

#### I/O

- **`log.md` is appended, not rewritten.** Every wiki operation read the entire
  log back just to write it out again — cost grew without bound. `get_log()`
  likewise now reads only the tail of the file.
- **Blocking file I/O moved off the event loop.** `GET /api/consolidation/notes`
  opened every file in `notes/` (hundreds) inline; that scan and the `echo.md` /
  `self_growth.md` reads now run in a worker thread.
- **Pending queues use `deque(maxlen=…)`.** Overflow was handled with `pop(0)`,
  which is O(n) per append once full.

### Tests

18 new tests in `tests/test_cognitive_fixes.py`. The deduplication and
contradiction tests assert against the *previous* implementation as well, so they
fail if they stop discriminating between old and new behaviour.

---

## [0.5.9] — 2026-07-13

### Security

- **Fixed arbitrary code execution in `validate_python()`**
  ([`self_modification/git_ops.py`](src/echo/self_modification/git_ops.py)). The
  file path was interpolated into a source string run via `python3 -c`, so a
  path containing a quote escaped the literal and executed. Because ECHO derives
  these paths from LLM output while rewriting its own source, the model could
  reach it. The path is now passed through `argv`, and the interpreter is
  `sys.executable` rather than whatever `python3` resolves to. Regression test
  reproduces the original exploit.
- **Widened `.gitignore` to `.env.*`** so ad-hoc copies (`.env.backup`, `.env.bak`)
  can no longer be committed; `.env.example` stays tracked via a negation.

### Fixed

- **Every `ECHO_*` variable in `.env` was silently ignored.** `Settings` declared
  no `env_prefix`, so ~34 tuned values were dead and the process ran on defaults —
  including `LLM_MAX_TOKENS_AGENT` at 256 instead of 1024 and
  `LLM_MAX_TOKENS_SYNTHESIS` at 1024 instead of 3072, which truncated thinking
  models mid-reasoning. An `AliasGenerator` now accepts **both** the bare and the
  `ECHO_`-prefixed spelling (bare wins if both are set), so no existing
  configuration breaks.

### Added

- **Startup diagnostic for dead configuration.** `find_unmapped_env_vars()` reports
  any `.env` variable matching no setting, logged as a warning by the API lifespan.
  `extra="ignore"` is what let the bug above go unnoticed; this makes it loud.

### Notes

- OS environment variables take precedence over `.env`. If a value refuses to
  change, check for stale exports with `env | grep ECHO_`.

---

## [0.5.8] — 2026-07-13

### Cognitive Load Optimisation — Latency & Background Throughput

ECHO's autonomous loops were consuming most of the inference backend's capacity,
leaving little for the user. This release reworks how foreground and background
work share the model.

#### Critical path (perceived latency)
- `max_concurrent_agent_calls` **1 → 3**: specialist agents now deliberate in
  parallel instead of one at a time. Serial execution multiplied the user's wait
  by the number of active agents; with 3 agents this is the single largest
  latency reduction. Routing weights and the plasticity architecture are
  unchanged — agents stay separate, they simply run concurrently.
- `_RateLimiter` is now **bypassed for local providers** (`lm_studio`, `ollama`).
  It held a lock while sleeping, so the 1.1 s inter-call spacing meant for the
  Cerebras free tier was serialising every local call and cancelling out the
  parallelism above.
- `_post_interact()` now awaits `wait_if_generating()` before spending any
  tokens. It runs fire-and-forget after the response streams, so it could still
  be working when the user sent a follow-up.

#### Background token load
- **Batched wiki updates**: `WikiStore.queue_interaction()` /
  `drain_pending()` replace the per-interaction `update_from_interaction()` call.
  Fact extraction was a full LLM call after *every* message — the largest single
  consumer of background capacity. Exchanges are now buffered (bounded at 20) and
  folded into the wiki in one call by the consolidation heartbeat, which also
  improves fact quality since the model sees more context at once.
- **Batched interest inference**: same treatment for
  `UserInterestProfile.queue_interaction()` / `drain_pending()`.
- **Global background token budget** (`echo.core.background_budget`): a sliding
  hourly ceiling shared by every autonomous subsystem, with priority-based
  shedding — `PROACTIVE` stops below 50 % remaining, `CURIOSITY` below 30 %,
  `CONSOLIDATION` below 10 %, and `REFLECTION` is never starved. Spend is charged
  automatically in `llm.chat()` whenever no user-facing generation is in flight.
  Configurable via `ECHO_BACKGROUND_TOKEN_BUDGET_PER_HOUR` (0 disables).
- `consolidation_light_interval_s` **300 → 900**: the light heartbeat fired 12×
  per hour, each time triggering curiosity, initiative and proactive checks.

#### Self-model growth
- Workspace→belief promotion threshold **0.6 → 0.8**, and at most **one** belief
  per interaction instead of three.
- New `_is_similar_belief()` Jaccard check rejects candidates that restate an
  existing belief, so the same recurring thought is no longer promoted every turn.
- New `IdentityGraph.prune()`, run in the deep/REM cycle: deletes isolated
  beliefs below 0.15 confidence and enforces a 300-belief cap. Connected beliefs
  are never pruned regardless of confidence. `coherence_score()` and `to_dict()`
  are O(n²), so an unbounded graph degraded the whole self-model.

#### Goal engine correctness
- **Fixed iteration deadlock**: pursuit stopped at `MAX_GOAL_ITERATIONS - 1` (9)
  but force-consolidation only fired at `MAX_GOAL_ITERATIONS` (10), so goals
  stalled at 9 actions permanently. Both thresholds are now aligned.
- **Unified consolidation**: the three duplicated consolidate-and-store blocks
  are replaced by `_consolidate_goal_knowledge(goal, reason=…)`. Since
  `consolidate_goal()` returns `None` for a non-active goal, the operation is
  idempotent and can no longer write duplicate semantic memories.
- **Abandoned goals are consolidated too** (at 0.7× salience) instead of having
  their research silently discarded.
- **Goal reflection now sees action history**: the prompt lists the last 3
  completed actions and the iteration count per goal, so the LLM stops
  re-proposing searches it has already run.
- Pursuits per cycle **1 → 2**: at 1, five active goals each advanced once every
  ~5 hours and never converged.

#### Plasticity
- `_LR` **0.05 → 0.10**: moving a routing weight by 0.5 took ~20 reflection
  cycles (60 interactions), which made adaptation effectively unobservable.

#### Tests
- `tests/test_background_optimizations.py`: 24 tests covering budget priority
  shedding, queue bounds and eviction order, belief deduplication, and pruning
  selection rules.

---

## [0.5.7] — 2026-07-13

### REM Wiki Consolidation
- `WikiStore.consolidate_connections(max_isolated=5)`: runs in every REM (deep) cycle — finds degree-0 nodes (pages with no `[[wikilinks]]`), asks LLM which other pages are genuinely related, appends `## Related` section with `[[wikilinks]]` to grow the knowledge graph
- Logs a `📚 WIKI` heartbeat event with count of connections created
- Isolated entities in the Memory graph progressively become part of the network across REM cycles

### Session Continuity
- `SESSION_DUMP.md`: full architecture map, critical constants, session history, known issues — use to resume work in a new LLM session without re-reading history

---

## [0.5.6] — 2026-07-12

### Proactive Engine — Real Agency
- Proactive engine now uses `stream_chat_with_tools()` instead of `llm.chat()` — ECHO can **actually act** during idle heartbeats (write files, commit, search wiki/memory) instead of only describing intentions
- Final message reports what ECHO **actually did**, not what it plans to; system prompt enforces "if you say you'll update a file, you MUST call the tool this cycle"
- Enriched state snapshot: adds **semantic memory** (top-salience facts) and **full wiki page index** alongside episodic memory, goals, curiosity, knowledge gaps, patterns
- Tool-use actions logged as `ProactiveEcho action: …`

### Self-Code-Modification via Proactive Engine
- Proactive engine can now modify **its own source code** (`src/echo/*.py`, frontend, scripts) — fix bugs seen in logs, tune constants, improve prompts, add features — then commit + push autonomously
- **Safety net** in `echo-workspace` MCP server: every `.py` write/edit/append is auto-validated with `ast.parse()`; syntax errors trigger automatic rollback (or file deletion for new files) with a `REJECTED` message. The running system can never be left with broken code
- `self_modification/engine.py` remains the only protected code file

### echo-workspace / bash MCP Servers
- `scripts/mcp_echo_workspace.py`: 7 tools (read/write/edit/append/list/git/validate) for full repo access
- `scripts/mcp_bash_server.py`: sandboxed `bash_exec` with timeout + destructive-command blocklist
- `notes/self_growth.md`: growth journal ECHO maintains autonomously

### Goal & Cron Fixes
- `_auto_achieve_file_goals()`: file-creation goals auto-marked achieved on startup when the target file exists — stops the infinite "Create self_growth.md" loop
- Goal pursuit supports file actions (`file_path` + `file_content`) via echo-workspace instead of web search
- `self_modification` cron task type; auto-migration from `llm_task`
- Skipped cron tasks no longer send Telegram notifications

## [0.5.5] — 2026-07-12

### ECHO Self-Modification
- `SelfModificationEngine` expanded to full repo — can now modify any file in `/root/echo` (src/, frontend/, scripts/, docs/, notes/, start.sh, data/mcp.json, etc.)
- New `self_modification` cron task type — replaces `llm_task` for the Self-Modification Loop; calls `SelfModificationEngine` directly (git commit/push, notes/, Telegram)
- `_migrate_task_types()`: auto-converts existing "Self-Modification Loop" `llm_task` entries to `self_modification` on startup
- Cron tasks with `status=skipped` no longer send Telegram notifications

### echo-workspace MCP Server
- New `scripts/mcp_echo_workspace.py`: 7 tools for full ECHO repo access
  - `echo_read_file`, `echo_write_file`, `echo_edit_file`, `echo_append_file`, `echo_list_files`, `echo_git`, `echo_validate_python`
  - ECHO can now directly edit `notes/self_growth.md`, modify prompts, update config, commit — no human copy-paste needed
- Added to `data/mcp.json` (first entry); `filesystem_user` mode upgraded to `readwrite`

### UI — All Labels in English
- IdentityGraph: Coherence, beliefs, semantic, episodic, relations, Supports, Contradicts, Refines, etc.
- AnalyticsPanel: Cognitive Drives, Emotional State, Self-Awareness, Plasticity — Drive Weights, Agent Routing, Valence, Motivation, Compression
- App.tsx: mood labels (Distressed/Uneasy/Neutral/Calm/Content/Enthusiastic), drive labels
- WikiGraphPanel: Entities, Concepts, Sources, Syntheses
- Tab renamed: **GRAPH → MEMORY**

### Telegram Language Fix
- `llm_task` cron executor injects "Always respond in Italian" when `ECHO_LANGUAGE=it`
- Fixes cron task results (Daily AI News, Self-Modification) being sent in English

## [0.5.4] — 2026-07-09

### Language Setting
- `ECHO_LANGUAGE` (default `it`) — controls language of all ECHO-generated text: synthesis responses, proactive messages, self-modification notes, cron outputs
- Injected into orchestrator synthesis system prompt, proactive engine, and self-modification engine

### Self-Modification Fixes
- System prompt rewritten: explicit `OUTPUT ONLY JSON, NO NARRATIVE` instruction — LLM was generating markdown plans instead of actionable JSON
- Temperature `0.4 → 0.15` — deterministic JSON output
- `_list_source_files()`: passes full listing of `src/echo/*.py` as `AVAILABLE FILES` context so LLM knows the real codebase (was hallucinating minimal echo service)
- Language directive injected into description/rationale fields

### Bug Fixes
- `opencode-mcp ServeError`: subprocess exited with code 1 on startup because `OPENCODE_SERVER_PASSWORD` was not set; `start.sh` now generates a stable token from hostname if not already in env
- Unsloth Studio default URL corrected: `https://api.unsloth.ai/v1` → `http://localhost:2242/v1` (Unsloth is a local server, not a cloud API); API key default `"unsloth"`
- Duplicate field identifiers in `api.ts` SetupConfig (`lm_studio_embedding_model`, `ollama_base_url`) removed

### Embedding Configuration UI
- New `EmbeddingSection` in Setup UI (always visible, independent of LLM provider)
- Shows 3-tier embedding chain: 1️⃣ Ollama (primary, local) → 2️⃣ LM Studio (fallback) → 3️⃣ HuggingFace (cloud fallback)
- All fields configurable: Ollama URL + model, LM Studio embedding model, HF model + token
- Warning: model must produce 768-dim vectors for ChromaDB compatibility

### Providers
- **Unsloth Studio**: local OpenAI-compatible server (`localhost:2242`), 6 preset models

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
