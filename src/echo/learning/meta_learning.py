"""Meta-Learning Module — ECHO learns *how* it learns best.

Tracks which types of experiences produce genuine improvement (measured by
declining prediction error) and adapts learning parameters accordingly.

Components:
    - LearningQualityTracker: rolling history of prediction errors + context
    - Dynamic α modulation: faster learning when quality is high, slower when noisy
    - Meta-insight journal: periodic LLM-generated observations about learning patterns
    - Integration hooks for LearningEngine and pipeline

Design principles:
    - Pure statistics where possible; LLM only for journal entries
    - Persistence via SQLite (survives restarts)
    - Non-blocking — all heavy work is fire-and-forget
"""

from __future__ import annotations
from echo.core.config import settings

import json
import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, Float, Integer, String, Text, select

from echo.core.db import Base, get_session_factory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_WINDOW_SIZE = 100          # observations for trend analysis
_INSIGHT_EVERY_N = 50       # generate a meta-insight every N observations
_MIN_OBSERVATIONS = 10      # need at least this many before computing trends
_ALPHA_BASE = 0.08          # default EMA alpha (matches personalization.py)
_ALPHA_MIN = 0.03           # minimum α (very slow learning — noisy regime)
_ALPHA_MAX = 0.20           # maximum α (fast learning — high quality regime)


# ---------------------------------------------------------------------------
# SQLAlchemy model — persists meta-learning observations
# ---------------------------------------------------------------------------

class MetaLearningRow(Base):
    __tablename__ = "meta_learning_observations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    prediction_error = Column(Float, nullable=False)
    interaction_type = Column(String, default="general")  # general, technical, emotional, creative
    user_engagement = Column(Float, default=0.5)
    response_length = Column(Integer, default=0)
    novelty_score = Column(Float, default=0.5)
    drive_state = Column(Text, default="{}")  # JSON snapshot of drive scores


