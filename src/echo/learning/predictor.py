"""Predictive Analytics Engine — lightweight EWMA-based forecasting.

Predicts four cognitive signals one step ahead from a rolling observation window:

    emotional_valence_forecast  – expected next emotional valence [-1, 1]
    curiosity_spike_prob        – probability of a curiosity spike [0, 1]
    identity_drift_risk         – risk of identity drift this cycle [0, 1]
    consolidation_urgency       – how urgently consolidation is needed [0, 1]

All arithmetic is pure Python float — no external ML framework required.
Inference budget: < 0.5 ms per ``predict()`` call (well within the 20 ms target).

Hot-swap: call ``reset()`` to return to initial state without restarting the system.
Predictions are logged as cognitive events by ``LearningEngine.observe()``.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_WINDOW = 20       # maximum observations kept in the rolling windows
_EMA_ALPHA = 0.20  # prediction EMA — faster than personalisation (detects trends sooner)


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class PredictionPriors:
    """Prediction outputs fed as priors into the Global Workspace competition.

    These are not hard overrides — they are low-to-medium salience workspace items
    that inform agents without forcing any particular behaviour.
    """

    emotional_valence_forecast: float   # expected next valence [-1, 1]
    curiosity_spike_prob: float          # [0, 1]
    identity_drift_risk: float           # [0, 1]
    consolidation_urgency: float         # [0, 1]

    # Threshold at which a signal is considered actionable
    _CURIOSITY_THRESHOLD: float = field(default=0.65, repr=False, compare=False)
    _DRIFT_THRESHOLD: float = field(default=0.55, repr=False, compare=False)
    _URGENCY_THRESHOLD: float = field(default=0.70, repr=False, compare=False)
    _VALENCE_THRESHOLD: float = field(default=0.35, repr=False, compare=False)

    def workspace_items(self) -> list[tuple[str, float]]:
        """Return (content, salience) pairs ready for ``GlobalWorkspace.broadcast()``.

        Only signals that exceed their actionable threshold produce workspace items —
        this prevents noise from flooding the workspace with low-signal predictions.
        """
        items: list[tuple[str, float]] = []

        if self.curiosity_spike_prob > self._CURIOSITY_THRESHOLD:
            sal = round(0.55 + 0.20 * self.curiosity_spike_prob, 3)
            items.append((
                f"[Prediction] Curiosity spike likely "
                f"(p={self.curiosity_spike_prob:.2f}) — "
                "Explorer weighting elevated for this turn.",
                sal,
            ))

        if self.identity_drift_risk > self._DRIFT_THRESHOLD:
            sal = round(0.55 + 0.15 * self.identity_drift_risk, 3)
            items.append((
                f"[Prediction] Identity drift risk elevated "
                f"({self.identity_drift_risk:.2f}) — "
                "Archivist grounding recommended.",
                sal,
            ))

        if self.consolidation_urgency > self._URGENCY_THRESHOLD:
            sal = round(0.50 + 0.10 * self.consolidation_urgency, 3)
            items.append((
                f"[Prediction] Memory consolidation urgency high "
                f"({self.consolidation_urgency:.2f}) — "
                "light-sleep cycle may be beneficial soon.",
                sal,
            ))

        if abs(self.emotional_valence_forecast) > self._VALENCE_THRESHOLD:
            direction = "positive" if self.emotional_valence_forecast > 0 else "negative"
            items.append((
                f"[Prediction] Emotional valence trending {direction} "
                f"({self.emotional_valence_forecast:+.2f}) — "
                "affective modulation active.",
                0.45,
            ))

        return items

    def is_notable(self) -> bool:
        """True if any signal crosses its actionable threshold."""
        return bool(self.workspace_items())


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class PredictiveAnalyticsEngine:
    """Online EWMA predictor — no ML framework, no disk state, hot-swappable.

    ``observe()`` is O(1) and called after every interaction.
    ``predict()`` is O(n) in the window size (constant 20 elements) — << 1 ms.
    """

    def __init__(self) -> None:
        # Rolling windows (most recent ``_WINDOW`` observations)
        self._valence: deque[float] = deque(maxlen=_WINDOW)
        self._curiosity: deque[float] = deque(maxlen=_WINDOW)
        self._drift: deque[float] = deque(maxlen=_WINDOW)
        self._memory_load: deque[float] = deque(maxlen=_WINDOW)

        # EMA accumulators (smooth estimates of current level)
        self._ema_valence: float = 0.0
        self._ema_curiosity: float = 0.5
        self._ema_drift: float = 0.0
        self._ema_load: float = 0.5

        self._n: int = 0

    # ------------------------------------------------------------------
    # Feed observation
    # ------------------------------------------------------------------

    def observe(
        self,
        *,
        emotional_valence: float,
        curiosity: float,
        identity_drift: float,
        memory_load: float,
    ) -> None:
        """Ingest one observation from a completed interaction.

        All parameters are expected in their natural ranges:
            emotional_valence  – [-1, 1]
            curiosity          – [0, 1]
            identity_drift     – [0, 1]  (cosine distance from previous weights)
            memory_load        – [0, 1]  (normalised memory count)
        """
        self._n += 1
        a = _EMA_ALPHA

        self._valence.append(emotional_valence)
        self._curiosity.append(curiosity)
        self._drift.append(identity_drift)
        self._memory_load.append(memory_load)

        self._ema_valence   += a * (emotional_valence - self._ema_valence)
        self._ema_curiosity += a * (curiosity         - self._ema_curiosity)
        self._ema_drift     += a * (identity_drift    - self._ema_drift)
        self._ema_load      += a * (memory_load       - self._ema_load)

    # ------------------------------------------------------------------
    # Predict
    # ------------------------------------------------------------------

    def predict(self) -> PredictionPriors:
        """Return prediction priors derived from current EMA state.

        Always returns a valid ``PredictionPriors`` even with no observations.
        Pure read — does NOT mutate any state.
        """
        if self._n == 0:
            return PredictionPriors(
                emotional_valence_forecast=0.0,
                curiosity_spike_prob=0.5,
                identity_drift_risk=0.0,
                consolidation_urgency=0.5,
            )

        # Valence forecast: linear extrapolation one step ahead from recent window.
        valence_forecast = _linear_extrapolate(list(self._valence))

        # Curiosity spike probability: EMA level + amplified positive velocity.
        c_velocity = _velocity(self._curiosity)
        spike_prob = self._ema_curiosity + 1.5 * max(0.0, c_velocity)

        # Identity drift risk: scale up EMA so small but consistent drift registers.
        # A drift EMA of 0.10 (10 % cosine distance per step) maps to ~0.30 risk.
        drift_risk = self._ema_drift * 3.0

        # Consolidation urgency: high load + low drift → stable enough to consolidate.
        urgency = self._ema_load * 0.7 + (1.0 - min(1.0, drift_risk)) * 0.3

        priors = PredictionPriors(
            emotional_valence_forecast=round(_clamp(valence_forecast, -1.0, 1.0), 3),
            curiosity_spike_prob=round(_clamp(spike_prob, 0.0, 1.0), 3),
            identity_drift_risk=round(_clamp(drift_risk, 0.0, 1.0), 3),
            consolidation_urgency=round(_clamp(urgency, 0.0, 1.0), 3),
        )
        logger.debug("PredictionPriors: %s", priors)
        return priors

    # ------------------------------------------------------------------
    # Hot-swap reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all rolling history — hot-swappable without system restart."""
        self.__init__()
        logger.info("PredictiveAnalyticsEngine reset")


# ---------------------------------------------------------------------------
# Pure-Python math helpers
# ---------------------------------------------------------------------------

def _velocity(window: deque[float]) -> float:
    """Average first-difference over the rolling window."""
    items = list(window)
    if len(items) < 2:
        return 0.0
    diffs = [items[i] - items[i - 1] for i in range(1, len(items))]
    return sum(diffs) / len(diffs)


def _linear_extrapolate(values: list[float]) -> float:
    """OLS linear regression → extrapolate one step ahead (pure Python)."""
    n = len(values)
    if n == 0:
        return 0.0
    if n == 1:
        return values[0]

    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(values) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, values))
    den = sum((x - mx) ** 2 for x in xs)
    slope = num / den if den != 0.0 else 0.0
    return my + slope * (n - mx)


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))
