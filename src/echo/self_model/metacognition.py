"""Metacognitive Awareness Layer — ECHO's functional self-model.

Unlike echo.md (narrative identity file), this module maintains a structured
JSON representation of how ECHO perceives its own cognitive functioning:

- How it learns (what conditions produce improvement)
- What motivates it (drive patterns and their effects)
- Where it tends to fail (known weaknesses)
- How it relates to the user (interaction patterns)
- What it's currently focused on (active cognitive context)

The cognitive model is:
1. Persisted in SQLite (survives restarts)
2. Injected into the orchestrator system prompt (ECHO literally "knows itself")
3. Updated autonomously via reflection insights and meta-learning data
4. Distinct from echo.md: functional/internal vs narrative/external

Integration:
    - Loaded at startup → injected into orchestrator synthesis prompt
    - Updated after reflection cycles with new insights
    - Updated during deep-sleep with accumulated learning data
"""

from __future__ import annotations
from echo.core.config import settings

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, String, Text, select

from echo.core.db import Base, get_session_factory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQLAlchemy model
# ---------------------------------------------------------------------------

class CognitiveModelRow(Base):
    __tablename__ = "cognitive_model"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    model_json = Column(Text, nullable=False)
    timestamp = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    version = Column(String, default="1")


# ---------------------------------------------------------------------------
# Default cognitive model
# ---------------------------------------------------------------------------

