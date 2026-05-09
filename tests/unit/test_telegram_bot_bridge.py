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
            "message_id": 77,
            "message_thread_id": 55,
            "chat": {"id": -1001234567890, "type": "supergroup"},
            "from": {"id": 602166026},
            "text": "Rispondi per favore",
        }
    }

    await bridge._handle_update(update)

    interact.assert_awaited_once()
    send_long_message.assert_awaited_once_with(
        -1001234567890,
        "ciao gruppo",
        message_thread_id=55,
        reply_to_message_id=77,
    )


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


@pytest.mark.asyncio
async def test_channel_post_is_processed_when_chat_is_whitelisted(monkeypatch):
    """Messages delivered as channel_post should be handled too."""
    from echo.integrations import telegram_bot as tg

    bridge = tg.TelegramBotBridge()
    bridge._allowed_chat_ids = {-100111222333}

    send_long_message = AsyncMock()
    monkeypatch.setattr(bridge, "_send_long_message", send_long_message)

    interact = AsyncMock(return_value=SimpleNamespace(assistant_response="ok canale"))
    monkeypatch.setattr(tg.pipeline, "interact", interact)

    update = {
        "channel_post": {
            "chat": {"id": -100111222333, "type": "channel"},
            "text": "ping canale",
        }
    }

    await bridge._handle_update(update)

    interact.assert_awaited_once()
    send_long_message.assert_awaited_once_with(-100111222333, "ok canale")


@pytest.mark.asyncio
async def test_group_unauthorized_chat_gets_hint(monkeypatch):
    """Unauthorized non-private chats should receive a throttled hint too."""
    from echo.integrations import telegram_bot as tg

    bridge = tg.TelegramBotBridge()
    bridge._allowed_chat_ids = {123456789}

    send_message = AsyncMock()
    monkeypatch.setattr(bridge, "_send_message", send_message)

    update = {
        "message": {
            "chat": {"id": -1009876543210, "type": "supergroup"},
            "from": {"id": 999999},
            "text": "ciao echo",
        }
    }

    await bridge._handle_update(update)

    send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_typing_action_is_sent_while_waiting(monkeypatch):
    """Bridge should emit sendChatAction typing while pipeline is computing."""
    from echo.integrations import telegram_bot as tg

    bridge = tg.TelegramBotBridge()
    bridge._allowed_chat_ids = set()

    send_chat_action = AsyncMock()
    monkeypatch.setattr(bridge, "_send_chat_action", send_chat_action)

    async def _fast_typing_heartbeat(chat_id: int, *, message_thread_id=None):
        await bridge._send_chat_action(chat_id, action="typing", message_thread_id=message_thread_id)

    monkeypatch.setattr(bridge, "_typing_heartbeat", _fast_typing_heartbeat)

    send_long_message = AsyncMock()
    monkeypatch.setattr(bridge, "_send_long_message", send_long_message)

    interact = AsyncMock(return_value=SimpleNamespace(assistant_response="ok"))
    monkeypatch.setattr(tg.pipeline, "interact", interact)

    update = {
        "message": {
            "chat": {"id": 123, "type": "private"},
            "from": {"id": 123},
            "text": "ciao",
        }
    }

    await bridge._handle_update(update)

    send_chat_action.assert_awaited()
    interact.assert_awaited_once()


@pytest.mark.asyncio
async def test_private_sender_metadata_seeds_identity_memory(monkeypatch):
    """Private Telegram sender metadata should be stored as identity facts."""
    from echo.integrations import telegram_bot as tg

    bridge = tg.TelegramBotBridge()
    bridge._allowed_chat_ids = set()

    # Avoid real network calls in this test path
    monkeypatch.setattr(bridge, "_send_chat_action", AsyncMock())
    monkeypatch.setattr(bridge, "_typing_heartbeat", AsyncMock())
    monkeypatch.setattr(bridge, "_send_long_message", AsyncMock())

    semantic_store = AsyncMock()
    monkeypatch.setattr(tg.pipeline.semantic, "store", semantic_store)

    interact = AsyncMock(return_value=SimpleNamespace(assistant_response="ok"))
    monkeypatch.setattr(tg.pipeline, "interact", interact)

    update = {
        "message": {
            "chat": {"id": 602166026, "type": "private"},
            "from": {
                "id": 602166026,
                "first_name": "Lorenzo",
                "username": "lorenzov",
            },
            "text": "ciao",
        }
    }

    await bridge._handle_update(update)

    stored_contents = [
        call.kwargs.get("content", "")
        for call in semantic_store.await_args_list
    ]
    assert "The user's name is Lorenzo." in stored_contents
    assert "The user's Telegram username is @lorenzov." in stored_contents
    interact.assert_awaited_once()


@pytest.mark.asyncio
async def test_read_ack_is_triggered_on_authorized_message(monkeypatch):
    """Bridge should emit read-ack for each authorized incoming message."""
    from echo.integrations import telegram_bot as tg

    bridge = tg.TelegramBotBridge()
    bridge._allowed_chat_ids = set()

    send_read_ack = AsyncMock()
    monkeypatch.setattr(bridge, "_send_read_ack", send_read_ack)
    monkeypatch.setattr(bridge, "_send_chat_action", AsyncMock())
    monkeypatch.setattr(bridge, "_typing_heartbeat", AsyncMock())
    monkeypatch.setattr(bridge, "_send_long_message", AsyncMock())

    interact = AsyncMock(return_value=SimpleNamespace(assistant_response="ok"))
    monkeypatch.setattr(tg.pipeline, "interact", interact)

    update = {
        "message": {
            "message_id": 42,
            "chat": {"id": 123, "type": "private"},
            "from": {"id": 123},
            "text": "ciao",
        }
    }

    await bridge._handle_update(update)

    send_read_ack.assert_awaited_once_with(
        123,
        message_id=42,
        chat_type="private",
    )
    interact.assert_awaited_once()


@pytest.mark.asyncio
async def test_read_ack_falls_back_to_eyes_reply_in_private_chat(monkeypatch):
    """If reaction API fails, bridge should fallback to 👀 reply in private chat."""
    from echo.integrations import telegram_bot as tg

    bridge = tg.TelegramBotBridge()

    fake_client = SimpleNamespace(post=AsyncMock(side_effect=RuntimeError("reaction unavailable")))
    bridge._client = fake_client

    send_message = AsyncMock()
    monkeypatch.setattr(bridge, "_send_message", send_message)

    await bridge._send_read_ack(
        321,
        message_id=99,
        chat_type="private",
    )

    send_message.assert_awaited_once_with(
        321,
        "👀",
        reply_to_message_id=99,
    )