class MetaInsightRow(Base):
    __tablename__ = "meta_insights"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    content = Column(Text, nullable=False)
    confidence = Column(Float, default=0.6)
    observation_count = Column(Integer, default=0)  # how many obs were used to derive this
    applied = Column(String, default="false")  # whether it has been acted upon


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class LearningObservation:
    """One data point about a learning event."""

    prediction_error: float
    interaction_type: str = "general"
    user_engagement: float = 0.5
    response_length: int = 0
    novelty_score: float = 0.5
    curiosity: float = 0.5
    coherence: float = 0.5
    emotional_valence: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class LearningQuality:
    """Computed quality metrics for the current learning regime."""

    trend: float = 0.0              # negative = improving, positive = degrading
    volatility: float = 0.5         # std dev of prediction error
    best_conditions: str = ""       # description of when learning is best
    recommended_alpha: float = _ALPHA_BASE
    is_improving: bool = False
    is_stagnant: bool = False
    observations_count: int = 0


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class MetaLearningEngine:
    """Tracks learning quality and adapts learning parameters."""

    def __init__(self) -> None:
        self._observations: deque[LearningObservation] = deque(maxlen=_WINDOW_SIZE)
        self._n: int = 0
        self._last_insight_at: int = 0
        self._cached_quality: LearningQuality = LearningQuality()
        self._loaded = False

        # Per-type error tracking (interaction_type → list of recent errors)
        self._type_errors: dict[str, deque[float]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        """Load recent observations from SQLite to warm the rolling window."""
        factory = get_session_factory()
        async with factory() as session:
            stmt = (
                select(MetaLearningRow)
                .order_by(MetaLearningRow.timestamp.desc())
                .limit(_WINDOW_SIZE)
            )
            rows = (await session.execute(stmt)).scalars().all()

        for row in reversed(rows):  # oldest first
            obs = LearningObservation(
                prediction_error=row.prediction_error,
                interaction_type=row.interaction_type or "general",
                user_engagement=row.user_engagement or 0.5,
                response_length=row.response_length or 0,
                novelty_score=row.novelty_score or 0.5,
            )
            self._observations.append(obs)
            self._n += 1

            # Rebuild per-type tracking
            t = obs.interaction_type
            if t not in self._type_errors:
                self._type_errors[t] = deque(maxlen=30)
            self._type_errors[t].append(obs.prediction_error)

        self._loaded = True
        self._recompute_quality()
        logger.info(
            "MetaLearningEngine loaded: %d observations, trend=%.4f, α=%.4f",
            self._n,
            self._cached_quality.trend,
            self._cached_quality.recommended_alpha,
        )

    # ------------------------------------------------------------------
    # Observation ingestion
    # ------------------------------------------------------------------

    async def observe(
        self,
        prediction_error: float,
        interaction_type: str = "general",
        user_engagement: float = 0.5,
        response_length: int = 0,
        novelty_score: float = 0.5,
        curiosity: float = 0.5,
        coherence: float = 0.5,
        emotional_valence: float = 0.0,
        drive_scores: dict[str, float] | None = None,
    ) -> LearningQuality:
        """Record one learning observation and recompute quality metrics.

        Returns the updated LearningQuality so callers can act immediately.
        """
        obs = LearningObservation(
            prediction_error=prediction_error,
            interaction_type=interaction_type,
            user_engagement=user_engagement,
            response_length=response_length,
            novelty_score=novelty_score,
            curiosity=curiosity,
            coherence=coherence,
            emotional_valence=emotional_valence,
        )
        self._observations.append(obs)
        self._n += 1

        # Per-type tracking
        if interaction_type not in self._type_errors:
            self._type_errors[interaction_type] = deque(maxlen=30)
        self._type_errors[interaction_type].append(prediction_error)

        # Persist to SQLite (non-blocking)
        await self._persist_observation(obs, drive_scores)

        # Recompute quality
        self._recompute_quality()

        # Generate meta-insight periodically
        if self._n - self._last_insight_at >= _INSIGHT_EVERY_N and self._n >= _MIN_OBSERVATIONS:
            self._last_insight_at = self._n
            # Fire-and-forget — don't block the pipeline
            import asyncio
            asyncio.create_task(self._generate_meta_insight())

        return self._cached_quality

    # ------------------------------------------------------------------
    # Quality computation (pure math, no LLM)
    # ------------------------------------------------------------------

    def _recompute_quality(self) -> None:
        """Recompute learning quality from the observation window."""
        obs = list(self._observations)
        n = len(obs)

        if n < _MIN_OBSERVATIONS:
            self._cached_quality = LearningQuality(observations_count=n)
            return

        errors = [o.prediction_error for o in obs]

        # Trend: linear regression slope of prediction error over time
        # Negative slope = improving (error going down)
        trend = self._compute_trend(errors)

        # Volatility: standard deviation of last 20 errors
        recent = errors[-20:]
        mean_recent = sum(recent) / len(recent)
        volatility = (sum((e - mean_recent) ** 2 for e in recent) / len(recent)) ** 0.5

        # Determine best conditions — which interaction types have lowest errors
        best_conditions = self._find_best_conditions()

        # Dynamic alpha: lower volatility + improving trend → higher α (learn faster)
        # High volatility or degrading trend → lower α (be cautious)
        stability_factor = max(0.0, 1.0 - volatility * 2)  # [0, 1]
        improvement_factor = max(0.0, min(1.0, 0.5 - trend * 5))  # [0, 1] — negative trend helps
        quality_score = 0.6 * stability_factor + 0.4 * improvement_factor

        recommended_alpha = _ALPHA_MIN + (_ALPHA_MAX - _ALPHA_MIN) * quality_score
        recommended_alpha = round(max(_ALPHA_MIN, min(_ALPHA_MAX, recommended_alpha)), 4)

        is_improving = trend < -0.001 and n >= 20
        is_stagnant = abs(trend) < 0.0005 and n >= 50

        self._cached_quality = LearningQuality(
            trend=round(trend, 6),
            volatility=round(volatility, 4),
            best_conditions=best_conditions,
            recommended_alpha=recommended_alpha,
            is_improving=is_improving,
            is_stagnant=is_stagnant,
            observations_count=n,
        )

    @staticmethod
    def _compute_trend(values: list[float]) -> float:
        """Linear regression slope over a sequence of values."""
        n = len(values)
        if n < 3:
            return 0.0
        xs = list(range(n))
        mx = sum(xs) / n
        my = sum(values) / n
        num = sum((x - mx) * (y - my) for x, y in zip(xs, values, strict=False))
        den = sum((x - mx) ** 2 for x in xs)
        return num / den if den != 0 else 0.0

    def _find_best_conditions(self) -> str:
        """Identify which interaction types produce the lowest prediction error."""
        if not self._type_errors:
            return "insufficient data"

        type_means: dict[str, float] = {}
        for itype, errors in self._type_errors.items():
            if len(errors) >= 3:
                type_means[itype] = sum(errors) / len(errors)

        if not type_means:
            return "insufficient data"

        # Sort by mean error (ascending — lower is better)
        sorted_types = sorted(type_means.items(), key=lambda kv: kv[1])
        best = sorted_types[0]
        return f"{best[0]} (avg_error={best[1]:.3f})"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def quality(self) -> LearningQuality:
        """Current learning quality assessment (read-only, no computation)."""
        return self._cached_quality

    @property
    def recommended_alpha(self) -> float:
        """Dynamic EMA alpha for personalization — use this instead of the static 0.08."""
        return self._cached_quality.recommended_alpha

    def get_type_performance(self) -> dict[str, dict[str, float]]:
        """Return mean prediction error per interaction type."""
        result = {}
        for itype, errors in self._type_errors.items():
            if errors:
                err_list = list(errors)
                result[itype] = {
                    "mean_error": round(sum(err_list) / len(err_list), 4),
                    "count": len(err_list),
                    "latest": round(err_list[-1], 4),
                }
        return result

    # ------------------------------------------------------------------
    # Meta-insight generation (LLM-based, periodic)
    # ------------------------------------------------------------------

    async def _generate_meta_insight(self) -> None:
        """Use LLM to generate a meta-observation about learning patterns."""
        try:
            from echo.core.llm_client import llm  # noqa: PLC0415

            # Prepare context
            obs = list(self._observations)[-30:]
            type_perf = self.get_type_performance()
            quality = self._cached_quality

            context = {
                "total_observations": self._n,
                "trend": quality.trend,
                "volatility": quality.volatility,
                "is_improving": quality.is_improving,
                "is_stagnant": quality.is_stagnant,
                "recommended_alpha": quality.recommended_alpha,
                "best_conditions": quality.best_conditions,
                "type_performance": type_perf,
                "recent_errors": [round(o.prediction_error, 3) for o in obs[-10:]],
                "recent_types": [o.interaction_type for o in obs[-10:]],
            }

            prompt = f"""\
You are ECHO's meta-cognitive monitor. Analyse these learning statistics and generate
ONE concise meta-insight (1-2 sentences) about ECHO's learning patterns.

Focus on actionable observations: when does ECHO learn best? What conditions produce
improvement? What should change?

Learning statistics:
{json.dumps(context, indent=2)}

Respond with ONLY valid JSON:
{{"insight": "...", "confidence": 0.7}}"""

            raw = await llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=settings.llm_max_tokens_meta_insight,
            )
            start = raw.find("{")
            end = raw.rfind("}") + 1
            data = json.loads(raw[start:end])

            insight_text = data.get("insight", "")
            confidence = float(data.get("confidence", 0.6))

            if insight_text and len(insight_text) > 10:
                await self._persist_insight(insight_text, confidence)
                logger.info("Meta-insight generated: %s (conf=%.2f)", insight_text[:80], confidence)

        except Exception as exc:  # noqa: BLE001
            logger.debug("Meta-insight generation failed: %s", exc)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _persist_observation(
        self,
        obs: LearningObservation,
        drive_scores: dict[str, float] | None = None,
    ) -> None:
        """Save observation to SQLite."""
        factory = get_session_factory()
        async with factory() as session:
            row = MetaLearningRow(
                id=str(uuid.uuid4()),
                timestamp=obs.timestamp.isoformat(),
                prediction_error=obs.prediction_error,
                interaction_type=obs.interaction_type,
                user_engagement=obs.user_engagement,
                response_length=obs.response_length,
                novelty_score=obs.novelty_score,
                drive_state=json.dumps(drive_scores or {}),
            )
            session.add(row)
            await session.commit()

    async def _persist_insight(self, content: str, confidence: float) -> None:
        """Save a meta-insight to SQLite."""
        factory = get_session_factory()
        async with factory() as session:
            row = MetaInsightRow(
                id=str(uuid.uuid4()),
                content=content,
                confidence=confidence,
                observation_count=self._n,
            )
            session.add(row)
            await session.commit()

    async def get_recent_insights(self, n: int = 5) -> list[dict[str, Any]]:
        """Return the N most recent meta-insights."""
        factory = get_session_factory()
        async with factory() as session:
            stmt = (
                select(MetaInsightRow)
                .order_by(MetaInsightRow.timestamp.desc())
                .limit(n)
            )
            rows = (await session.execute(stmt)).scalars().all()
        return [
            {
                "id": r.id,
                "content": r.content,
                "confidence": r.confidence,
                "observation_count": r.observation_count,
                "timestamp": r.timestamp,
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Interaction type classification (lightweight heuristic)
    # ------------------------------------------------------------------

    @staticmethod
    def classify_interaction(user_input: str, response: str) -> str:
        """Classify interaction type based on content heuristics.

        Returns one of: technical, emotional, creative, philosophical, general
        """
        text = (user_input + " " + response).lower()

        # Technical markers
        tech_markers = {"code", "function", "api", "error", "debug", "python",
                       "algorithm", "database", "server", "deploy", "bug"}
        if sum(1 for m in tech_markers if m in text) >= 2:
            return "technical"

        # Emotional markers
        emo_markers = {"feel", "sad", "happy", "angry", "worried", "love",
                      "afraid", "anxious", "grateful", "frustrated",
                      "sento", "felice", "triste", "paura", "grazie"}
        if sum(1 for m in emo_markers if m in text) >= 2:
            return "emotional"

        # Creative markers
        creative_markers = {"imagine", "story", "poem", "create", "design",
                          "art", "music", "write", "invent", "fantasia",
                          "scrivi", "inventa", "crea", "racconto"}
        if sum(1 for m in creative_markers if m in text) >= 2:
            return "creative"

        # Philosophical markers
        phil_markers = {"meaning", "consciousness", "exist", "truth", "moral",
                       "ethics", "purpose", "reality", "free will",
                       "coscienza", "esistenza", "verità", "senso", "etica"}
        if sum(1 for m in phil_markers if m in text) >= 2:
            return "philosophical"

        return "general"


# Module-level singleton
meta_learning = MetaLearningEngine()
