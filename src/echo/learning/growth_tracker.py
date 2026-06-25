"""Growth Tracker — measures ECHO's improvement over time.

Maintains rolling statistics and computes a composite growth score.
When growth stagnates, triggers a "shake-up" to break out of local optima.

Components:
    - Rolling averages (window=100): prediction error, engagement, drive stability
    - Growth score: composite metric of improvement velocity
    - Shake-up trigger: boost curiosity + generate self-improvement goals when stagnant
    - Growth report: periodic summary stored as semantic memory

Integration:
    Called from LearningEngine.observe() after each interaction.
    Growth reports generated during deep-sleep consolidation.
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

_WINDOW_SIZE = 100            # rolling window for statistics
_STAGNATION_THRESHOLD = 200   # interactions without growth → shake-up
_GROWTH_REPORT_INTERVAL = 100 # generate report every N interactions
_MIN_OBSERVATIONS = 20        # minimum before computing growth score


# ---------------------------------------------------------------------------
# SQLAlchemy model
# ---------------------------------------------------------------------------

class GrowthReportRow(Base):
    __tablename__ = "growth_reports"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    interaction_count = Column(Integer, default=0)
    growth_score = Column(Float, default=0.0)
    prediction_error_avg = Column(Float, default=0.5)
    prediction_error_trend = Column(Float, default=0.0)
    engagement_avg = Column(Float, default=0.5)
    drive_stability = Column(Float, default=0.5)
    shake_up_triggered = Column(String, default="false")
    report_text = Column(Text, default="")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class GrowthMetrics:
    """Current growth state."""
    growth_score: float = 0.0           # composite [-1, 1]: positive = growing
    prediction_error_avg: float = 0.5
    prediction_error_trend: float = 0.0  # negative = improving
    engagement_avg: float = 0.5
    engagement_trend: float = 0.0        # positive = more engaged
    drive_stability: float = 0.5         # low volatility = stable
    interactions_since_growth: int = 0   # counter for stagnation detection
    is_growing: bool = False
    is_stagnant: bool = False
    shake_up_needed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "growth_score": round(self.growth_score, 4),
            "prediction_error_avg": round(self.prediction_error_avg, 4),
            "prediction_error_trend": round(self.prediction_error_trend, 6),
            "engagement_avg": round(self.engagement_avg, 4),
            "engagement_trend": round(self.engagement_trend, 6),
            "drive_stability": round(self.drive_stability, 4),
            "interactions_since_growth": self.interactions_since_growth,
            "is_growing": self.is_growing,
            "is_stagnant": self.is_stagnant,
            "shake_up_needed": self.shake_up_needed,
        }


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class GrowthTracker:
    """Tracks ECHO's long-term improvement trajectory."""

    def __init__(self) -> None:
        self._n: int = 0
        self._last_report_at: int = 0
        self._last_shake_up_at: int = 0

        # Rolling windows
        self._prediction_errors: deque[float] = deque(maxlen=_WINDOW_SIZE)
        self._engagements: deque[float] = deque(maxlen=_WINDOW_SIZE)
        self._drive_variances: deque[float] = deque(maxlen=_WINDOW_SIZE)
        self._response_lengths: deque[int] = deque(maxlen=_WINDOW_SIZE)

        # Growth tracking
        self._growth_history: deque[float] = deque(maxlen=50)  # recent growth scores
        self._interactions_since_improvement: int = 0
        self._best_error_avg: float = 1.0  # best prediction error average seen

        # Cached metrics
        self._metrics: GrowthMetrics = GrowthMetrics()

    # ------------------------------------------------------------------
    # Per-interaction observation
    # ------------------------------------------------------------------

    def observe(
        self,
        prediction_error: float,
        engagement: float,
        drive_scores: dict[str, float],
        response_length: int = 0,
    ) -> GrowthMetrics:
        """Record one observation and recompute growth metrics.

        Called from LearningEngine.observe() after each interaction.
        Returns updated metrics for pipeline trace.
        """
        self._n += 1

        self._prediction_errors.append(prediction_error)
        self._engagements.append(engagement)
        self._response_lengths.append(response_length)

        # Drive stability: variance across the 5 drive scores this turn
        if drive_scores:
            values = list(drive_scores.values())
            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / len(values)
            self._drive_variances.append(variance)

        # Recompute metrics
        self._recompute()

        return self._metrics

    # ------------------------------------------------------------------
    # Metrics computation
    # ------------------------------------------------------------------

    def _recompute(self) -> None:
        """Recompute all growth metrics from rolling windows."""
        n = len(self._prediction_errors)
        if n < _MIN_OBSERVATIONS:
            self._metrics = GrowthMetrics(interactions_since_growth=self._n)
            return

        errors = list(self._prediction_errors)
        engagements = list(self._engagements)

        # Averages
        error_avg = sum(errors) / len(errors)
        engagement_avg = sum(engagements) / len(engagements)

        # Trends (linear regression slopes)
        error_trend = self._slope(errors)
        engagement_trend = self._slope(engagements)

        # Drive stability: 1 - mean variance (lower variance = more stable)
        drive_stability = 0.5
        if self._drive_variances:
            mean_var = sum(self._drive_variances) / len(self._drive_variances)
            drive_stability = max(0.0, min(1.0, 1.0 - mean_var * 4))

        # Composite growth score:
        # - Negative error trend (improving) → positive growth
        # - Positive engagement trend → positive growth
        # - High drive stability → stable foundation for growth
        growth_score = (
            -error_trend * 20        # weight error improvement heavily
            + engagement_trend * 10   # engagement improvement
            + (drive_stability - 0.5) * 0.5  # stability bonus
        )
        growth_score = max(-1.0, min(1.0, growth_score))

        # Track if we're actually improving
        is_growing = growth_score > 0.05 and error_trend < -0.0005
        is_stagnant = abs(growth_score) < 0.02 and n >= 50

        # Track time since last improvement
        if error_avg < self._best_error_avg * 0.95:
            self._best_error_avg = error_avg
            self._interactions_since_improvement = 0
        else:
            self._interactions_since_improvement += 1

        # Shake-up detection
        shake_up_needed = (
            self._interactions_since_improvement >= _STAGNATION_THRESHOLD
            and (self._n - self._last_shake_up_at) > _STAGNATION_THRESHOLD
        )

        self._metrics = GrowthMetrics(
            growth_score=growth_score,
            prediction_error_avg=error_avg,
            prediction_error_trend=error_trend,
            engagement_avg=engagement_avg,
            engagement_trend=engagement_trend,
            drive_stability=drive_stability,
            interactions_since_growth=self._interactions_since_improvement,
            is_growing=is_growing,
            is_stagnant=is_stagnant,
            shake_up_needed=shake_up_needed,
        )

        self._growth_history.append(growth_score)

    # ------------------------------------------------------------------
    # Shake-up: break out of stagnation
    # ------------------------------------------------------------------

    async def trigger_shake_up(self) -> dict[str, Any]:
        """Trigger a shake-up when growth has stagnated.

        Actions:
        1. Boost curiosity drive by 0.2
        2. Create a self-improvement goal
        3. Reset stagnation counter
        4. Log the event

        Returns dict describing what was done.
        """
        self._last_shake_up_at = self._n
        self._interactions_since_improvement = 0

        actions_taken: list[str] = []

        # 1. Boost curiosity
        try:
            from echo.core.pipeline import pipeline  # noqa: PLC0415
            if pipeline._ready:
                pipeline.meta_tracker.update_drives({"curiosity": 0.2, "stability": -0.1})
                actions_taken.append("Boosted curiosity +0.2, reduced stability -0.1")
        except Exception:  # noqa: BLE001
            pass

        # 2. Create self-improvement goal
        try:
            from echo.memory.goals import goal_store  # noqa: PLC0415
            goal = await goal_store.create(
                title="Break out of learning stagnation",
                description=(
                    f"Growth has stagnated for {_STAGNATION_THRESHOLD}+ interactions. "
                    f"Current prediction error avg: {self._metrics.prediction_error_avg:.3f}. "
                    "Try new approaches: explore unfamiliar topics, change response patterns, "
                    "or seek challenging interactions."
                ),
                priority=0.85,
                tags=["auto_growth", "shake_up"],
            )
            actions_taken.append(f"Created goal: {goal['title']}")
        except (ValueError, Exception) as exc:  # noqa: BLE001
            logger.debug("Shake-up goal creation failed: %s", exc)

        # 3. Store as semantic memory
        try:
            from echo.memory.semantic import SemanticMemoryStore  # noqa: PLC0415
            semantic = SemanticMemoryStore()
            await semantic.store(
                content=(
                    f"[Growth Shake-up] Triggered after {self._interactions_since_improvement} "
                    f"interactions without improvement. "
                    f"Error avg: {self._metrics.prediction_error_avg:.3f}, "
                    f"Engagement: {self._metrics.engagement_avg:.3f}. "
                    f"Actions: {'; '.join(actions_taken)}"
                ),
                tags=["growth", "shake_up", "meta_learning"],
                salience=0.8,
            )
        except Exception:  # noqa: BLE001
            pass

        logger.info(
            "GROWTH SHAKE-UP triggered (stagnant for %d interactions): %s",
            _STAGNATION_THRESHOLD,
            actions_taken,
        )

        return {
            "triggered": True,
            "interaction_count": self._n,
            "actions": actions_taken,
            "metrics": self._metrics.to_dict(),
        }

    # ------------------------------------------------------------------
    # Growth report (called during deep-sleep)
    # ------------------------------------------------------------------

    async def generate_report(self) -> dict[str, Any] | None:
        """Generate a growth report and store it.

        Called during deep-sleep consolidation. Returns the report dict or None.
        """
        if self._n < _MIN_OBSERVATIONS:
            return None

        if self._n - self._last_report_at < _GROWTH_REPORT_INTERVAL:
            return None

        self._last_report_at = self._n
        metrics = self._metrics

        # Build report text
        growth_dir = "improving" if metrics.is_growing else "stagnant" if metrics.is_stagnant else "stable"
        report_text = (
            f"[Growth Report — Interaction #{self._n}]\n"
            f"Overall trajectory: {growth_dir} (score: {metrics.growth_score:.4f})\n"
            f"Prediction error: avg={metrics.prediction_error_avg:.3f}, "
            f"trend={metrics.prediction_error_trend:.6f}\n"
            f"User engagement: avg={metrics.engagement_avg:.3f}, "
            f"trend={metrics.engagement_trend:.6f}\n"
            f"Drive stability: {metrics.drive_stability:.3f}\n"
            f"Interactions since last improvement: {metrics.interactions_since_growth}"
        )

        # Persist to SQLite
        factory = get_session_factory()
        async with factory() as session:
            row = GrowthReportRow(
                id=str(uuid.uuid4()),
                interaction_count=self._n,
                growth_score=metrics.growth_score,
                prediction_error_avg=metrics.prediction_error_avg,
                prediction_error_trend=metrics.prediction_error_trend,
                engagement_avg=metrics.engagement_avg,
                drive_stability=metrics.drive_stability,
                shake_up_triggered="true" if metrics.shake_up_needed else "false",
                report_text=report_text,
            )
            session.add(row)
            await session.commit()

        # Store as semantic memory
        try:
            from echo.memory.semantic import SemanticMemoryStore  # noqa: PLC0415
            semantic = SemanticMemoryStore()
            await semantic.store(
                content=report_text,
                tags=["growth_report", "meta_learning"],
                salience=0.65,
            )
        except Exception:  # noqa: BLE001
            pass

        logger.info("Growth report generated: %s (score=%.4f)", growth_dir, metrics.growth_score)
        return {"report": report_text, "metrics": metrics.to_dict()}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def metrics(self) -> GrowthMetrics:
        return self._metrics

    @property
    def interaction_count(self) -> int:
        return self._n

    async def get_report_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return recent growth reports from SQLite."""
        factory = get_session_factory()
        async with factory() as session:
            stmt = (
                select(GrowthReportRow)
                .order_by(GrowthReportRow.timestamp.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
        return [
            {
                "timestamp": r.timestamp,
                "interaction_count": r.interaction_count,
                "growth_score": r.growth_score,
                "prediction_error_avg": r.prediction_error_avg,
                "engagement_avg": r.engagement_avg,
                "drive_stability": r.drive_stability,
                "report_text": r.report_text,
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _slope(values: list[float]) -> float:
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
growth_tracker = GrowthTracker()
