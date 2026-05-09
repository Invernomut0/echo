"""Unit tests for Telegram bot bridge behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_help_command_with_bot_suffix_is_handled(monkeypatch):
    """Commands like /help@botusername should be treated as /help."""
    from echo.integrations import telegram_bot as tg

    bridge = tg.TelegramBotBridge()
    bridge._allowed_chat_ids = set()

    send_message = AsyncMock()
    monkeypatch.setattr(bridge, "_send_message", send_message)

    interact = AsyncMock(return_value=SimpleNamespace(assistant_response="ok"))
    monkeypatch.setattr(tg.pipeline, "interact", interact)

    update = {
        "message": {
            "chat": {"id": 123, "type": "private"},
            "from": {"id": 123},
            "text": "/help@echo_bot",
        }
    }

    await bridge._handle_update(update)

    send_message.assert_awaited_once()
    interact.assert_not_called()


@pytest.mark.asyncio
async def test_group_message_allowed_when_sender_id_is_whitelisted(monkeypatch):
    """If sender ID is allowed, group chat message should be processed."""
    from echo.integrations import telegram_bot as tg

    bridge = tg.TelegramBotBridge()
    bridge._allowed_chat_ids = {602166026}

    send_long_message = AsyncMock()
    monkeypatch.setattr(bridge, "_send_long_message", send_long_message)

    interact = AsyncMock(return_value=SimpleNamespace(assistant_response="ciao gruppo"))
    monkeypatch.setattr(tg.pipeline, "interact", interact)

    update = {
        "message": {
            "chat": {"id": -1001234567890, "type": "supergroup"},
            "from": {"id": 602166026},
            "text": "Rispondi per favore",
        }
    }

    await bridge._handle_update(update)

    interact.assert_awaited_once()
    send_long_message.assert_awaited_once_with(-1001234567890, "ciao gruppo")


@pytest.mark.asyncio
async def test_private_unauthorized_chat_gets_hint(monkeypatch):
    """Unauthorized private chats receive a clear guidance message."""
    from echo.integrations import telegram_bot as tg

    bridge = tg.TelegramBotBridge()
    bridge._allowed_chat_ids = {111}

    send_message = AsyncMock()
    monkeypatch.setattr(bridge, "_send_message", send_message)

    interact = AsyncMock(return_value=SimpleNamespace(assistant_response="ignored"))
    monkeypatch.setattr(tg.pipeline, "interact", interact)

    update = {
        "message": {
            "chat": {"id": 222, "type": "private"},
            "from": {"id": 222},
            "text": "ciao",
        }
    }

    await bridge._handle_update(update)

    send_message.assert_awaited_once()
    interact.assert_not_called()
