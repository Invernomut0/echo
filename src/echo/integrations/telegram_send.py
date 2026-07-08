"""Centralised Telegram broadcast helper.

Used by:
- CognitivePipeline._post_interact  → mirror web-chat responses to Telegram
- InitiativeEngine._deliver         → proactive messages during heartbeat
- GoalStore resolution notifications (already separate)

Prefers the running TelegramBotBridge (connection pooled), falls back to
a one-shot httpx call if the bridge is unavailable.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Module-level reference to the running bridge — set by server.py lifespan
_bridge: "object | None" = None


def set_bridge(bridge: "object | None") -> None:
    """Register (or clear) the active TelegramBotBridge instance."""
    global _bridge  # noqa: PLW0603
    _bridge = bridge


async def broadcast(text: str, *, prefix: str = "") -> int:
    """Send *text* to all configured Telegram chat IDs.

    Returns the number of chats successfully notified.

    Args:
        text:   Message body.
        prefix: Optional prefix prepended to the text (e.g. an emoji label).
    """
    from echo.core.config import settings  # noqa: PLC0415

    if not settings.telegram_enabled:
        return 0

    token = (settings.telegram_bot_token or "").strip()
    if not token:
        return 0

    chat_ids = list(settings.telegram_allowed_chat_ids)
    if not chat_ids:
        return 0

    full_text = f"{prefix}{text}" if prefix else text

    # Fast path: use running bridge (connection already open)
    bridge = _bridge
    if bridge is not None and getattr(bridge, "_running", False):
        sent = 0
        for chat_id in chat_ids:
            try:
                await bridge._send_long_message(int(chat_id), full_text)  # type: ignore[attr-defined]
                sent += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("broadcast via bridge failed chat_id=%s: %s", chat_id, exc)
        return sent

    # Fallback: one-shot httpx call
    import httpx  # noqa: PLC0415
    from echo.integrations.telegram_bot import _md_to_html  # noqa: PLC0415

    base = settings.telegram_api_base_url.rstrip("/")
    url = f"{base}/bot{token}/sendMessage"
    sent = 0
    html_text = _md_to_html(full_text)
    async with httpx.AsyncClient(timeout=15.0) as client:
        for chat_id in chat_ids:
            remaining = html_text
            while remaining:
                chunk, remaining = remaining[:4096], remaining[4096:]
                try:
                    r = await client.post(url, json={
                        "chat_id": int(chat_id),
                        "text": chunk,
                        "parse_mode": "HTML",
                    })
                    if r.json().get("ok"):
                        sent += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("broadcast fallback failed chat_id=%s: %s", chat_id, exc)
                    break
    return sent
