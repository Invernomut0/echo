# Module 15 — Proactive Initiative Engine

**Source:** `src/echo/initiative/engine.py`

ECHO doesn't just respond — it thinks autonomously and reaches out when it has something meaningful to share.

---

## Initiative Types

| Type | Emoji | Description |
|------|-------|-------------|
| `insight` | 💡 | Unexpected connections between memories |
| `question` | ❓ | Thoughtful questions based on knowledge gaps |
| `milestone` | 🎯 | Goal progress reports (at 3, 5, 8 actions) |
| `reflection` | 🪞 | Meta-observations about self-growth |

---

## Rate Limiting

- Maximum **3 initiatives per 24 hours**
- Minimum **4 hours** between initiatives
- Quality threshold: insight quality must be ≥ 0.6

---

## Generation Flow

### Daily Insight
1. Retrieve diverse memories (recent episodic + varied semantic)
2. Ask LLM to find ONE non-obvious connection
3. Validate quality score ≥ 0.6
4. Deliver via Telegram + store as semantic memory

### Question Generation
1. Read user's interest profile (top 5 topics)
2. Ask LLM to formulate a natural, caring question
3. Deliver via Telegram

### Goal Milestones
1. Check active goals for action count milestones
2. Deduplicate against already-sent notifications
3. Format progress update

### Proactive Reflection
1. Check if state is notable (improving, stagnant, high/low engagement)
2. Ask LLM for a genuine self-observation
3. Only share if LLM rates it as `share_worthy: true`

---

## Delivery

All initiatives are:
1. Sent via Telegram (if enabled and configured)
2. Persisted to `initiative_log` table in SQLite
3. Stored as semantic memory with tags `["initiative", type, "proactive"]`

---

## Integration

| Component | Trigger |
|-----------|---------|
| Light consolidation cycle | `initiative_engine.run_cycle()` — after curiosity engine |
| Telegram | Outbound messages via `httpx` |
| Settings | `telegram_enabled`, `telegram_bot_token`, `telegram_allowed_chat_ids` |
