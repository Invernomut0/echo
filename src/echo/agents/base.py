"""Base agent interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from echo.core.types import AgentRole, MetaState, WorkspaceSnapshot


class BaseAgent(ABC):
    """All cognitive agents inherit from this."""

    role: AgentRole

    def __init__(self, routing_weight: float = 1.0) -> None:
        self.routing_weight = routing_weight

    @abstractmethod
    async def process(
        self,
        user_input: str,
        workspace: WorkspaceSnapshot,
        meta_state: MetaState,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Process user input in context of workspace and meta-state.

        Returns the agent's text contribution.
        """

    @property
    def name(self) -> str:
        return self.role.value

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(weight={self.routing_weight:.2f})"
