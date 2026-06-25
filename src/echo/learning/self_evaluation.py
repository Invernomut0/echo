"""Self-Evaluation Loop — ECHO evaluates its own performance over time.

Components:
    - PredictionTracker: tracks prediction error trends across interactions
    - SkillAssessment: periodic LLM-based self-evaluation on multiple dimensions
    - CompetenceMap: persistent map of strengths/weaknesses by domain
    - Implicit feedback detection: engagement signals from user behaviour

Integration:
    Called from _post_interact after each interaction to record signals,
    and periodically (every ASSESSMENT_INTERVAL interactions) for deep eval.
"""

from __future__ import annotations

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

_ASSESSMENT_INTERVAL = 50     # run full skill assessment every N interactions
_TREND_WINDOW = 50            # prediction error trend window
_COMPETENCE_DECAY = 0.995     # slow decay of competence scores toward 0.5 (forget old data)
_ENGAGEMENT_EMA_ALPHA = 0.12  # EMA for tracking user engagement signals


# ---------------------------------------------------------------------------
# SQLAlchemy models
# ---------------------------------------------------------------------------

class SkillAssessmentRow(Base):
    __tablename__ = "skill_assessments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    accuracy = Column(Float, default=0.5)
    helpfulness = Column(Float, default=0.5)
    depth = Column(Float, default=0.5)
    empathy = Column(Float, default=0.5)
    creativity = Column(Float, default=0.5)
    self_awareness = Column(Float, default=0.5)
    overall = Column(Float, default=0.5)
    insights = Column(Text, default="[]")  # JSON list of insight strings
    interaction_count = Column(Integer, default=0)


class CompetenceMapRow(Base):
    __tablename__ = "competence_map"

    domain = Column(String, primary_key=True)  # e.g. "technical", "emotional"
    score = Column(Float, default=0.5)         # [0, 1] competence level
    sample_count = Column(Integer, default=0)
    last_updated = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    strengths = Column(Text, default="[]")     # JSON list
    weaknesses = Column(Text, default="[]")    # JSON list


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class EngagementSignals:
    """Implicit feedback signals derived from user behaviour."""

    message_length: float = 0.5      # normalised user message length
    follow_up_depth: int = 0         # consecutive turns on same topic
    response_time_ms: int = 0        # how fast the user responded (lower = more engaged)
    asks_clarification: bool = False  # user asks for more detail
    topic_change: bool = False       # user changed topic (potentially bored)
    positive_markers: int = 0        # "thanks", "perfect", "great" etc.
    negative_markers: int = 0        # "no", "wrong", "not what I meant"


