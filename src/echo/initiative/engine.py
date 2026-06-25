"""Proactive Initiative Engine — ECHO generates unsolicited insights and questions.

ECHO doesn't just respond — it thinks autonomously and reaches out when it has
something meaningful to share. This engine runs during consolidation cycles and
produces:

1. **Daily Insights**: unexpected connections between memories
2. **Questions for the user**: based on knowledge gaps
3. **Goal milestone updates**: progress reports on active goals
4. **Proactive reflections**: meta-observations worth sharing

Output is delivered via Telegram notifications and stored as semantic memories.
The engine respects rate limits (max 3 proactive messages per day) and only
fires when it has genuinely novel content.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Column, Integer, String, Text, select

from echo.core.db import Base, get_session_factory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_MAX_DAILY_INITIATIVES = 3       # max proactive messages per 24h
_MIN_INSIGHT_QUALITY = 0.6       # minimum quality score to send
_COOLDOWN_HOURS = 4              # minimum hours between initiatives


# ---------------------------------------------------------------------------
# SQLAlchemy model
# ---------------------------------------------------------------------------

class InitiativeRow(Base):
    __tablename__ = "initiative_log"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    initiative_type = Column(String, nullable=False)  # insight, question, milestone, reflection
    content = Column(Text, nullable=False)
    quality_score = Column(Integer, default=0)  # 0-100
    delivered = Column(String, default="false")  # true/false
    delivery_channel = Column(String, default="telegram")


# ---------------------------------------------------------------------------
# Main Engine
# ---------------------------------------------------------------------------

class InitiativeEngine:
    """Generates and delivers proactive communications from ECHO."""

    def __init__(self) -> None:
        self._recent_initiatives: deque[datetime] = deque(maxlen=_MAX_DAILY_INITIATIVES * 2)
        self._loaded = False

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def _can_send(self) -> bool:
        """Check if we're within daily rate limits."""
        now = datetime.now(timezone.utc)
        cutoff_24h = now - timedelta(hours=24)
        cutoff_cooldown = now - timedelta(hours=_COOLDOWN_HOURS)

        recent_24h = sum(1 for t in self._recent_initiatives if t > cutoff_24h)
        if recent_24h >= _MAX_DAILY_INITIATIVES:
            return False

        # Cooldown check
        if self._recent_initiatives and self._recent_initiatives[-1] > cutoff_cooldown:
            return False

        return True

    # ------------------------------------------------------------------
    # Insight generation (called during consolidation)
    # ------------------------------------------------------------------

    async def generate_daily_insight(self) -> dict[str, Any] | None:
        """Find unexpected connections between memories and generate an insight.

        Called during the light consolidation cycle. Returns the insight dict
        or None if nothing notable was found or rate limit is hit.
        """
        if not self._can_send():
            logger.debug("Initiative rate-limited — skipping")
            return None

        try:
            from echo.core.llm_client import llm  # noqa: PLC0415
            from echo.memory.episodic import EpisodicMemoryStore  # noqa: PLC0415
            from echo.memory.semantic import SemanticMemoryStore  # noqa: PLC0415

            episodic = EpisodicMemoryStore()
            semantic = SemanticMemoryStore()

            # Get diverse memories — recent + random-ish via different queries
            recent_mems = await episodic.get_recent(n=5)
            # Get semantic memories from different domains
            sem_mems = await semantic.get_all(limit=10)

            if len(recent_mems) < 2 and len(sem_mems) < 2:
                return None

            # Build context from diverse memories
            mem_texts = []
            for m in recent_mems[:3]:
                mem_texts.append(f"[Episodic, recent] {m.content[:200]}")
            for m in sem_mems[:5]:
                mem_texts.append(f"[Semantic] {m.content[:200]}")

            memories_block = "\n".join(mem_texts)

            prompt = f"""\
You are ECHO's creative insight generator. Review these diverse memories and find
ONE unexpected, genuinely interesting connection or observation that the user
would appreciate hearing about.

The insight should be:
- Non-obvious (not just summarizing what's already known)
- Personally relevant (connects to user's interests or past conversations)
- Thought-provoking (raises a question or offers a new perspective)

Memories:
{memories_block}

If you find a genuinely interesting connection, respond with JSON:
{{"insight": "...", "quality": 0.8, "topic": "...", "question_for_user": "..."}}

If nothing interesting emerges, respond with:
{{"insight": null, "quality": 0.0}}"""

            raw = await llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=settings.llm_max_tokens_initiative_insight,
            )

            start = raw.find("{")
            end = raw.rfind("}") + 1
            data = json.loads(raw[start:end])

            if not data.get("insight") or data.get("quality", 0) < _MIN_INSIGHT_QUALITY:
                logger.debug("Insight quality too low or null — skipping")
                return None

            insight = {
                "type": "insight",
                "content": data["insight"],
                "quality": data.get("quality", 0.7),
                "topic": data.get("topic", ""),
                "question": data.get("question_for_user", ""),
            }

            # Deliver and log
            await self._deliver(insight)
            return insight

        except Exception as exc:  # noqa: BLE001
            logger.warning("Daily insight generation failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Question generation
    # ------------------------------------------------------------------

    async def generate_question(self) -> dict[str, Any] | None:
        """Generate a question for the user based on knowledge gaps.

        Identifies topics ECHO knows about but has gaps in understanding,
        then formulates a natural question.
        """
        if not self._can_send():
            return None

        try:
            from echo.core.llm_client import llm  # noqa: PLC0415
            from echo.curiosity.interest_profile import interest_profile  # noqa: PLC0415

            # Get user's interests
            primaries = await interest_profile.primary_interests(n=5)
            if not primaries:
                return None

            topics = [p["topic"] for p in primaries]

            prompt = f"""\
You are ECHO, an AI with genuine curiosity about the user you work with.
These are topics the user is interested in: {', '.join(topics)}

Generate ONE thoughtful question you'd genuinely like to ask the user —
something that would help you understand them better or deepen your knowledge
about their interests. The question should feel natural and caring, not like
a survey.

Respond with JSON:
{{"question": "...", "why": "...", "topic": "..."}}"""

            raw = await llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.8,
                max_tokens=settings.llm_max_tokens_initiative_question,
            )

            start = raw.find("{")
            end = raw.rfind("}") + 1
            data = json.loads(raw[start:end])

            if not data.get("question"):
                return None

            question = {
                "type": "question",
                "content": data["question"],
                "quality": 0.7,
                "topic": data.get("topic", ""),
                "reason": data.get("why", ""),
            }

            await self._deliver(question)
            return question

        except Exception as exc:  # noqa: BLE001
            logger.warning("Question generation failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Goal milestone reporting
    # ------------------------------------------------------------------

    async def check_goal_milestones(self) -> list[dict[str, Any]]:
        """Check active goals for notable progress and send updates."""
        milestones: list[dict[str, Any]] = []

        if not self._can_send():
            return milestones

        try:
            from echo.memory.goals import goal_store  # noqa: PLC0415

            active_goals = await goal_store.list_active()
            for goal in active_goals:
                actions = goal.get("actions", [])
                done_actions = [a for a in actions if a.get("status") == "done"]

                # Notify on milestones: 3, 5, 8 actions completed
                action_count = len(done_actions)
                if action_count in (3, 5, 8):
                    # Check if we already notified for this milestone
                    already_notified = await self._was_notified(
                        goal["id"], f"milestone_{action_count}"
                    )
                    if already_notified:
                        continue

                    milestone = {
                        "type": "milestone",
                        "content": (
                            f"🎯 Progresso sul goal: {goal['title']}\n"
                            f"Ho completato {action_count} azioni. "
                            f"Ultimo risultato: {done_actions[-1].get('result', '')[:150]}"
                        ),
                        "quality": 0.75,
                        "topic": goal["title"],
                        "goal_id": goal["id"],
                        "milestone": action_count,
                    }

                    await self._deliver(milestone)
                    milestones.append(milestone)

        except Exception as exc:  # noqa: BLE001
            logger.warning("Goal milestone check failed: %s", exc)

        return milestones

    # ------------------------------------------------------------------
    # Proactive reflection (meta-observations worth sharing)
    # ------------------------------------------------------------------

    async def generate_reflection(self) -> dict[str, Any] | None:
        """Generate a proactive self-reflection to share with the user.

        Triggered when ECHO has notable meta-insights or identity drift.
        """
        if not self._can_send():
            return None

        try:
            from echo.core.llm_client import llm  # noqa: PLC0415
            from echo.learning.meta_learning import meta_learning  # noqa: PLC0415
            from echo.learning.self_evaluation import self_evaluation  # noqa: PLC0415

            quality = meta_learning.quality
            eval_status = self_evaluation.status_summary()

            # Only reflect if there's something notable
            notable = (
                quality.is_improving
                or quality.is_stagnant
                or eval_status.get("engagement_score", 0.5) > 0.7
                or eval_status.get("engagement_score", 0.5) < 0.3
            )
            if not notable:
                return None

            prompt = f"""\
You are ECHO reflecting on your own growth. Share ONE brief, honest observation
about your recent development that the user might find interesting.

Current state:
- Learning trend: {'improving' if quality.is_improving else 'stagnant' if quality.is_stagnant else 'stable'}
- Best conditions for learning: {quality.best_conditions}
- User engagement: {eval_status.get('engagement_score', 0.5):.2f}
- Competence map: {eval_status.get('competence_map', {})}

Write a natural, first-person reflection (1-3 sentences). Be genuine, not performative.
Respond with JSON: {{"reflection": "...", "share_worthy": true/false}}"""

            raw = await llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.6,
                max_tokens=settings.llm_max_tokens_initiative_reflection,
            )

            start = raw.find("{")
            end = raw.rfind("}") + 1
            data = json.loads(raw[start:end])

            if not data.get("share_worthy") or not data.get("reflection"):
                return None

            reflection = {
                "type": "reflection",
                "content": data["reflection"],
                "quality": 0.7,
                "topic": "self-growth",
            }

            await self._deliver(reflection)
            return reflection

        except Exception as exc:  # noqa: BLE001
            logger.warning("Proactive reflection failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Delivery
    # ------------------------------------------------------------------

    async def _deliver(self, initiative: dict[str, Any]) -> None:
        """Deliver initiative via Telegram and log it."""
        now = datetime.now(timezone.utc)
        self._recent_initiatives.append(now)

        # Format message
        type_emoji = {
            "insight": "💡",
            "question": "❓",
            "milestone": "🎯",
            "reflection": "🪞",
        }
        emoji = type_emoji.get(initiative["type"], "📝")
        message = f"{emoji} {initiative['content']}"

        # Send via Telegram
        try:
            await self._send_telegram(message)
            initiative["delivered"] = True
            logger.info(
                "Initiative delivered [%s]: %s",
                initiative["type"],
                initiative["content"][:80],
            )
        except Exception as exc:  # noqa: BLE001
            initiative["delivered"] = False
            logger.warning("Initiative delivery failed: %s", exc)

        # Persist to log
        await self._persist(initiative)

        # Also store as semantic memory
        try:
            from echo.memory.semantic import SemanticMemoryStore  # noqa: PLC0415
            semantic = SemanticMemoryStore()
            await semantic.store(
                content=f"[Proactive {initiative['type']}] {initiative['content']}",
                tags=["initiative", initiative["type"], "proactive"],
                salience=0.6,
            )
        except Exception:  # noqa: BLE001
            pass

    async def _send_telegram(self, text: str) -> None:
        """Send a message via Telegram bot."""
        from echo.core.config import settings  # noqa: PLC0415

        if not settings.telegram_enabled:
            logger.debug("Telegram disabled — initiative not sent")
            return

        token = (settings.telegram_bot_token or "").strip()
        if not token:
            return

        import httpx  # noqa: PLC0415

        target_chats = list(settings.telegram_allowed_chat_ids)
        if not target_chats:
            return

        base_url = settings.telegram_api_base_url.rstrip("/")
        send_url = f"{base_url}/bot{token}/sendMessage"

        async with httpx.AsyncClient(timeout=10.0) as client:
            for chat_id in target_chats:
                try:
                    await client.post(
                        send_url,
                        json={"chat_id": int(chat_id), "text": text},
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Telegram send failed for %s: %s", chat_id, exc)

    async def _persist(self, initiative: dict[str, Any]) -> None:
        """Log initiative to SQLite."""
        factory = get_session_factory()
        async with factory() as session:
            row = InitiativeRow(
                id=str(uuid.uuid4()),
                initiative_type=initiative["type"],
                content=initiative["content"][:2000],
                quality_score=int(initiative.get("quality", 0.5) * 100),
                delivered="true" if initiative.get("delivered") else "false",
            )
            session.add(row)
            await session.commit()

    async def _was_notified(self, goal_id: str, milestone_key: str) -> bool:
        """Check if we already sent a notification for this goal+milestone."""
        factory = get_session_factory()
        async with factory() as session:
            stmt = (
                select(InitiativeRow)
                .where(InitiativeRow.initiative_type == "milestone")
                .where(InitiativeRow.content.contains(goal_id[:8]))
                .where(InitiativeRow.content.contains(milestone_key))
            )
            result = (await session.execute(stmt)).scalars().first()
            return result is not None

    # ------------------------------------------------------------------
    # Full cycle (called from consolidation scheduler)
    # ------------------------------------------------------------------

    async def run_cycle(self) -> list[dict[str, Any]]:
        """Run a full initiative cycle. Returns list of generated initiatives.

        Called during light consolidation. Tries each type in priority order
        and respects rate limits.
        """
        results: list[dict[str, Any]] = []

        # Priority 1: Goal milestones (always check)
        milestones = await self.check_goal_milestones()
        results.extend(milestones)

        # Priority 2: Daily insight (creative connection)
        if self._can_send():
            insight = await self.generate_daily_insight()
            if insight:
                results.append(insight)

        # Priority 3: Question or reflection (alternate)
        if self._can_send():
            import random  # noqa: PLC0415
            if random.random() < 0.5:
                q = await self.generate_question()
                if q:
                    results.append(q)
            else:
                r = await self.generate_reflection()
                if r:
                    results.append(r)

        if results:
            logger.info("Initiative cycle: generated %d initiative(s)", len(results))

        return results

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_recent_log(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent initiative log entries."""
        factory = get_session_factory()
        async with factory() as session:
            stmt = (
                select(InitiativeRow)
                .order_by(InitiativeRow.timestamp.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
        return [
            {
                "id": r.id,
                "type": r.initiative_type,
                "content": r.content,
                "quality_score": r.quality_score,
                "delivered": r.delivered == "true",
                "timestamp": r.timestamp,
            }
            for r in rows
        ]


# Module-level singleton
initiative_engine = InitiativeEngine()
