"""Personalization state — learns user interaction preferences over time.

Accumulates per-session statistics and adapts style dimensions via EMA:

    verbosity           – preferred response length (0 = terse, 1 = verbose)
    topic_depth         – preferred explanatory depth (0 = shallow, 1 = deep)
    recall_frequency    – proactive memory surfacing rate (0 = low, 1 = high)
    drive_baselines     – long-run drive score baselines inferred from history

The state is persisted in a dedicated SQLite table (``personalization_state``)
and survives across sessions.  A new row is appended every ``_SAVE_INTERVAL``
interactions so the table also acts as a time-series audit log.

Design constraints (module 16):
    - Personalisation MUST NOT override identity — it modulates *style*, not self.
    - EMA alpha is intentionally slow (0.08) to prevent rapid style drift from a
      single atypical interaction.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, select

from echo.core.db import Base, get_session_factory

logger = logging.getLogger(__name__)

# Slow EMA — one unusual interaction should not flip the entire style model.
_EMA_ALPHA = 0.08


# ---------------------------------------------------------------------------
# ORM row
# ---------------------------------------------------------------------------

class PersonalizationRow(Base):
    __tablename__ = "personalization_state"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    state_json = Column(Text, nullable=False)
    timestamp = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# State object
# ---------------------------------------------------------------------------

class PersonalizationState:
    """Mutable struct that holds user-specific style preferences.

    All dimensions live in [0, 1].  ``drive_baselines`` contains *delta* shifts
    from the default 0.5 baseline and is keyed by drive name
    (curiosity, coherence, etc.).
    """

    def __init__(self) -> None:
        # Style dimensions
        self.verbosity: float = 0.5           # 0 = terse, 1 = verbose
        self.topic_depth: float = 0.5         # 0 = shallow, 1 = deep
        self.recall_frequency: float = 0.5    # proactive memory surfacing rate

        # Long-run drive score baselines (drive_name → learned average)
        self.drive_baselines: dict[str, float] = {}

        # Interaction counter — used for save throttling and logging
        self._n: int = 0

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(
        self,
        response_length: int,
        *,
        novelty_score: float,
        user_engagement: float,
        curiosity: float,
        coherence: float,
    ) -> None:
        """Apply one EMA step from an observed interaction.

        Args:
            response_length:  character count of ECHO's response.
            novelty_score:    novelty drive score [0, 1] from motivational scorer.
            user_engagement:  estimated engagement proxy (user turn length, normalised).
            curiosity:        curiosity drive score [0, 1].
            coherence:        coherence drive score [0, 1].
        """
        self._n += 1
        a = _EMA_ALPHA

        # Verbosity: long responses that correlate with high engagement signal that
        # this user values detailed answers.
        verbosity_signal = min(1.0, response_length / 600)  # normalise at ~600 chars
        self.verbosity = _ema(self.verbosity, verbosity_signal * user_engagement, a)

        # Topic depth: high novelty + high curiosity together indicate the user
        # actively explored a complex topic → they prefer depth.
        depth_signal = 0.5 * novelty_score + 0.5 * curiosity
        self.topic_depth = _ema(self.topic_depth, depth_signal, a)

        # Recall frequency: users with high coherence drives tend to appreciate
        # cross-referencing past context.
        recall_signal = 0.4 * coherence + 0.6 * self.recall_frequency
        self.recall_frequency = _ema(self.recall_frequency, recall_signal, a)

        # Drive baselines: slow drift toward long-run observed drive values.
        for drive, val in [("curiosity", curiosity), ("coherence", coherence)]:
            current = self.drive_baselines.get(drive, 0.5)
            self.drive_baselines[drive] = round(
                _ema(current, val, a * 0.5), 4  # extra-slow for baselines
            )

        logger.debug(
            "Personalization n=%d  verbosity=%.3f  depth=%.3f  recall=%.3f",
            self._n, self.verbosity, self.topic_depth, self.recall_frequency,
        )

    # ------------------------------------------------------------------
    # Style hint generation
    # ------------------------------------------------------------------

    def style_hint(self) -> str:
        """One-line style instruction derived from learnt preferences.

        Appended to the synthesis prompt so agents reflect the user's preferred
        communication style without altering identity.
        """
        parts: list[str] = []

        if self.verbosity < 0.35:
            parts.append("Be concise — this user prefers short, direct answers.")
        elif self.verbosity > 0.65:
            parts.append("Be thorough — this user appreciates detailed responses.")

        if self.topic_depth < 0.35:
            parts.append("Keep explanations high-level; avoid deep technical detail.")
        elif self.topic_depth > 0.65:
            parts.append("Go deep — this user engages with technical and nuanced content.")

        if self.recall_frequency > 0.65:
            parts.append(
                "Proactively surface relevant past context if it adds value."
            )

        if not parts:
            return ""  # neutral — no hint needed

        return "PERSONALISATION HINT: " + " ".join(parts)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "verbosity": round(self.verbosity, 4),
            "topic_depth": round(self.topic_depth, 4),
            "recall_frequency": round(self.recall_frequency, 4),
            "drive_baselines": self.drive_baselines,
            "_n": self._n,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PersonalizationState":
        obj = cls()
        obj.verbosity = data.get("verbosity", 0.5)
        obj.topic_depth = data.get("topic_depth", 0.5)
        obj.recall_frequency = data.get("recall_frequency", 0.5)
        obj.drive_baselines = data.get("drive_baselines", {})
        obj._n = data.get("_n", 0)
        return obj

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def load(self) -> None:
        """Restore the most recent persisted state from SQLite."""
        factory = get_session_factory()
        async with factory() as session:
            stmt = (
                select(PersonalizationRow)
                .order_by(PersonalizationRow.timestamp.desc())
                .limit(1)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()

        if row:
            restored = PersonalizationState.from_dict(json.loads(row.state_json))
            self.verbosity = restored.verbosity
            self.topic_depth = restored.topic_depth
            self.recall_frequency = restored.recall_frequency
            self.drive_baselines = restored.drive_baselines
            self._n = restored._n
            logger.info("PersonalizationState restored (n=%d)", self._n)

    async def save(self) -> None:
        """Persist current state as a new time-series row in SQLite."""
        factory = get_session_factory()
        async with factory() as session:
            row = PersonalizationRow(
                id=str(uuid.uuid4()),
                state_json=json.dumps(self.to_dict()),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            session.add(row)
            await session.commit()
        logger.debug("PersonalizationState saved (n=%d)", self._n)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ema(current: float, target: float, alpha: float) -> float:
    """Exponential moving average, clamped to [0, 1]."""
    return max(0.0, min(1.0, current + alpha * (target - current)))
