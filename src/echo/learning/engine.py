"""Learning Engine — top-level coordinator for module 16.

Orchestrates:
    - ``PersonalizationState``  (slow EMA style adaptation + SQLite persistence)
    - ``PredictiveAnalyticsEngine``  (fast EWMA prediction priors)

Integration contract with ``CognitivePipeline``:
    1.  ``await engine.startup()``          — call once at system startup.
    2.  ``await engine.observe(...)``       — call inside ``_post_interact`` after
                                              motivational scoring is complete.
    3.  ``engine.get_priors()``             — call before workspace loading to inject
                                              prediction priors into the workspace.
    4.  ``engine.personalization``          — read ``style_hint()`` to get the
                                              personalisation note for the prompt.

Design constraints (module 16):
    - Personalization modulates *style*, never *identity*.
    - Predictions are workspace priors, not hard overrides.
    - Persistence survives across sessions (SQLite ``personalization_state`` table).
    - Predictor is hot-swappable via ``reset_predictor()`` without system restart.
"""

from __future__ import annotations

import logging

from echo.core.event_bus import bus
from echo.core.types import CognitiveEvent, EventTopic
from echo.learning.personalization import PersonalizationState
from echo.learning.predictor import PredictiveAnalyticsEngine, PredictionPriors

logger = logging.getLogger(__name__)

# Persist personalization every N interactions to limit DB write frequency.
_SAVE_INTERVAL = 5


class LearningEngine:
    """Coordinates personalization and predictive analytics (module 16).

    This class is the single integration point for the pipeline.  All internal
    details (EMA logic, SQLite rows, prediction arithmetic) are encapsulated in
    ``PersonalizationState`` and ``PredictiveAnalyticsEngine`` respectively.
    """

    def __init__(self) -> None:
        self.personalization: PersonalizationState = PersonalizationState()
        self.predictor: PredictiveAnalyticsEngine = PredictiveAnalyticsEngine()
        self._n: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        """Load persisted personalization state from SQLite."""
        await self.personalization.load()
        logger.info(
            "LearningEngine ready — personalization n=%d  verbosity=%.3f  depth=%.3f",
            self.personalization._n,
            self.personalization.verbosity,
            self.personalization.topic_depth,
        )

    # ------------------------------------------------------------------
    # Post-interaction update
    # ------------------------------------------------------------------

    async def observe(
        self,
        *,
        response: str,
        user_input: str,
        novelty_score: float,
        curiosity: float,
        coherence: float,
        emotional_valence: float,
        identity_drift: float,
        memory_count: int,
    ) -> PredictionPriors:
        """Update personalization + predictor from a completed interaction.

        Returns the freshly computed ``PredictionPriors`` so the pipeline can
        publish them as a cognitive event without a second ``predict()`` call.

        Args:
            response:          ECHO's full response text for this turn.
            user_input:        The user's message for this turn.
            novelty_score:     novelty drive score [0, 1].
            curiosity:         curiosity drive score [0, 1].
            coherence:         coherence drive score [0, 1].
            emotional_valence: current emotional valence [-1, 1].
            identity_drift:    cosine distance between previous/current agent weights [0, 1].
            memory_count:      total memories retrieved this turn (episodic + semantic).
        """
        # Engagement proxy: longer user turns → higher presumed engagement.
        user_engagement = min(1.0, len(user_input) / 200)

        self.personalization.update(
            len(response),
            novelty_score=novelty_score,
            user_engagement=user_engagement,
            curiosity=curiosity,
            coherence=coherence,
        )

        self.predictor.observe(
            emotional_valence=emotional_valence,
            curiosity=curiosity,
            identity_drift=identity_drift,
            memory_load=min(1.0, memory_count / 10),
        )

        self._n += 1

        # Throttled persistence — avoids a DB write on every single interaction.
        if self._n % _SAVE_INTERVAL == 0:
            await self.personalization.save()

        priors = self.predictor.predict()

        # Publish learning cycle event to the event bus for monitoring.
        await bus.publish(CognitiveEvent(
            topic=EventTopic.META_STATE_UPDATE,
            payload={
                "type": "learning_cycle",
                "n": self._n,
                "verbosity": round(self.personalization.verbosity, 3),
                "topic_depth": round(self.personalization.topic_depth, 3),
                "curiosity_spike_prob": priors.curiosity_spike_prob,
                "identity_drift_risk": priors.identity_drift_risk,
                "consolidation_urgency": priors.consolidation_urgency,
            },
        ))

        logger.debug(
            "LearningEngine n=%d  priors=%s  verbosity=%.3f  depth=%.3f",
            self._n, priors, self.personalization.verbosity, self.personalization.topic_depth,
        )
        return priors

    # ------------------------------------------------------------------
    # Pre-interaction read (no side effects)
    # ------------------------------------------------------------------

    def get_priors(self) -> PredictionPriors:
        """Return current prediction priors (pure read — safe to call any time)."""
        return self.predictor.predict()

    # ------------------------------------------------------------------
    # Hot-swap
    # ------------------------------------------------------------------

    def reset_predictor(self) -> None:
        """Reset the predictive engine without restarting the system."""
        self.predictor.reset()
        logger.info("LearningEngine predictor reset (hot-swap)")
