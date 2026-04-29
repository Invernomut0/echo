"""Meta-state tracker — drives, emotional valence, agent routing weights."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, select

from echo.core.db import Base, get_session_factory
from echo.core.types import DriveScores, MetaState

logger = logging.getLogger(__name__)


class MetaStateRow(Base):
    __tablename__ = "meta_states"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    state_json = Column(Text, nullable=False)
    timestamp = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())


class MetaStateTracker:
    """Maintains the current meta-state and a time-series history."""

    def __init__(self) -> None:
        self._current: MetaState = MetaState()

    @property
    def current(self) -> MetaState:
        return self._current

    async def load_latest(self) -> None:
        """Restore last-saved state from SQLite."""
        factory = get_session_factory()
        async with factory() as session:
            stmt = (
                select(MetaStateRow)
                .order_by(MetaStateRow.timestamp.desc())
                .limit(1)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
        if row:
            self._current = MetaState.model_validate_json(row.state_json)
            logger.info("MetaState restored from DB")

    async def save(self) -> None:
        """Persist current state to SQLite (append-only time series)."""
        factory = get_session_factory()
        async with factory() as session:
            row = MetaStateRow(
                id=str(uuid.uuid4()),
                state_json=self._current.model_dump_json(),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            session.add(row)
            await session.commit()

    def update_drives(self, adjustments: dict[str, float]) -> MetaState:
        """Apply delta adjustments to drive scores (clamped 0–1).

        Also performs Hebbian-style weight adaptation:
        drives highly active during competence growth get their weight (w_i in
        M = Σ w_i · d_i) increased, so the motivation formula self-tunes over time.
        """
        d = self._current.drives
        competence_before = d.competence

        for key, delta in adjustments.items():
            if hasattr(d, key):
                current_val = getattr(d, key)
                setattr(d, key, max(0.0, min(1.0, current_val + delta)))

        # IM-6: Hebbian weight evolution — drives active during competence gains grow stronger
        competence_delta = d.competence - competence_before
        if abs(competence_delta) > 0.01 and d.weights:
            _WEIGHT_LR = 0.004
            for drive_name in ("curiosity", "coherence", "compression"):
                drive_val = getattr(d, drive_name, 0.5)
                if competence_delta > 0 and drive_val > 0.6:
                    # Drive was active and competence improved → strengthen its weight
                    d.weights[drive_name] = min(0.40, d.weights.get(drive_name, 0.2) + _WEIGHT_LR)
                elif competence_delta < 0 and drive_val > 0.6:
                    # Drive was active but competence fell → slightly weaken its weight
                    d.weights[drive_name] = max(0.05, d.weights.get(drive_name, 0.2) - _WEIGHT_LR * 0.5)
            # Re-normalise weights so they always sum to 1.0
            total = sum(d.weights.values())
            if total > 0:
                for k in d.weights:
                    d.weights[k] = round(d.weights[k] / total, 6)

        self._current.timestamp = datetime.now(timezone.utc)
        return self._current

    def update_agent_weight(self, agent: str, delta: float) -> None:
        """Adjust routing weight for an agent (clamped 0.1–2.0)."""
        current = self._current.agent_weights.get(agent, 1.0)
        self._current.agent_weights[agent] = max(0.1, min(2.0, current + delta))

    def update_valence(self, delta: float) -> None:
        self._current.emotional_valence = max(
            -1.0, min(1.0, self._current.emotional_valence + delta)
        )

    def update_arousal(self, delta: float) -> None:
        """Adjust arousal level — clamped to [0, 1].

        Arousal encodes alertness/activation (0 = deeply calm, 1 = hyperactivated).
        It rises with prediction error (surprise) and mean drive activation.
        """
        self._current.arousal = max(0.0, min(1.0, self._current.arousal + delta))

    async def get_history(self, limit: int = 100) -> list[MetaState]:
        factory = get_session_factory()
        async with factory() as session:
            stmt = (
                select(MetaStateRow)
                .order_by(MetaStateRow.timestamp.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
        return [MetaState.model_validate_json(r.state_json) for r in reversed(rows)]
