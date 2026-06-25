"""User activity tracker — lets background tasks know when a user is active.

Background tasks (curiosity, initiative, consolidation LLM calls) should
yield priority to user interactions. This module provides a simple flag:

    mark_active()    — call at the start of each user interaction
    is_active()      — returns True if user interacted recently
    wait_for_idle()  — async wait until user has been idle long enough

Usage in background tasks::

    from echo.core.user_activity import is_active
    if is_active():
        logger.debug("User active — skipping background LLM call")
        return

Usage in pipeline::

    from echo.core.user_activity import mark_active
    mark_active()   # call at the start of stream_interact / interact
"""

from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

# Monotonic timestamp of the last user interaction.
_last_interaction_at: float = 0.0

# How long (seconds) after an interaction we consider the user "active".
# Background tasks will skip LLM calls during this window.
_ACTIVE_WINDOW_SECONDS: float = 60.0


def mark_active() -> None:
    """Signal that a user interaction just started."""
    global _last_interaction_at  # noqa: PLW0603
    _last_interaction_at = time.monotonic()


def is_active() -> bool:
    """Return True if a user interaction occurred within the active window."""
    if _last_interaction_at == 0.0:
        return False
    return (time.monotonic() - _last_interaction_at) < _ACTIVE_WINDOW_SECONDS


def seconds_since_interaction() -> float:
    """Seconds elapsed since last user interaction (∞ if never)."""
    if _last_interaction_at == 0.0:
        return float("inf")
    return time.monotonic() - _last_interaction_at


async def wait_for_idle(
    timeout: float = 30.0,
    poll_interval: float = 2.0,
) -> bool:
    """Wait until the user has been idle for at least _ACTIVE_WINDOW_SECONDS.

    Returns True if idle, False if timeout expired.
    Used by background tasks that want to be polite about LLM usage.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not is_active():
            return True
        await asyncio.sleep(poll_interval)
    return False
