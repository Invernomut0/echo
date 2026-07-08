"""Telegram bot bridge (long polling) for PROJECT ECHO."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections import deque
from contextlib import suppress
from typing import Any

import httpx

from echo.core.config import settings
from echo.core.pipeline import pipeline

logger = logging.getLogger(__name__)

_NAME_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ'.\-]{2,40}")


def _normalize_space(text: str) -> str:
    return " ".join((text or "").split()).strip().lower()


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
        # Ensure users can actually see the typing indicator even when responses
        # are generated very fast.
        self._typing_min_visible_seconds = max(
            0.0,
            min(3.0, float(getattr(settings, "telegram_typing_min_visible_seconds", 1.2))),
        )

        self._offset = 0
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._client: httpx.AsyncClient | None = None
        self._history_by_chat: dict[int, deque[dict[str, str]]] = {}
        self._unauthorized_hint_sent_at: dict[int, float] = {}
        self._unauthorized_hint_cooldown_seconds = 30.0
        self._identity_signature_by_chat: dict[int, str] = {}

    def _buffer_for(self, chat_id: int) -> deque[dict[str, str]]:
        buffer = self._history_by_chat.get(chat_id)
        if buffer is None:
            buffer = deque(maxlen=self._history_turns * 2)
            self._history_by_chat[chat_id] = buffer
        return buffer

    @staticmethod
    def _strip_user_echo_from_response(response: str, user_text: str) -> str:
        """Remove direct user-text echoes from assistant response.

        Keeps normal semantic references, but drops exact quoted/reprinted lines
        that match the current user message.
        """
        cleaned = (response or "").strip()
        user_norm = _normalize_space(user_text)
        if not cleaned or not user_norm:
            return cleaned

        out_lines: list[str] = []
        removed_any = False
        for raw_line in cleaned.splitlines():
            line = raw_line.strip()
            probe = line.lstrip(">-•: ").strip()
            probe_norm = _normalize_space(probe)
            if probe_norm == user_norm:
                removed_any = True
                continue
            out_lines.append(raw_line)

        result = "\n".join(out_lines).strip()
        if removed_any and not result:
            return "Ricevuto."
        return result or cleaned

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

    async def _bootstrap(self) -> bool:
        """Verify token + delete any active webhook before polling starts.

        Returns True if bootstrap succeeded, False if the token is invalid.
        Long-polling and active webhooks are mutually exclusive — any existing
        webhook must be removed first or getUpdates returns nothing silently.
        """
        if self._client is None:
            return False

        # 1. Verify token via getMe
        try:
            r = await self._client.get(f"{self._base_url}/getMe")
            r.raise_for_status()
            data = r.json()
            if not data.get("ok"):
                logger.error(
                    "Telegram token invalid — getMe returned: %s", data
                )
                return False
            bot = data.get("result", {})
            logger.info(
                "Telegram bot verified: @%s (id=%s)",
                bot.get("username", "?"),
                bot.get("id", "?"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Telegram bootstrap getMe failed: %s", exc)
            return False

        # 2. Delete any active webhook (silently conflicts with long-polling)
        try:
            r = await self._client.post(
                f"{self._base_url}/deleteWebhook",
                json={"drop_pending_updates": False},
            )
            data = r.json()
            if data.get("ok"):
                logger.info("Telegram webhook cleared (long-polling mode active)")
            else:
                logger.debug("deleteWebhook returned: %s", data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telegram deleteWebhook failed (non-fatal): %s", exc)

        return True

    async def _run_loop(self) -> None:
        ok = await self._bootstrap()
        if not ok:
            logger.error(
                "Telegram bridge bootstrap failed — polling loop will not start. "
                "Check TELEGRAM_BOT_TOKEN and network connectivity."
            )
            self._running = False
            return

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

    async def _typing_heartbeat(
        self,
        chat_id: int,
        *,
        message_thread_id: int | None = None,
    ) -> None:
        """Keep Telegram 'typing…' indicator visible while model is computing."""
        while True:
            await self._send_chat_action(
                chat_id,
                action="typing",
                message_thread_id=message_thread_id,
            )
            await asyncio.sleep(4.0)

    async def _send_read_ack(
        self,
        chat_id: int,
        *,
        message_id: int | None,
        chat_type: str | None,
    ) -> None:
        """Acknowledge the message as read with an eyes icon (👀).

        Preferred channel is a Telegram reaction. If unavailable, fallback to a
        lightweight reply icon in private chats.
        """
        if self._client is None or message_id is None:
            return

        reaction_payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "reaction": [{"type": "emoji", "emoji": "👀"}],
            "is_big": False,
        }

        try:
            response = await self._client.post(
                f"{self._base_url}/setMessageReaction",
                json=reaction_payload,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("ok", False):
                return
            raise RuntimeError(f"setMessageReaction returned non-ok payload: {data}")
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Telegram read ack reaction failed for chat_id=%s message_id=%s: %s",
                chat_id,
                message_id,
                exc,
            )

        if chat_type != "private":
            return

        # Fallback for clients/chats where reactions are unavailable.
        with suppress(Exception):
            await self._send_message(
                chat_id,
                "👀",
                reply_to_message_id=message_id,
            )

    async def _ensure_sender_identity_memory(
        self,
        chat_id: int,
        *,
        chat_type: str | None,
        sender: dict[str, Any] | None,
    ) -> None:
        """Persist stable user identity facts from Telegram sender metadata.

        We only do this for private chats to avoid polluting identity memory in
        group contexts where multiple people can write in the same chat.
        """
        if chat_type != "private" or not isinstance(sender, dict):
            return

        first_name_raw = str(sender.get("first_name") or "").strip()
        username_raw = str(sender.get("username") or "").strip().lstrip("@")

        first_name = ""
        if first_name_raw:
            match = _NAME_TOKEN_RE.search(first_name_raw)
            if match:
                first_name = match.group(0).capitalize()

        signature = f"{first_name.lower()}|{username_raw.lower()}"
        if signature and self._identity_signature_by_chat.get(chat_id) == signature:
            return

        try:
            if first_name:
                await pipeline.semantic.store(
                    content=f"The user's name is {first_name}.",
                    tags=["user_identity", "name", "telegram", "private_chat"],
                    salience=0.95,
                )
            if username_raw:
                await pipeline.semantic.store(
                    content=f"The user's Telegram username is @{username_raw}.",
                    tags=["user_identity", "telegram", "username", "private_chat"],
                    salience=0.85,
                )

            if signature:
                self._identity_signature_by_chat[chat_id] = signature
                logger.info(
                    "Telegram identity seeded for chat_id=%s first_name=%s username=%s",
                    chat_id,
                    first_name or "-",
                    username_raw or "-",
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Identity seeding failed for chat_id=%s: %s", chat_id, exc)

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

        message_id: int | None = None
        if message.get("message_id") is not None:
            try:
                message_id = int(message.get("message_id"))
            except (TypeError, ValueError):
                message_id = None

        message_thread_id: int | None = None
        if message.get("message_thread_id") is not None:
            try:
                message_thread_id = int(message.get("message_thread_id"))
            except (TypeError, ValueError):
                message_thread_id = None

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

        chat_type = str(chat.get("type", ""))
        read_ack_task = asyncio.create_task(
            self._send_read_ack(
                chat_id,
                message_id=message_id,
                chat_type=chat_type,
            )
        )

        await self._ensure_sender_identity_memory(
            chat_id,
            chat_type=chat_type,
            sender=sender if isinstance(sender, dict) else None,
        )

        command_token = text.split(maxsplit=1)[0]
        command = command_token.partition("@")[0].lower()
        if command in {"/start", "/help"}:
            privacy_hint = ""
            if chat_type in {"group", "supergroup"}:
                privacy_hint = (
                    "\n\nℹ️ Se non rispondo ai messaggi normali nel gruppo, "
                    "disattiva la Privacy Mode con @BotFather (/setprivacy)."
                )
            with suppress(Exception):
                await read_ack_task
            await self._send_message(
                chat_id,
                "👋 ECHO è online. Scrivimi un messaggio per iniziare. "
                "Usa /reset per azzerare il contesto della chat."
                f"{privacy_hint}",
                message_thread_id=message_thread_id,
            )
            return

        if command == "/reset":
            self._history_by_chat.pop(chat_id, None)
            with suppress(Exception):
                await read_ack_task
            await self._send_message(
                chat_id,
                "🧹 Contesto conversazione azzerato.",
                message_thread_id=message_thread_id,
            )
            return

        await self._send_chat_action(
            chat_id,
            action="typing",
            message_thread_id=message_thread_id,
        )
        typing_started_at = time.monotonic()
        typing_task = asyncio.create_task(
            self._typing_heartbeat(chat_id, message_thread_id=message_thread_id)
        )
        channel_placeholder_id: int | None = None
        if chat_type == "channel":
            channel_placeholder_id = await self._send_message(
                chat_id,
                "✍️ ECHO sta scrivendo…",
                message_thread_id=message_thread_id,
            )
        try:
            history = list(self._buffer_for(chat_id))
            record = await pipeline.interact(text, history=history)
            assistant_response = self._strip_user_echo_from_response(
                record.assistant_response,
                text,
            )

            chat_buffer = self._buffer_for(chat_id)
            chat_buffer.append({"role": "user", "content": text})
            chat_buffer.append({"role": "assistant", "content": assistant_response})

            send_kwargs: dict[str, int] = {}
            if message_thread_id is not None:
                send_kwargs["message_thread_id"] = message_thread_id

            # Keep typing visible for a short minimum interval; otherwise on fast
            # responses Telegram clients may not render the indicator at all.
            elapsed = time.monotonic() - typing_started_at
            remaining = self._typing_min_visible_seconds - elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)

            sent_via_placeholder_edit = False
            if (
                channel_placeholder_id is not None
                and len((assistant_response or "").strip()) <= 4096
            ):
                sent_via_placeholder_edit = await self._edit_message_text(
                    chat_id,
                    channel_placeholder_id,
                    assistant_response,
                )

            if not sent_via_placeholder_edit:
                if channel_placeholder_id is not None:
                    with suppress(Exception):
                        await self._delete_message(chat_id, channel_placeholder_id)
                await self._send_long_message(chat_id, assistant_response, **send_kwargs)

        except Exception as exc:  # noqa: BLE001
            logger.error("Telegram message handling failed: %s", exc, exc_info=True)
            if channel_placeholder_id is not None:
                edited = await self._edit_message_text(
                    chat_id,
                    channel_placeholder_id,
                    "⚠️ Errore interno ECHO. Riprova tra poco.",
                )
                if not edited:
                    with suppress(Exception):
                        await self._delete_message(chat_id, channel_placeholder_id)
                    await self._send_message(
                        chat_id,
                        "⚠️ Errore interno ECHO. Riprova tra poco.",
                        message_thread_id=message_thread_id,
                    )
            else:
                await self._send_message(
                    chat_id,
                    "⚠️ Errore interno ECHO. Riprova tra poco.",
                    message_thread_id=message_thread_id,
                )
        finally:
            typing_task.cancel()
            with suppress(asyncio.CancelledError):
                await typing_task
            with suppress(Exception):
                await read_ack_task

    async def _send_long_message(
        self,
        chat_id: int,
        text: str,
        *,
        message_thread_id: int | None = None,
        reply_to_message_id: int | None = None,
    ) -> None:
        cleaned = text.strip() if text else ""
        if not cleaned:
            cleaned = "(nessuna risposta)"

        is_first = True
        for chunk in self._split_text(cleaned, self._max_reply_chars):
            await self._send_message(
                chat_id,
                chunk,
                message_thread_id=message_thread_id,
                reply_to_message_id=reply_to_message_id if is_first else None,
            )
            is_first = False

    async def _send_message(
        self,
        chat_id: int,
        text: str,
        *,
        message_thread_id: int | None = None,
        reply_to_message_id: int | None = None,
    ) -> int | None:
        if self._client is None:
            return None

        payload = {
            "chat_id": chat_id,
            "text": text[:4096],
        }
        if message_thread_id is not None:
            payload["message_thread_id"] = message_thread_id
        if reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id
            payload["allow_sending_without_reply"] = True

        response = await self._client.post(f"{self._base_url}/sendMessage", json=payload)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok", False):
            raise RuntimeError(f"Telegram sendMessage failed for chat_id={chat_id}: {data}")

        result = data.get("result")
        message_id = result.get("message_id") if isinstance(result, dict) else None
        logger.info(
            "Telegram sendMessage ok chat_id=%s message_id=%s chars=%s",
            chat_id,
            message_id,
            len(payload.get("text", "")),
        )
        try:
            return int(message_id) if message_id is not None else None
        except (TypeError, ValueError):
            return None

    async def _send_chat_action(
        self,
        chat_id: int,
        *,
        action: str = "typing",
        message_thread_id: int | None = None,
    ) -> None:
        if self._client is None:
            return

        payload: dict[str, Any] = {"chat_id": chat_id, "action": action}
        if message_thread_id is not None:
            payload["message_thread_id"] = message_thread_id

        response = await self._client.post(f"{self._base_url}/sendChatAction", json=payload)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok", False):
            logger.warning("Telegram sendChatAction failed for chat_id=%s: %s", chat_id, data)

    async def _edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
    ) -> bool:
        if self._client is None:
            return False

        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": (text or "").strip()[:4096] or "(nessuna risposta)",
        }

        try:
            response = await self._client.post(
                f"{self._base_url}/editMessageText",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            if not data.get("ok", False):
                logger.debug(
                    "Telegram editMessageText non-ok for chat_id=%s message_id=%s: %s",
                    chat_id,
                    message_id,
                    data,
                )
                return False
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Telegram editMessageText failed for chat_id=%s message_id=%s: %s",
                chat_id,
                message_id,
                exc,
            )
            return False

    async def _delete_message(self, chat_id: int, message_id: int) -> bool:
        if self._client is None:
            return False
        try:
            response = await self._client.post(
                f"{self._base_url}/deleteMessage",
                json={"chat_id": chat_id, "message_id": message_id},
            )
            response.raise_for_status()
            data = response.json()
            return bool(data.get("ok", False))
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Telegram deleteMessage failed for chat_id=%s message_id=%s: %s",
                chat_id,
                message_id,
                exc,
            )
            return False

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