@dataclass
class SkillScores:
    """Multi-dimensional skill assessment."""

    accuracy: float = 0.5
    helpfulness: float = 0.5
    depth: float = 0.5
    empathy: float = 0.5
    creativity: float = 0.5
    self_awareness: float = 0.5
    overall: float = 0.5
    insights: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "accuracy": round(self.accuracy, 3),
            "helpfulness": round(self.helpfulness, 3),
            "depth": round(self.depth, 3),
            "empathy": round(self.empathy, 3),
            "creativity": round(self.creativity, 3),
            "self_awareness": round(self.self_awareness, 3),
            "overall": round(self.overall, 3),
            "insights": self.insights,
        }


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class SelfEvaluationEngine:
    """Tracks ECHO's performance and identifies areas for improvement."""

    def __init__(self) -> None:
        self._n: int = 0
        self._last_assessment_at: int = 0

        # Prediction error trend
        self._prediction_errors: deque[float] = deque(maxlen=_TREND_WINDOW)
        self._prediction_trend: float = 0.0  # negative = improving

        # User engagement tracking
        self._engagement_score: float = 0.5  # running EMA
        self._consecutive_topic_turns: int = 0
        self._last_topic: str = ""

        # Competence map (in-memory cache, persisted to SQLite)
        self._competence: dict[str, float] = {}
        self._competence_samples: dict[str, int] = {}

        # Recent interaction cache for assessment context
        self._recent_interactions: deque[dict[str, str]] = deque(maxlen=10)

        # Last assessment result
        self._last_assessment: SkillScores | None = None
        self._loaded = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        """Load competence map and last assessment from SQLite."""
        factory = get_session_factory()
        async with factory() as session:
            # Load competence map
            rows = (await session.execute(select(CompetenceMapRow))).scalars().all()
            for row in rows:
                self._competence[row.domain] = row.score
                self._competence_samples[row.domain] = row.sample_count

            # Load last assessment
            stmt = (
                select(SkillAssessmentRow)
                .order_by(SkillAssessmentRow.timestamp.desc())
                .limit(1)
            )
            last = (await session.execute(stmt)).scalar_one_or_none()
            if last:
                self._last_assessment = SkillScores(
                    accuracy=last.accuracy,
                    helpfulness=last.helpfulness,
                    depth=last.depth,
                    empathy=last.empathy,
                    creativity=last.creativity,
                    self_awareness=last.self_awareness,
                    overall=last.overall,
                    insights=json.loads(last.insights or "[]"),
                )
                self._n = last.interaction_count

        self._loaded = True
        logger.info(
            "SelfEvaluationEngine loaded: %d domains tracked, n=%d",
            len(self._competence),
            self._n,
        )

    # ------------------------------------------------------------------
    # Per-interaction observation
    # ------------------------------------------------------------------

    async def observe_interaction(
        self,
        user_input: str,
        response: str,
        prediction_error: float,
        interaction_type: str = "general",
        drive_scores: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Record one interaction and update all tracking metrics.

        Returns a dict with current evaluation state for pipeline trace.
        """
        self._n += 1

        # Track prediction error trend
        self._prediction_errors.append(prediction_error)
        if len(self._prediction_errors) >= 5:
            self._prediction_trend = self._compute_trend(
                list(self._prediction_errors)
            )

        # Detect engagement signals
        engagement = self._detect_engagement(user_input, response)
        self._engagement_score = (
            self._engagement_score * (1 - _ENGAGEMENT_EMA_ALPHA)
            + engagement * _ENGAGEMENT_EMA_ALPHA
        )

        # Update competence map for this interaction type
        # Lower prediction error + higher engagement = better competence
        competence_signal = (1.0 - prediction_error) * 0.6 + engagement * 0.4
        await self._update_competence(interaction_type, competence_signal)

        # Cache for assessment context
        self._recent_interactions.append({
            "user": user_input[:200],
            "echo": response[:200],
            "type": interaction_type,
            "error": str(round(prediction_error, 3)),
        })

        # Run full assessment periodically
        result: dict[str, Any] = {
            "prediction_trend": round(self._prediction_trend, 6),
            "engagement_score": round(self._engagement_score, 3),
            "interaction_count": self._n,
            "assessment_due": False,
        }

        if self._n - self._last_assessment_at >= _ASSESSMENT_INTERVAL:
            self._last_assessment_at = self._n
            result["assessment_due"] = True
            # Fire-and-forget — don't block pipeline
            import asyncio
            asyncio.create_task(self._run_assessment())

        return result

    # ------------------------------------------------------------------
    # Engagement detection (heuristic, no LLM)
    # ------------------------------------------------------------------

    def _detect_engagement(self, user_input: str, response: str) -> float:
        """Compute engagement score from implicit signals. Returns [0, 1]."""
        score = 0.5

        # Length signal: longer user messages = more engaged
        length_signal = min(1.0, len(user_input) / 300)
        score += (length_signal - 0.5) * 0.3

        # Positive markers
        _pos = {"grazie", "thanks", "perfect", "great", "ottimo", "fantastico",
                "esatto", "bravo", "exactly", "amazing", "helpful", "perfetto"}
        _neg = {"no", "wrong", "sbagliato", "non è", "that's not", "not what",
                "non intendevo", "non capisco"}

        lower_input = user_input.lower()
        pos_count = sum(1 for m in _pos if m in lower_input)
        neg_count = sum(1 for m in _neg if m in lower_input)

        score += pos_count * 0.1
        score -= neg_count * 0.15

        # Follow-up detection: very short responses often mean "go on"
        if len(user_input.strip()) < 20 and "?" not in user_input:
            # Could be acknowledgement or boredom
            if pos_count > 0:
                score += 0.1
            else:
                score -= 0.05

        # Question marks suggest engagement
        if user_input.count("?") >= 1:
            score += 0.05

        return max(0.0, min(1.0, score))

    # ------------------------------------------------------------------
    # Competence map
    # ------------------------------------------------------------------

    async def _update_competence(self, domain: str, signal: float) -> None:
        """Update competence score for a domain using EMA."""
        current = self._competence.get(domain, 0.5)
        count = self._competence_samples.get(domain, 0)

        # Adaptive alpha: fewer samples = faster convergence
        alpha = min(0.3, 0.15 / (1 + count * 0.01))
        new_score = current + alpha * (signal - current)

        # Apply slow decay toward 0.5 (forces re-earning of competence)
        new_score = new_score * _COMPETENCE_DECAY + 0.5 * (1 - _COMPETENCE_DECAY)

        self._competence[domain] = round(max(0.0, min(1.0, new_score)), 4)
        self._competence_samples[domain] = count + 1

        # Persist every 10 samples
        if (count + 1) % 10 == 0:
            await self._persist_competence(domain)

    async def _persist_competence(self, domain: str) -> None:
        """Save one competence domain to SQLite."""
        factory = get_session_factory()
        async with factory() as session:
            existing = await session.get(CompetenceMapRow, domain)
            if existing:
                existing.score = self._competence[domain]
                existing.sample_count = self._competence_samples[domain]
                existing.last_updated = datetime.now(timezone.utc).isoformat()
            else:
                row = CompetenceMapRow(
                    domain=domain,
                    score=self._competence[domain],
                    sample_count=self._competence_samples[domain],
                )
                session.add(row)
            await session.commit()

    # ------------------------------------------------------------------
    # Full skill assessment (LLM-based, periodic)
    # ------------------------------------------------------------------

    async def _run_assessment(self) -> None:
        """Run a comprehensive self-assessment using the LLM."""
        try:
            from echo.core.llm_client import llm  # noqa: PLC0415

            # Build context
            recent = list(self._recent_interactions)
            interactions_text = "\n".join(
                f"  [{r['type']}] User: {r['user'][:100]}\n"
                f"           ECHO: {r['echo'][:100]}\n"
                f"           (pred_error={r['error']})"
                for r in recent[-5:]
            )

            competence_text = "\n".join(
                f"  {domain}: {score:.3f} ({self._competence_samples.get(domain, 0)} samples)"
                for domain, score in sorted(
                    self._competence.items(),
                    key=lambda kv: kv[1],
                    reverse=True,
                )
            )

            prompt = f"""\
You are ECHO's self-evaluation system. Analyse recent performance and provide
an honest assessment across multiple dimensions.

Recent interactions ({len(recent)} total, showing last 5):
{interactions_text}

Prediction error trend: {self._prediction_trend:.6f} (negative = improving)
User engagement (EMA): {self._engagement_score:.3f}
Total interactions since last assessment: {_ASSESSMENT_INTERVAL}

Competence map:
{competence_text or "  (no data yet)"}

Rate each dimension 0.0-1.0 and provide 2-3 actionable insights.
Respond ONLY with valid JSON:
{{
  "accuracy": 0.7,
  "helpfulness": 0.8,
  "depth": 0.6,
  "empathy": 0.7,
  "creativity": 0.5,
  "self_awareness": 0.6,
  "overall": 0.65,
  "insights": ["insight1", "insight2"],
  "strengths": ["strength1"],
  "weaknesses": ["weakness1"]
}}"""

            raw = await llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300,
            )

            start = raw.find("{")
            end = raw.rfind("}") + 1
            data = json.loads(raw[start:end])

            scores = SkillScores(
                accuracy=float(data.get("accuracy", 0.5)),
                helpfulness=float(data.get("helpfulness", 0.5)),
                depth=float(data.get("depth", 0.5)),
                empathy=float(data.get("empathy", 0.5)),
                creativity=float(data.get("creativity", 0.5)),
                self_awareness=float(data.get("self_awareness", 0.5)),
                overall=float(data.get("overall", 0.5)),
                insights=data.get("insights", []),
            )
            self._last_assessment = scores

            # Persist
            await self._persist_assessment(scores)

            # Promote insights as identity beliefs
            await self._promote_insights(
                data.get("strengths", []),
                data.get("weaknesses", []),
            )

            logger.info(
                "Self-assessment complete: overall=%.3f accuracy=%.3f "
                "helpfulness=%.3f depth=%.3f empathy=%.3f",
                scores.overall,
                scores.accuracy,
                scores.helpfulness,
                scores.depth,
                scores.empathy,
            )

        except Exception as exc:  # noqa: BLE001
            logger.warning("Self-assessment failed: %s", exc)

    async def _persist_assessment(self, scores: SkillScores) -> None:
        """Save assessment to SQLite."""
        factory = get_session_factory()
        async with factory() as session:
            row = SkillAssessmentRow(
                id=str(uuid.uuid4()),
                accuracy=scores.accuracy,
                helpfulness=scores.helpfulness,
                depth=scores.depth,
                empathy=scores.empathy,
                creativity=scores.creativity,
                self_awareness=scores.self_awareness,
                overall=scores.overall,
                insights=json.dumps(scores.insights),
                interaction_count=self._n,
            )
            session.add(row)
            await session.commit()

    async def _promote_insights(
        self,
        strengths: list[str],
        weaknesses: list[str],
    ) -> None:
        """Store strengths/weaknesses as semantic memories for future reference."""
        try:
            from echo.memory.semantic import SemanticMemoryStore  # noqa: PLC0415

            semantic = SemanticMemoryStore()
            now = datetime.now(timezone.utc).isoformat()

            if strengths:
                content = (
                    f"[Self-Assessment {now[:10]}] Strengths: "
                    + "; ".join(s[:100] for s in strengths[:3])
                )
                await semantic.store(
                    content=content,
                    tags=["self_assessment", "strengths"],
                    salience=0.7,
                )

            if weaknesses:
                content = (
                    f"[Self-Assessment {now[:10]}] Areas to improve: "
                    + "; ".join(w[:100] for w in weaknesses[:3])
                )
                await semantic.store(
                    content=content,
                    tags=["self_assessment", "weaknesses", "growth"],
                    salience=0.75,
                )

        except Exception as exc:  # noqa: BLE001
            logger.debug("Insight promotion failed: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def prediction_trend(self) -> float:
        """Current prediction error trend. Negative = improving."""
        return self._prediction_trend

    @property
    def engagement_score(self) -> float:
        """Running EMA of user engagement."""
        return self._engagement_score

    @property
    def competence_map(self) -> dict[str, float]:
        """Current competence scores by domain."""
        return dict(self._competence)

    @property
    def last_assessment(self) -> SkillScores | None:
        """Most recent full skill assessment."""
        return self._last_assessment

    async def get_assessment_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return recent assessment history from SQLite."""
        factory = get_session_factory()
        async with factory() as session:
            stmt = (
                select(SkillAssessmentRow)
                .order_by(SkillAssessmentRow.timestamp.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
        return [
            {
                "timestamp": r.timestamp,
                "overall": r.overall,
                "accuracy": r.accuracy,
                "helpfulness": r.helpfulness,
                "depth": r.depth,
                "empathy": r.empathy,
                "creativity": r.creativity,
                "self_awareness": r.self_awareness,
                "insights": json.loads(r.insights or "[]"),
                "interaction_count": r.interaction_count,
            }
            for r in rows
        ]

    def status_summary(self) -> dict[str, Any]:
        """Return a compact status dict for pipeline trace / API."""
        return {
            "interaction_count": self._n,
            "prediction_trend": round(self._prediction_trend, 6),
            "engagement_score": round(self._engagement_score, 3),
            "competence_map": {k: round(v, 3) for k, v in self._competence.items()},
            "last_assessment": self._last_assessment.to_dict() if self._last_assessment else None,
            "next_assessment_in": max(0, _ASSESSMENT_INTERVAL - (self._n - self._last_assessment_at)),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_trend(values: list[float]) -> float:
        """Linear regression slope."""
        n = len(values)
        if n < 3:
            return 0.0
        xs = list(range(n))
        mx = sum(xs) / n
        my = sum(values) / n
        num = sum((x - mx) * (y - my) for x, y in zip(xs, values, strict=False))
        den = sum((x - mx) ** 2 for x in xs)
        return num / den if den != 0 else 0.0


# Module-level singleton
self_evaluation = SelfEvaluationEngine()
