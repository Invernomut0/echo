"""Outbound Telegram notifications (no polling dependency)."""

from __future__ import annotations

import logging
from typing import Iterable

import httpx

from echo.core.config import settings

logger = logging.getLogger(__name__)


def _split_text(text: str, max_chars: int = 4096) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            split_at = text.rfind("\n", start, end)
            if split_at > start + max_chars // 3:
                end = split_at

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end
        while start < len(text) and text[start] == "\n":
            start += 1

    return chunks or [text[:max_chars]]


def _format_goal_resolution_message(
    *,
    goal_title: str,
    why_chosen: str,
    solution_summary: str,
) -> str:
    return (
        "🎯 Goal risolto\n"
        f"Goal: {goal_title}\n\n"
        f"Perché l'avevo scelto: {why_chosen}\n\n"
        f"Riassunto soluzione: {solution_summary}"
    )


async def send_goal_resolution_notification(
    *,
    goal_title: str,
    why_chosen: str,
    solution_summary: str,
    chat_ids: Iterable[int] | None = None,
) -> int:
    """Broadcast a goal-resolution summary to configured Telegram chats.

    Returns the number of successfully notified chats.
    """
    if not settings.telegram_enabled or not settings.telegram_goal_notifications_enabled:
        return 0

    token = (settings.telegram_bot_token or "").strip()
    if not token:
        return 0

    target_chats = list(chat_ids) if chat_ids is not None else list(settings.telegram_allowed_chat_ids)
    target_chats = sorted({int(cid) for cid in target_chats if cid is not None})
    if not target_chats:
        return 0

    base_url = settings.telegram_api_base_url.rstrip("/")
    send_url = f"{base_url}/bot{token}/sendMessage"

    text = _format_goal_resolution_message(
        goal_title=goal_title,
        why_chosen=why_chosen,
        solution_summary=solution_summary,
    )
    chunks = _split_text(text, max_chars=3900)

    sent = 0
    timeout = max(5.0, float(settings.telegram_request_timeout_seconds))
    async with httpx.AsyncClient(timeout=timeout) as client:
        for chat_id in target_chats:
            ok_chat = True
            for chunk in chunks:
                try:
                    response = await client.post(send_url, json={"chat_id": chat_id, "text": chunk})
                    response.raise_for_status()
                    payload = response.json()
                    if not payload.get("ok", False):
                        ok_chat = False
                        logger.warning(
                            "Goal notification sendMessage non-ok chat_id=%s: %s",
                            chat_id,
                            payload,
                        )
                        break
                except Exception as exc:  # noqa: BLE001
                    ok_chat = False
                    logger.warning(
                        "Goal notification failed chat_id=%s: %s",
                        chat_id,
                        exc,
                    )
                    break

            if ok_chat:
                sent += 1

    return sent
