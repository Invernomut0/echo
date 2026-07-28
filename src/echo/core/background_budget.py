"""Token budget for ECHO's autonomous background work.

Problem this solves
-------------------
ECHO's background modules (consolidation, curiosity, goals, proactive engine,
wiki updates) each throttle themselves independently.  In aggregate they can
still saturate a local inference server: with a 5-minute consolidation
heartbeat and a 15-minute curiosity cycle, a slow backend spends most of its
throughput on autonomous work and has nothing left when the user arrives.

This module adds a single global ceiling on background token consumption,
expressed as a sliding hourly window.  Foreground (user-facing) calls never
pass through it — only autonomous ones.

Priorities
----------
When the budget runs low, low-priority work is dropped first so that the
cognitively essential loops keep running::

    REFLECTION    (3) — identity/belief upkeep, never starved
    CONSOLIDATION (2) — memory hygiene
    CURIOSITY     (1) — knowledge acquisition
    PROACTIVE     (0) — outreach, purely discretionary

Usage::

    from echo.core.background_budget import background_budget, Priority

    if not background_budget.can_spend(600, Priority.CURIOSITY):
        return  # skip this cycle, budget exhausted
    ...
    background_budget.record(actual_tokens)
"""

from __future__ import annotations

import logging
import time
from collections import deque
from enum import IntEnum

logger = logging.getLogger(__name__)


class Priority(IntEnum):
    """Background task priority. Higher survives budget pressure longer."""

    PROACTIVE = 0
    CURIOSITY = 1
    CONSOLIDATION = 2
    REFLECTION = 3


# Fraction of the hourly budget still available below which a priority level
# stops being served.  REFLECTION (3) has no floor — it always runs.
_PRIORITY_FLOOR: dict[Priority, float] = {
    Priority.PROACTIVE: 0.50,      # needs ≥50% of budget left
    Priority.CURIOSITY: 0.30,      # needs ≥30% left
    Priority.CONSOLIDATION: 0.10,  # needs ≥10% left
    Priority.REFLECTION: 0.0,      # always allowed
}

_WINDOW_SECONDS: float = 3600.0


class BackgroundBudget:
    """Sliding-window token budget shared by all autonomous subsystems."""

    def __init__(self, tokens_per_hour: int = 20_000) -> None:
        self._limit = tokens_per_hour
        # (monotonic_timestamp, tokens) entries within the sliding window
        self._spent: deque[tuple[float, int]] = deque()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _evict_expired(self) -> None:
        """Drop entries older than the sliding window."""
        cutoff = time.monotonic() - _WINDOW_SECONDS
        while self._spent and self._spent[0][0] < cutoff:
            self._spent.popleft()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def limit(self) -> int:
        """Configured hourly token ceiling."""
        return self._limit

    def spent(self) -> int:
        """Tokens consumed within the current sliding hour."""
        self._evict_expired()
        return sum(tokens for _, tokens in self._spent)

    def remaining_fraction(self) -> float:
        """Fraction of the hourly budget still available, in [0.0, 1.0]."""
        if self._limit <= 0:
            return 1.0  # limit disabled
        return max(0.0, 1.0 - self.spent() / self._limit)

    def can_spend(self, tokens: int, priority: Priority) -> bool:
        """Return True if *tokens* may be spent at this *priority* level.

        Args:
            tokens: estimated token cost of the pending call.
            priority: caller's priority tier.
        """
        if self._limit <= 0:
            return True  # budget disabled

        remaining = self.remaining_fraction()
        floor = _PRIORITY_FLOOR[priority]

        if remaining < floor:
            logger.debug(
                "Background budget: %s denied (%.0f%% left < %.0f%% floor)",
                priority.name, remaining * 100, floor * 100,
            )
            return False

        # Also refuse a single call large enough to blow the remaining budget
        if tokens > 0 and (self.spent() + tokens) > self._limit and priority < Priority.REFLECTION:
            logger.debug(
                "Background budget: %s denied (call of %d tok exceeds ceiling)",
                priority.name, tokens,
            )
            return False

        return True

    def record(self, tokens: int) -> None:
        """Record *tokens* actually consumed by a background call."""
        if tokens <= 0:
            return
        self._evict_expired()
        self._spent.append((time.monotonic(), tokens))

    def stats(self) -> dict[str, float | int]:
        """Snapshot for the monitoring API."""
        spent = self.spent()
        return {
            "limit_per_hour": self._limit,
            "spent_this_hour": spent,
            "remaining_fraction": round(self.remaining_fraction(), 3),
            "entries": len(self._spent),
        }

    def reset(self) -> None:
        """Clear all recorded spend (used by tests and manual overrides)."""
        self._spent.clear()


# Module-level singleton.  Limit is read from settings at first use so the
# value can be tuned via ECHO_BACKGROUND_TOKEN_BUDGET_PER_HOUR without an
# import-time dependency on the settings object.
def _initial_limit() -> int:
    try:
        from echo.core.config import settings  # noqa: PLC0415
        return settings.background_token_budget_per_hour
    except Exception:  # noqa: BLE001
        return 20_000


background_budget = BackgroundBudget(tokens_per_hour=_initial_limit())
