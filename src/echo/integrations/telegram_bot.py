"""Telegram bot bridge (long polling) for PROJECT ECHO."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from contextlib import suppress
from typing import Any

import httpx

from echo.core.config import settings
from echo.core.pipeline import pipeline

logger = logging.getLogger(__name__)


class TelegramBotBridge:
    """Bridge Telegram messages to ECHO's cognitive pipeline."""

    def __init__(self) -> None:
        self._token = settings.telegram_bot_token.strip()
        self._enabled = bool(settings.telegram_enabled and self._token)
        self._base_url = ""
        if self._token:
            base = settings.telegram_api_base_url.rstrip("/")
            self._base_url = f"{base}/bot{self._token}"

        self._poll_interval = max(0.1, settings.telegram_poll_interval_seconds)
        self._update_timeout = max(1, settings.telegram_update_timeout_seconds)
        self._request_timeout = max(5.0, settings.telegram_request_timeout_seconds)
        self._allowed_chat_ids = set(settings.telegram_allowed_chat_ids)
        self._history_turns = max(1, settings.telegram_history_turns)
        self._max_reply_chars = max(500, min(4096, settings.telegram_max_reply_chars))

        self._offset = 0
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._client: httpx.AsyncClient | None = None
        self._history_by_chat: dict[int, deque[dict[str, str]]] = {}
        self._unauthorized_hint_sent_at: dict[int, float] = {}
        self._unauthorized_hint_cooldown_seconds = 30.0

    def _buffer_for(self, chat_id: int) -> deque[dict[str, str]]:
        buffer = self._history_by_chat.get(chat_id)
        if buffer is None:
            buffer = deque(maxlen=self._history_turns * 2)
            self._history_by_chat[chat_id] = buffer
        return buffer

    def _is_chat_authorized(self, chat_id: int, sender_id: int | None) -> bool:
        """Allow explicit chat IDs and (for groups) sender IDs."""
        if not self._allowed_chat_ids:
            return True
        if chat_id in self._allowed_chat_ids:
            return True
        return sender_id is not None and sender_id in self._allowed_chat_ids

    def start(self) -> None:
        """Start background polling if Telegram integration is enabled."""
        if not settings.telegram_enabled:
            logger.info("Telegram bridge disabled (TELEGRAM_ENABLED=false)")
            return

        if not self._token:
            logger.warning(
                "Telegram enabled but TELEGRAM_BOT_TOKEN is empty — bridge not started"
            )
            return

        if self._task and not self._task.done():
            return

        self._running = True
        self._client = httpx.AsyncClient(timeout=self._request_timeout)
        self._task = asyncio.create_task(self._run_loop())

        allowed = sorted(self._allowed_chat_ids) if self._allowed_chat_ids else "all"
        logger.info("Telegram bridge started (allowed_chat_ids=%s)", allowed)

    async def stop(self) -> None:
        """Stop background polling and close HTTP resources."""
        self._running = False

        if self._task and not self._task.done():
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        self._task = None

        if self._client is not None:
            await self._client.aclose()
            self._client = None

        if settings.telegram_enabled:
            logger.info("Telegram bridge stopped")

    async def _run_loop(self) -> None:
        while self._running:
            try:
                updates = await self._fetch_updates()
                for update in updates:
                    await self._handle_update(update)

                if not updates:
                    await asyncio.sleep(self._poll_interval)

            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error("Telegram polling error: %s", exc, exc_info=True)
                await asyncio.sleep(max(self._poll_interval, 1.0))

    async def _fetch_updates(self) -> list[dict[str, Any]]:
        if self._client is None:
            return []

        # Accept standard chat messages plus channel posts and edited variants.
        # This avoids silent drops when users interact from channels/groups where
        # updates are not always delivered as plain "message".
        allowed_updates = [
            "message",
            "edited_message",
            "channel_post",
            "edited_channel_post",
        ]

        response = await self._client.get(
            f"{self._base_url}/getUpdates",
            params={
                "timeout": self._update_timeout,
                "offset": self._offset,
                "allowed_updates": json.dumps(allowed_updates),
            },
        )
        response.raise_for_status()

        payload = response.json()
        if not payload.get("ok", False):
            raise RuntimeError(f"Telegram getUpdates failed: {payload}")

        updates = payload.get("result", [])
        if updates:
            last_id = max(int(item.get("update_id", 0)) for item in updates)
            self._offset = last_id + 1

        return updates

    @staticmethod
    def _extract_message_container(update: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
        """Return first supported Telegram message container from an update."""
        for key in ("message", "edited_message", "channel_post", "edited_channel_post"):
            candidate = update.get(key)
            if isinstance(candidate, dict):
                return candidate, key
        return None, None

    async def _send_unauthorized_hint(self, chat_id: int, chat_type: str | None) -> None:
        """Send a throttled hint that helps users whitelist the correct chat id."""
        now = time.monotonic()
        last = self._unauthorized_hint_sent_at.get(chat_id, 0.0)
        if now - last < self._unauthorized_hint_cooldown_seconds:
            return
        self._unauthorized_hint_sent_at[chat_id] = now

        scope = "chat privata" if chat_type == "private" else "chat/gruppo"
        try:
            await self._send_message(
                chat_id,
                f"⚠️ {scope} non autorizzata. Aggiungi questo ID in Allowed Chat IDs: {chat_id}",
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not send unauthorized hint to chat_id=%s: %s", chat_id, exc)

    async def _handle_update(self, update: dict[str, Any]) -> None:
        message, update_kind = self._extract_message_container(update)
        if not isinstance(message, dict):
            return

        chat = message.get("chat")
        if not isinstance(chat, dict):
            return

        chat_id_raw = chat.get("id")
        if chat_id_raw is None:
            return

        try:
            chat_id = int(chat_id_raw)
        except (TypeError, ValueError):
            return

        sender_id: int | None = None
        sender = message.get("from")
        if isinstance(sender, dict) and sender.get("id") is not None:
            try:
                sender_id = int(sender.get("id"))
            except (TypeError, ValueError):
                sender_id = None

        text = (message.get("text") or message.get("caption") or "").strip()
        if not text:
            return

        logger.info(
            "Telegram update received kind=%s chat_id=%s sender_id=%s",
            update_kind,
            chat_id,
            sender_id,
        )

        if not self._is_chat_authorized(chat_id, sender_id):
            logger.warning(
                "Ignoring Telegram message from unauthorized chat_id=%s sender_id=%s",
                chat_id,
                sender_id,
            )
            await self._send_unauthorized_hint(chat_id, str(chat.get("type", "")))
            return

        command_token = text.split(maxsplit=1)[0]
        command = command_token.partition("@")[0].lower()
        if command in {"/start", "/help"}:
            privacy_hint = ""
            if chat.get("type") in {"group", "supergroup"}:
                privacy_hint = (
                    "\n\nℹ️ Se non rispondo ai messaggi normali nel gruppo, "
                    "disattiva la Privacy Mode con @BotFather (/setprivacy)."
                )
            await self._send_message(
                chat_id,
                "👋 ECHO è online. Scrivimi un messaggio per iniziare. "
                "Usa /reset per azzerare il contesto della chat."
                f"{privacy_hint}",
            )
            return

        if command == "/reset":
            self._history_by_chat.pop(chat_id, None)
            await self._send_message(chat_id, "🧹 Contesto conversazione azzerato.")
            return

        try:
            history = list(self._buffer_for(chat_id))
            record = await pipeline.interact(text, history=history)

            chat_buffer = self._buffer_for(chat_id)
            chat_buffer.append({"role": "user", "content": text})
            chat_buffer.append({"role": "assistant", "content": record.assistant_response})

            await self._send_long_message(chat_id, record.assistant_response)

        except Exception as exc:  # noqa: BLE001
            logger.error("Telegram message handling failed: %s", exc, exc_info=True)
            await self._send_message(chat_id, "⚠️ Errore interno ECHO. Riprova tra poco.")

    async def _send_long_message(self, chat_id: int, text: str) -> None:
        cleaned = text.strip() if text else ""
        if not cleaned:
            cleaned = "(nessuna risposta)"

        for chunk in self._split_text(cleaned, self._max_reply_chars):
            await self._send_message(chat_id, chunk)

    async def _send_message(self, chat_id: int, text: str) -> None:
        if self._client is None:
            return

        payload = {
            "chat_id": chat_id,
            "text": text[:4096],
        }

        response = await self._client.post(f"{self._base_url}/sendMessage", json=payload)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok", False):
            logger.warning("Telegram sendMessage failed for chat_id=%s: %s", chat_id, data)

    @staticmethod
    def _split_text(text: str, max_chars: int) -> list[str]:
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
