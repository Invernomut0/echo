"""Global Workspace — Baars-inspired competition for cognitive resources."""

from __future__ import annotations

import logging

from echo.core.config import settings
from echo.core.types import MetaState, WorkspaceItem, WorkspaceSnapshot

logger = logging.getLogger(__name__)


class GlobalWorkspace:
    """Maintains a limited-slot workspace where agents compete for activation.

    Slots = settings.max_workspace_slots (default 7).
    Items compete by salience × (1 + routing_weight_bonus).
    """

    def __init__(self, max_slots: int | None = None) -> None:
        self._max_slots = max_slots or settings.max_workspace_slots
        self._items: list[WorkspaceItem] = []

    @property
    def snapshot(self) -> WorkspaceSnapshot:
        return WorkspaceSnapshot(items=list(self._items))

    def broadcast(
        self,
        content: str,
        source_agent: str,
        salience: float,
        routing_weight: float = 1.0,
    ) -> None:
        """Add item to workspace; evict lowest-scoring if over capacity."""
        score = salience * (1.0 + routing_weight * 0.2)
        item = WorkspaceItem(
            content=content,
            source_agent=source_agent,
            salience=salience,
            competition_score=round(score, 4),
        )
        self._items.append(item)
        self._items.sort(key=lambda x: x.competition_score, reverse=True)

        if len(self._items) > self._max_slots:
            evicted = self._items.pop()
            logger.debug("Evicted from workspace: %s (score=%.3f)", evicted.source_agent, evicted.competition_score)

    def clear(self) -> None:
        self._items = []

    def load_memories(self, memories: list, agent_name: str = "archivist") -> None:
        """Push retrieved memories into workspace as low-salience background context."""
        for mem in memories[:3]:
            self.broadcast(mem.content, agent_name, salience=mem.salience * 0.7)

    def competition_scores(self) -> dict[str, float]:
        return {item.source_agent: item.competition_score for item in self._items}
