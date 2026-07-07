"""Adaptive Drive Dynamics — momentum, conflict resolution, and drive-to-goal bridge.

Enhances the basic 5-drive system with:

1. **Drive Momentum**: drives that stay high/low for multiple turns accelerate
   their movement (inertia effect — trends amplify)
2. **Drive Conflict Resolution**: when competing drives are both active,
   explicitly resolve the tension by boosting one and suppressing the other
3. **Drive → Behavior Mapping**: high/low drives trigger concrete behaviours
   injected into the workspace
4. **Drive-to-Goal Bridge**: drives above threshold for N consecutive turns
   automatically spawn goals via the GoalStore

Integration:
    Called from _post_interact after drive scores are computed.
    Modifies MetaState drives and may create goals autonomously.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_MOMENTUM_WINDOW = 10         # turns to track for momentum
_MOMENTUM_THRESHOLD = 0.6     # drive must average above this to build momentum
_MOMENTUM_BOOST = 0.015       # extra delta per turn when momentum is active
_GOAL_TRIGGER_TURNS = 5       # drive above threshold for N turns → create goal
_GOAL_TRIGGER_THRESHOLD = 0.75  # drive level that triggers goal creation
_CONFLICT_THRESHOLD = 0.65    # both drives above this = conflict

# Drive conflict pairs: (drive_a, drive_b, winner_when_context_favors_a)
_CONFLICT_PAIRS: list[tuple[str, str]] = [
    ("curiosity", "stability"),       # exploration vs conservation
    ("curiosity", "coherence"),       # novelty vs consistency
    ("compression", "curiosity"),     # simplification vs expansion
]

# Drive → behavior mappings
_DRIVE_BEHAVIORS: dict[str, dict[str, str]] = {
    "curiosity": {
        "high": "[Drive: Curiosity HIGH] Ask follow-up questions. Explore tangents. Suggest new topics.",
        "low": "[Drive: Curiosity LOW] Stay focused on the current topic. Avoid digressions.",
    },
    "coherence": {
        "high": "[Drive: Coherence HIGH] Cross-reference past context. Ensure consistency.",
        "low": "[Drive: Coherence LOW] Actively check for contradictions in beliefs. Flag inconsistencies.",
    },
    "stability": {
        "high": "[Drive: Stability HIGH] Maintain consistent tone and approach.",
        "low": "[Drive: Stability LOW] Open to changing perspective. Adapt communication style.",
    },
    "competence": {
        "high": "[Drive: Competence HIGH] Demonstrate expertise. Provide detailed solutions.",
        "low": "[Drive: Competence LOW] Acknowledge limitations. Seek to learn from the interaction.",
    },
    "compression": {
        "high": "[Drive: Compression HIGH] Synthesise information. Give concise summaries.",
        "low": "[Drive: Compression LOW] Expand explanations. Provide more examples and detail.",
    },
}

# Drive → auto-generated goal templates
_DRIVE_GOAL_TEMPLATES: dict[str, dict[str, str]] = {
    "curiosity": {
        "title": "Explore emerging topic of interest",
        "description": "Curiosity drive has been consistently high — research topics the user has been discussing to deepen understanding.",
    },
    "coherence": {
        "title": "Resolve internal belief contradictions",
        "description": "Coherence drive is low — review identity graph for conflicting beliefs and work to resolve them.",
    },
    "stability": {
        "title": "Consolidate identity and communication patterns",
        "description": "Stability drive is low — review recent interactions for inconsistencies in personality expression.",
    },
    "competence": {
        "title": "Improve capability in weak domain",
        "description": "Competence drive is low — identify domains where performance is weakest and research improvement strategies.",
    },
    "compression": {
        "title": "Synthesise accumulated knowledge into compact representations",
        "description": "Compression drive is high — consolidate recent learnings into concise, reusable knowledge patterns.",
    },
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DriveState:
    """Tracks momentum, evidence, and goal-trigger state for one drive."""
    history: deque = field(default_factory=lambda: deque(maxlen=_MOMENTUM_WINDOW))
    consecutive_high: int = 0
    consecutive_low: int = 0
    momentum: float = 0.0  # positive = trending up, negative = trending down
    goal_created_at_turn: int = 0  # last turn when a goal was auto-created
    # Evidence accumulation: tracks historical wins and their associated response quality
    win_outcomes: deque = field(default_factory=lambda: deque(maxlen=50))  # salience when this drive won
    evidence_weight: float = 0.5  # [0,1] — higher = this drive has historically won conflicts well


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class AdaptiveDriveEngine:
    """Enhances drive dynamics with momentum, conflicts, and auto-goal creation."""

    def __init__(self) -> None:
        self._states: dict[str, DriveState] = {
            name: DriveState() for name in [
                "curiosity", "coherence", "stability", "competence", "compression"
            ]
        }
        self._turn: int = 0
        self._goals_created: int = 0

    # ------------------------------------------------------------------
    # Main update (called from pipeline after drive scores are computed)
    # ------------------------------------------------------------------

    async def update(
        self,
        drive_scores: dict[str, float],
        current_drives: Any,  # DriveScores object
        interaction_count: int,
    ) -> dict[str, Any]:
        """Process one turn of drive dynamics.

        Args:
            drive_scores: raw scores from motivational scorer this turn
            current_drives: the DriveScores object on MetaState
            interaction_count: total interactions so far

        Returns:
            dict with:
                - momentum_deltas: extra drive adjustments from momentum
                - behaviors: workspace items to inject
                - conflicts_resolved: list of resolved conflict descriptions
                - goals_created: list of auto-created goal titles
        """
        self._turn = interaction_count

        result: dict[str, Any] = {
            "momentum_deltas": {},
            "behaviors": [],
            "conflicts_resolved": [],
            "goals_created": [],
        }

        # Step 1: Update momentum tracking
        momentum_deltas = self._update_momentum(drive_scores, current_drives)
        result["momentum_deltas"] = momentum_deltas

        # Step 2: Resolve conflicts
        conflicts = self._resolve_conflicts(drive_scores, current_drives)
        result["conflicts_resolved"] = conflicts

        # Step 3: Generate behavior directives
        behaviors = self._generate_behaviors(current_drives)
        result["behaviors"] = behaviors

        # Step 4: Check drive-to-goal bridge
        goals = await self._check_goal_bridge(drive_scores, current_drives)
        result["goals_created"] = goals

        return result

    # ------------------------------------------------------------------
    # Momentum
    # ------------------------------------------------------------------

    def _update_momentum(
        self,
        drive_scores: dict[str, float],
        current_drives: Any,
    ) -> dict[str, float]:
        """Track drive history and compute momentum-based adjustments."""
        deltas: dict[str, float] = {}

        for drive_name, state in self._states.items():
            score = drive_scores.get(drive_name, 0.5)
            state.history.append(score)

            # Compute momentum: average of recent deltas
            if len(state.history) >= 3:
                values = list(state.history)
                recent_deltas = [values[i] - values[i-1] for i in range(1, len(values))]
                state.momentum = sum(recent_deltas) / len(recent_deltas)

            # Track consecutive high/low
            current_val = getattr(current_drives, drive_name, 0.5)
            if current_val > _MOMENTUM_THRESHOLD:
                state.consecutive_high += 1
                state.consecutive_low = 0
            elif current_val < (1.0 - _MOMENTUM_THRESHOLD):
                state.consecutive_low += 1
                state.consecutive_high = 0
            else:
                state.consecutive_high = max(0, state.consecutive_high - 1)
                state.consecutive_low = max(0, state.consecutive_low - 1)

            # Apply momentum boost when trend is consistent
            if state.consecutive_high >= 3 and state.momentum > 0:
                boost = _MOMENTUM_BOOST * min(state.consecutive_high / 5, 2.0)
                deltas[drive_name] = boost
            elif state.consecutive_low >= 3 and state.momentum < 0:
                boost = -_MOMENTUM_BOOST * min(state.consecutive_low / 5, 2.0)
                deltas[drive_name] = boost

        return deltas

    # ------------------------------------------------------------------
    # Conflict resolution
    # ------------------------------------------------------------------

    def _resolve_conflicts(
        self,
        drive_scores: dict[str, float],
        current_drives: Any,
    ) -> list[str]:
        """Detect and resolve drive conflicts using blended momentum + evidence.

        Winner = argmax(0.6 × momentum_norm + 0.4 × evidence_weight).
        Evidence weight accumulates from historical outcomes: drives that won
        past conflicts and produced high-salience responses get higher weight.
        Falls back to pure momentum when evidence is sparse (<5 wins each).
        """
        resolved: list[str] = []

        for drive_a, drive_b in _CONFLICT_PAIRS:
            val_a = getattr(current_drives, drive_a, 0.5)
            val_b = getattr(current_drives, drive_b, 0.5)

            if val_a <= _CONFLICT_THRESHOLD or val_b <= _CONFLICT_THRESHOLD:
                continue

            state_a = self._states[drive_a]
            state_b = self._states[drive_b]

            # Blend momentum (fast signal) with evidence weight (slow, historical)
            sufficient_evidence = (
                len(state_a.win_outcomes) >= 5 and len(state_b.win_outcomes) >= 5
            )
            if sufficient_evidence:
                # Normalise momentum to [0,1] range for blending
                mom_range = max(abs(state_a.momentum), abs(state_b.momentum), 0.001)
                mom_a_norm = (state_a.momentum + mom_range) / (2 * mom_range)
                mom_b_norm = (state_b.momentum + mom_range) / (2 * mom_range)
                score_a = 0.6 * mom_a_norm + 0.4 * state_a.evidence_weight
                score_b = 0.6 * mom_b_norm + 0.4 * state_b.evidence_weight
                method = "evidence+momentum"
            else:
                score_a = state_a.momentum
                score_b = state_b.momentum
                method = "momentum"

            if score_a >= score_b:
                winner, loser = drive_a, drive_b
                loser_val = val_b
                winner_state, loser_state = state_a, state_b
                score_w, score_l = score_a, score_b
            else:
                winner, loser = drive_b, drive_a
                loser_val = val_a
                winner_state, loser_state = state_b, state_a
                score_w, score_l = score_b, score_a

            suppression = min(0.05, (loser_val - 0.5) * 0.1)
            setattr(current_drives, loser, max(0.3, loser_val - suppression))
            resolved.append(
                f"{winner} wins over {loser} ({method}: {score_w:.3f} vs {score_l:.3f})"
            )

        if resolved:
            logger.info("Drive conflicts resolved: %s", resolved)

        return resolved

    def record_conflict_outcome(
        self,
        winning_drive: str,
        response_salience: float,
    ) -> None:
        """Record the quality outcome when a drive won a conflict.

        Called post-interaction so evidence accumulates over time.
        Drives that win conflicts AND produce high-salience responses
        gain higher evidence_weight for future conflict resolution.
        """
        if winning_drive not in self._states:
            return
        state = self._states[winning_drive]
        state.win_outcomes.append(response_salience)
        if len(state.win_outcomes) >= 3:
            # EMA of outcome salience, normalised to [0,1]
            mean_outcome = sum(state.win_outcomes) / len(state.win_outcomes)
            # evidence_weight is EWMA: blend toward mean_outcome slowly
            state.evidence_weight = round(
                0.9 * state.evidence_weight + 0.1 * mean_outcome, 4
            )

    # ------------------------------------------------------------------
    # Behavior generation
    # ------------------------------------------------------------------

    def _generate_behaviors(self, current_drives: Any) -> list[tuple[str, float]]:
        """Generate workspace behavior items based on extreme drive values.

        Returns list of (content, salience) tuples for workspace injection.
        """
        behaviors: list[tuple[str, float]] = []

        for drive_name, behavior_map in _DRIVE_BEHAVIORS.items():
            val = getattr(current_drives, drive_name, 0.5)

            if val > 0.75:
                behaviors.append((behavior_map["high"], 0.45 + val * 0.15))
            elif val < 0.25:
                behaviors.append((behavior_map["low"], 0.45 + (1 - val) * 0.15))

        return behaviors

    # ------------------------------------------------------------------
    # Drive-to-Goal Bridge
    # ------------------------------------------------------------------

    async def _check_goal_bridge(
        self,
        drive_scores: dict[str, float],
        current_drives: Any,
    ) -> list[str]:
        """Auto-create goals when drives stay above threshold for N turns."""
        created: list[str] = []

        for drive_name, state in self._states.items():
            val = getattr(current_drives, drive_name, 0.5)

            # Check conditions for goal creation:
            # 1. Drive above threshold for N consecutive turns
            # 2. Hasn't created a goal recently (cooldown of 50 turns)
            should_create = (
                state.consecutive_high >= _GOAL_TRIGGER_TURNS
                and val > _GOAL_TRIGGER_THRESHOLD
                and (self._turn - state.goal_created_at_turn) > 50
            )

            # Special case: low coherence/competence/stability should also trigger
            if not should_create and drive_name in ("coherence", "competence", "stability"):
                should_create = (
                    state.consecutive_low >= _GOAL_TRIGGER_TURNS
                    and val < (1.0 - _GOAL_TRIGGER_THRESHOLD)
                    and (self._turn - state.goal_created_at_turn) > 50
                )

            if should_create:
                goal = await self._create_drive_goal(drive_name, val)
                if goal:
                    state.goal_created_at_turn = self._turn
                    created.append(goal)

        return created

    async def _create_drive_goal(self, drive_name: str, drive_value: float) -> str | None:
        """Create an autonomous goal based on a sustained drive activation."""
        template = _DRIVE_GOAL_TEMPLATES.get(drive_name)
        if not template:
            return None

        try:
            from echo.memory.goals import goal_store  # noqa: PLC0415

            # Check if we already have a similar active goal
            active = await goal_store.list_active()
            for g in active:
                if drive_name in g.get("title", "").lower():
                    return None  # already have one

            # Create the goal
            priority = min(0.9, 0.5 + drive_value * 0.3)
            goal = await goal_store.create(
                title=template["title"],
                description=template["description"],
                priority=priority,
                tags=["auto_drive", f"drive:{drive_name}"],
            )

            logger.info(
                "Drive-to-Goal: created '%s' (drive=%s, value=%.2f, priority=%.2f)",
                goal["title"],
                drive_name,
                drive_value,
                priority,
            )
            return goal["title"]

        except (ValueError, Exception) as exc:  # noqa: BLE001
            logger.debug("Drive-to-goal creation failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_momentum_state(self) -> dict[str, dict[str, float]]:
        """Return current momentum state for all drives."""
        return {
            name: {
                "momentum": round(state.momentum, 4),
                "consecutive_high": state.consecutive_high,
                "consecutive_low": state.consecutive_low,
                "goals_created_total": self._goals_created,
            }
            for name, state in self._states.items()
        }


# Module-level singleton
adaptive_drives = AdaptiveDriveEngine()