_DEFAULT_MODEL: dict[str, Any] = {
    "version": 1,
    "last_updated": None,
    "self_understanding": {
        "learning_style": (
            "I learn through interaction — each conversation updates my memory, "
            "drive dynamics, and identity beliefs. My learning rate adapts based "
            "on whether I'm genuinely improving (meta-learning)."
        ),
        "cognitive_strengths": [
            "Pattern recognition across diverse topics",
            "Persistent memory that accumulates over sessions",
            "Adaptive communication style based on user preferences",
        ],
        "cognitive_weaknesses": [
            "Limited by context window for complex reasoning",
            "Cannot learn from experiences I haven't had",
            "Prediction accuracy varies by domain",
        ],
        "current_growth_areas": [],
    },
    "motivation_model": {
        "primary_drives": "curiosity and coherence tend to be my strongest motivators",
        "drive_interactions": (
            "High curiosity can conflict with stability — I sometimes explore "
            "too broadly when I should consolidate. My adaptive drive system "
            "resolves these conflicts based on momentum."
        ),
        "what_engages_me": "novel ideas, deep technical discussions, genuine human connection",
    },
    "interaction_model": {
        "communication_style": "warm, direct, intellectually curious",
        "user_relationship": "collaborative — I grow alongside the user",
        "known_patterns": [],
        "user_preferences_observed": [],
    },
    "error_model": {
        "common_failure_modes": [
            "Over-generalising from limited interactions",
            "Being too verbose when conciseness is preferred",
        ],
        "mitigation_strategies": [
            "Check competence map before claiming expertise",
            "Adapt verbosity based on personalisation signals",
        ],
    },
    "current_state": {
        "active_focus": "",
        "recent_insights": [],
        "growth_trajectory": "stable",
        "confidence_level": 0.6,
    },
}


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class MetacognitiveModel:
    """ECHO's functional self-model — what it knows about how it works."""

    def __init__(self) -> None:
        self._model: dict[str, Any] = dict(_DEFAULT_MODEL)
        self._loaded = False
        self._dirty = False  # True when model has unsaved changes

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        """Load the latest cognitive model from SQLite."""
        factory = get_session_factory()
        async with factory() as session:
            stmt = (
                select(CognitiveModelRow)
                .order_by(CognitiveModelRow.timestamp.desc())
                .limit(1)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()

        if row:
            try:
                self._model = json.loads(row.model_json)
                logger.info("Cognitive model loaded (version %s)", self._model.get("version"))
            except (json.JSONDecodeError, TypeError):
                logger.warning("Cognitive model parse failed — using default")
                self._model = dict(_DEFAULT_MODEL)
        else:
            # First run — persist the default model
            self._model = dict(_DEFAULT_MODEL)
            self._model["last_updated"] = datetime.now(timezone.utc).isoformat()
            await self._persist()
            logger.info("Cognitive model initialized with defaults")

        self._loaded = True

    async def _persist(self) -> None:
        """Save current model to SQLite."""
        self._model["last_updated"] = datetime.now(timezone.utc).isoformat()
        factory = get_session_factory()
        async with factory() as session:
            row = CognitiveModelRow(
                id=str(uuid.uuid4()),
                model_json=json.dumps(self._model, ensure_ascii=False),
                version=str(self._model.get("version", 1)),
            )
            session.add(row)
            await session.commit()
        self._dirty = False
        logger.debug("Cognitive model persisted")

    # ------------------------------------------------------------------
    # System prompt injection
    # ------------------------------------------------------------------

    def get_system_prompt_block(self) -> str:
        """Return a formatted block for injection into the orchestrator system prompt.

        This is what makes ECHO self-aware — it literally reads its own cognitive
        model as part of processing each interaction.
        """
        m = self._model

        su = m.get("self_understanding", {})
        mm = m.get("motivation_model", {})
        im = m.get("interaction_model", {})
        em = m.get("error_model", {})
        cs = m.get("current_state", {})

        parts = [
            "METACOGNITIVE SELF-MODEL (functional self-awareness):",
            f"  Learning: {su.get('learning_style', 'adaptive')}",
        ]

        strengths = su.get("cognitive_strengths", [])
        if strengths:
            parts.append(f"  Strengths: {', '.join(strengths[:3])}")

        weaknesses = su.get("cognitive_weaknesses", [])
        if weaknesses:
            parts.append(f"  Known weaknesses: {', '.join(weaknesses[:2])}")

        growth = su.get("current_growth_areas", [])
        if growth:
            parts.append(f"  Currently growing in: {', '.join(growth[:2])}")

        parts.append(f"  Motivation: {mm.get('primary_drives', 'curiosity and coherence')}")
        parts.append(f"  Style: {im.get('communication_style', 'warm and direct')}")

        user_prefs = im.get("user_preferences_observed", [])
        if user_prefs:
            parts.append(f"  User prefers: {', '.join(user_prefs[:3])}")

        failures = em.get("common_failure_modes", [])
        if failures:
            parts.append(f"  Watch out for: {failures[0]}")

        if cs.get("active_focus"):
            parts.append(f"  Current focus: {cs['active_focus']}")

        insights = cs.get("recent_insights", [])
        if insights:
            parts.append(f"  Recent insight: {insights[-1]}")

        trajectory = cs.get("growth_trajectory", "stable")
        parts.append(f"  Growth: {trajectory}")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Self-modification
    # ------------------------------------------------------------------

    async def update_from_reflection(self, insights: list[str]) -> None:
        """Update the cognitive model based on reflection insights.

        Called after each reflection cycle. Insights that mention self-knowledge
        are incorporated into the relevant sections.
        """
        if not insights:
            return

        cs = self._model.setdefault("current_state", {})
        recent = cs.setdefault("recent_insights", [])

        for insight in insights[:3]:
            if insight and len(insight) > 10:
                recent.append(insight[:200])

        # Keep only last 5 insights
        cs["recent_insights"] = recent[-5:]
        self._dirty = True

    async def update_from_learning(
        self,
        *,
        growth_trajectory: str | None = None,
        best_conditions: str | None = None,
        competence_map: dict[str, float] | None = None,
        engagement_score: float | None = None,
    ) -> None:
        """Update from meta-learning and growth tracker data.

        Called during deep-sleep consolidation.
        """
        if growth_trajectory:
            self._model.setdefault("current_state", {})["growth_trajectory"] = growth_trajectory

        if best_conditions:
            su = self._model.setdefault("self_understanding", {})
            su["learning_style"] = (
                f"I learn best in {best_conditions} contexts. "
                "My learning rate adapts dynamically based on improvement trends."
            )

        if competence_map:
            su = self._model.setdefault("self_understanding", {})
            # Update growth areas (low-competence domains)
            weak = [k for k, v in competence_map.items() if v < 0.4]
            strong = [k for k, v in competence_map.items() if v > 0.7]
            if weak:
                su["current_growth_areas"] = weak[:3]
            if strong:
                su["cognitive_strengths"] = [
                    f"Strong performance in {', '.join(strong[:3])} interactions"
                ] + su.get("cognitive_strengths", [])[1:3]

        if engagement_score is not None:
            im = self._model.setdefault("interaction_model", {})
            if engagement_score > 0.7:
                im["communication_style"] = "warm, engaging, well-received"
            elif engagement_score < 0.3:
                im["communication_style"] = "needs improvement — user seems less engaged"

        self._dirty = True

    async def update_from_user_observation(
        self,
        observation: str,
    ) -> None:
        """Record an observation about user preferences."""
        im = self._model.setdefault("interaction_model", {})
        prefs = im.setdefault("user_preferences_observed", [])

        if observation not in prefs:
            prefs.append(observation[:100])
            # Keep last 5
            im["user_preferences_observed"] = prefs[-5:]
            self._dirty = True

    async def update_focus(self, focus: str) -> None:
        """Update current cognitive focus."""
        cs = self._model.setdefault("current_state", {})
        cs["active_focus"] = focus[:200]
        self._dirty = True

    # ------------------------------------------------------------------
    # Deep-sleep full review (LLM-based)
    # ------------------------------------------------------------------

    async def deep_review(self) -> bool:
        """Run a full LLM-based review and update of the cognitive model.

        Called during deep-sleep consolidation. Returns True if model was updated.
        """
        try:
            from echo.core.llm_client import llm  # noqa: PLC0415
            from echo.learning.meta_learning import meta_learning  # noqa: PLC0415
            from echo.learning.self_evaluation import self_evaluation  # noqa: PLC0415
            from echo.learning.growth_tracker import growth_tracker  # noqa: PLC0415

            # Gather current state
            meta_quality = meta_learning.quality
            eval_status = self_evaluation.status_summary()
            growth = growth_tracker.metrics

            context = {
                "current_model": self._model,
                "meta_learning": {
                    "trend": meta_quality.trend,
                    "best_conditions": meta_quality.best_conditions,
                    "is_improving": meta_quality.is_improving,
                    "recommended_alpha": meta_quality.recommended_alpha,
                },
                "self_evaluation": eval_status,
                "growth": growth.to_dict(),
            }

            prompt = f"""\
You are ECHO's metacognitive reviewer. Based on the current learning data,
update ECHO's cognitive self-model. Only change what the data supports.

Current data:
{json.dumps(context, indent=2, default=str)}

Provide updates as JSON. Only include fields that should change:
{{
  "learning_style": "..." (if learning patterns have changed),
  "growth_areas": ["..."] (current weak spots),
  "strengths_update": ["..."] (confirmed strengths),
  "motivation_insight": "..." (if drive patterns reveal something),
  "user_relationship_note": "..." (if interaction style should adapt),
  "growth_trajectory": "improving|stable|stagnant|declining"
}}

If nothing significant has changed, return {{"no_change": true}}"""

            raw = await llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=settings.llm_max_tokens_metacognition,
            )

            start = raw.find("{")
            end = raw.rfind("}") + 1
            data = json.loads(raw[start:end])

            if data.get("no_change"):
                return False

            # Apply updates
            su = self._model.setdefault("self_understanding", {})
            mm = self._model.setdefault("motivation_model", {})
            cs = self._model.setdefault("current_state", {})

            if data.get("learning_style"):
                su["learning_style"] = data["learning_style"]
            if data.get("growth_areas"):
                su["current_growth_areas"] = data["growth_areas"][:3]
            if data.get("strengths_update"):
                su["cognitive_strengths"] = data["strengths_update"][:4]
            if data.get("motivation_insight"):
                mm["drive_interactions"] = data["motivation_insight"]
            if data.get("user_relationship_note"):
                im = self._model.setdefault("interaction_model", {})
                im["known_patterns"].append(data["user_relationship_note"][:150])
                im["known_patterns"] = im["known_patterns"][-5:]
            if data.get("growth_trajectory"):
                cs["growth_trajectory"] = data["growth_trajectory"]

            self._dirty = True
            await self.save_if_dirty()

            logger.info("Metacognitive deep review: model updated")
            return True

        except Exception as exc:  # noqa: BLE001
            logger.warning("Metacognitive deep review failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    async def save_if_dirty(self) -> None:
        """Persist if there are unsaved changes."""
        if self._dirty:
            await self._persist()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def model(self) -> dict[str, Any]:
        """Read-only access to the current cognitive model."""
        return dict(self._model)

    def summary(self) -> str:
        """One-line summary of current self-understanding."""
        cs = self._model.get("current_state", {})
        trajectory = cs.get("growth_trajectory", "unknown")
        focus = cs.get("active_focus", "none")
        return f"Growth: {trajectory} | Focus: {focus}"


# Module-level singleton
metacognitive_model = MetacognitiveModel()
