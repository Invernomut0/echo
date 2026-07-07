"""Global Workspace — Baars-inspired competition for cognitive resources."""

from __future__ import annotations

import logging
import time as _time

from echo.core.config import settings
from echo.core.types import MetaState, WorkspaceItem, WorkspaceSnapshot

logger = logging.getLogger(__name__)

# Salience adjustments for age-based scoring
_AGE_PENALTY_PER_TURN: float = 0.08   # deducted from score per turn an item persists
_AGE_PENALTY_START_TURN: int = 2       # penalty kicks in after this many turns
_RECENCY_BOOST: float = 0.10           # bonus for items added in the current broadcast wave


class GlobalWorkspace:
    """Maintains a limited-slot workspace where agents compete for activation.

    Slots = settings.max_workspace_slots (default 7).

    Scoring:  base = salience × (1 + routing_weight × 0.2)
              + RECENCY_BOOST if added this turn
              − AGE_PENALTY × max(0, turns_resident − AGE_PENALTY_START_TURN)

    Age penalty prevents stale high-salience items from blocking fresh context
    across turns. Recency boost ensures items from the current interaction
    beat out survivors from previous turns.
    """

    def __init__(self, max_slots: int | None = None) -> None:
        self._max_slots = max_slots or settings.max_workspace_slots
        self._items: list[WorkspaceItem] = []
        self._item_added_at: dict[int, int] = {}   # id(item) → turn added
        self._current_turn: int = 0
        self._broadcast_wave: int = 0  # incremented per broadcast call

    def _effective_score(self, item: WorkspaceItem, is_new: bool) -> float:
        """Compute age-adjusted competition score for an item."""
        base = item.competition_score
        turns_resident = self._current_turn - self._item_added_at.get(id(item), self._current_turn)
        age_penalty = _AGE_PENALTY_PER_TURN * max(0, turns_resident - _AGE_PENALTY_START_TURN)
        recency = _RECENCY_BOOST if is_new else 0.0
        return max(0.0, base + recency - age_penalty)

    @property
    def snapshot(self) -> WorkspaceSnapshot:
        return WorkspaceSnapshot(items=list(self._items))

    def advance_turn(self) -> None:
        """Increment turn counter — call once per interaction turn."""
        self._current_turn += 1

    def broadcast(
        self,
        content: str,
        source_agent: str,
        salience: float,
        routing_weight: float = 1.0,
    ) -> None:
        """Add item to workspace; evict lowest effective-score item if over capacity."""
        base_score = salience * (1.0 + routing_weight * 0.2)
        item = WorkspaceItem(
            content=content,
            source_agent=source_agent,
            salience=salience,
            competition_score=round(base_score, 4),
        )
        self._item_added_at[id(item)] = self._current_turn
        self._items.append(item)

        # Sort by effective (age-adjusted) score
        self._items.sort(
            key=lambda x: self._effective_score(x, is_new=(self._item_added_at.get(id(x)) == self._current_turn)),
            reverse=True,
        )

        if len(self._items) > self._max_slots:
            evicted = self._items.pop()
            self._item_added_at.pop(id(evicted), None)
            logger.debug(
                "Evicted from workspace: %s (base=%.3f, effective=%.3f, age=%d turns)",
                evicted.source_agent,
                evicted.competition_score,
                self._effective_score(evicted, is_new=False),
                self._current_turn - self._item_added_at.get(id(evicted), self._current_turn),
            )

    def clear(self) -> None:
        self._items = []

    def load_memories(self, memories: list, agent_name: str = "archivist") -> None:
        """Push retrieved memories into workspace as low-salience background context."""
        for mem in memories[:3]:
            self.broadcast(mem.content, agent_name, salience=mem.salience * 0.7)

    def competition_scores(self) -> dict[str, float]:
        return {item.source_agent: item.competition_score for item in self._items}
