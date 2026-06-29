"""Setup and configuration API router.

Exposes endpoints for:
- Reading / updating .env-backed settings (LM Studio, GitHub OAuth)
- Initiating the GitHub OAuth Device Authorization Flow
- Polling GitHub for the resulting access token
- Fetching a GitHub Copilot API token from the GitHub REST API
- Testing the LM Studio connection
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from echo.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/setup", tags=["setup"])

# .env location (resolved relative to the project root where uvicorn is launched)
ENV_PATH = Path(".env")

# VS Code's GitHub OAuth App — same client used by the official Copilot extension.
# Public device-flow client, no secret required.
VSCODE_CLIENT_ID = "Iv1.b507a08c87ecfe98"
VSCODE_SCOPE = ""  # empty scope is what VS Code Copilot uses

# ── Copilot token cache ───────────────────────────────────────────────────────
# Avoids refetching the short-lived Copilot token on every request.
# Automatically refreshed when the token is within 60 seconds of expiry.

_copilot_token_cache: dict[str, str] = {}
_copilot_token_lock = asyncio.Lock()


def _parse_expires_at(value: object) -> datetime | None:
    """Parse Copilot expires_at accepting epoch seconds or ISO timestamps."""
    if value is None:
        return None

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            return None

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None

        if raw.isdigit():
            try:
                return datetime.fromtimestamp(float(raw), tz=timezone.utc)
            except Exception:
                return None

        iso = raw.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(iso)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            return None

    return None


async def _get_copilot_token_cached() -> dict:
    """Return a valid Copilot API token, auto-refreshing if nearly expired."""
    global _copilot_token_cache

    def _cached_if_fresh() -> dict | None:
        if _copilot_token_cache.get("token") and _copilot_token_cache.get("expires_at"):
            expires = _parse_expires_at(_copilot_token_cache.get("expires_at"))
            if expires is None:
                return None
            remaining = (expires - datetime.now(timezone.utc)).total_seconds()
            if remaining > 60:
                return _copilot_token_cache
            logger.debug("Copilot token expires in %.0fs — refreshing", remaining)
        return None

    fresh = _cached_if_fresh()
    if fresh is not None:
        return fresh

    # Prevent refresh stampede under concurrent requests.
    async with _copilot_token_lock:
        fresh = _cached_if_fresh()
        if fresh is not None:
            return fresh

        # Fetch a fresh token from GitHub
        gh_token = settings.github_token
        if not gh_token:
            raise HTTPException(
                status_code=400,
                detail="No GitHub token stored — complete the device flow first.",
            )

        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://api.github.com/copilot_internal/v2/token",
                headers={
                    "Authorization": f"token {gh_token}",
                    "Accept": "application/json",
                    "Editor-Version": "vscode/1.99.3",
                    "Editor-Plugin-Version": "copilot-chat/0.22.4",
                    "User-Agent": "GitHubCopilotChat/0.22.4",
                    "Copilot-Integration-Id": "vscode-chat",
                },
                timeout=15.0,
            )

        if r.status_code == 401:
            raise HTTPException(status_code=401, detail="GitHub token is invalid or expired.")
        if r.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"GitHub Copilot API returned HTTP {r.status_code}: {r.text}",
            )

        data = r.json()
        _copilot_token_cache = {
            "token": data.get("token", ""),
            "expires_at": data.get("expires_at", ""),
            "endpoint": data.get("endpoints", {}).get("api", "https://api.githubcopilot.com"),
        }
        logger.info("Copilot token refreshed, expires %s", _copilot_token_cache["expires_at"])
        return _copilot_token_cache


# ── Pydantic models ───────────────────────────────────────────────────────────


class ConfigPayload(BaseModel):
    lm_studio_base_url: str | None = None
    lm_studio_api_key: str | None = None
    lm_studio_model: str | None = None
    lm_studio_embedding_model: str | None = None
    github_token: str | None = None
    llm_provider: Literal["copilot", "lm_studio", "openai", "groq", "anthropic", "ollama", "opencode", "openrouter"] | None = None
    copilot_model: str | None = None
    # OpenCode
    opencode_api_key: str | None = None
    opencode_model: str | None = None
    opencode_base_url: str | None = None
    # OpenRouter
    openrouter_api_key: str | None = None
    openrouter_model: str | None = None
    openrouter_base_url: str | None = None
    # OpenAI
    openai_api_key: str | None = None
    openai_model: str | None = None
    openai_base_url: str | None = None
    # Groq
    groq_api_key: str | None = None
    groq_model: str | None = None
    # Anthropic
    anthropic_api_key: str | None = None
    anthropic_model: str | None = None
    # Ollama chat
    ollama_chat_model: str | None = None
    ollama_base_url: str | None = None
    # Telegram bot integration
    telegram_enabled: bool | None = None
    telegram_bot_token: str | None = None
    telegram_api_base_url: str | None = None
    telegram_poll_interval_seconds: float | None = None
    telegram_update_timeout_seconds: int | None = None
    telegram_request_timeout_seconds: float | None = None
    telegram_allowed_chat_ids: list[int] | None = None
    telegram_history_turns: int | None = None
    telegram_max_reply_chars: int | None = None


class PollRequest(BaseModel):
    device_code: str


class TelegramTestPayload(BaseModel):
    bot_token: str | None = None
    api_base_url: str | None = None


# ── Helper ────────────────────────────────────────────────────────────────────


def _set_env_key(key: str, value: str) -> None:
    """Update (or append) a single key in the .env file."""
    try:
        from dotenv import set_key  # python-dotenv is already a dependency

        set_key(str(ENV_PATH), key, value, quote_mode="never")
    except Exception as exc:
        logger.warning("Could not write to .env: %s", exc)


def _to_env_value(value: object) -> str:
    """Convert payload values to deterministic string form for .env storage."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set, dict)):
        return json.dumps(value)
    return str(value)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/config")
async def get_config() -> dict:
    """Return current configuration (secrets masked)."""
    return {
        "lm_studio_base_url": settings.lm_studio_base_url,
        "lm_studio_api_key": settings.lm_studio_api_key,
        "lm_studio_model": settings.lm_studio_model,
        "lm_studio_embedding_model": settings.lm_studio_embedding_model,
        "llm_provider": settings.llm_provider,
        "copilot_model": settings.copilot_model,
        # OpenCode
        "opencode_api_key": "***" if settings.opencode_api_key else "",
        "opencode_model": settings.opencode_model,
        "opencode_base_url": settings.opencode_base_url,
        # OpenRouter
        "openrouter_api_key": "***" if settings.openrouter_api_key else "",
        "openrouter_model": settings.openrouter_model,
        "openrouter_base_url": settings.openrouter_base_url,
        # OpenAI
        "openai_api_key": "***" if settings.openai_api_key else "",
        "openai_model": settings.openai_model,
        "openai_base_url": settings.openai_base_url,
        # Groq
        "groq_api_key": "***" if settings.groq_api_key else "",
        "groq_model": settings.groq_model,
        # Anthropic
        "anthropic_api_key": "***" if settings.anthropic_api_key else "",
        "anthropic_model": settings.anthropic_model,
        # Ollama chat
        "ollama_chat_model": settings.ollama_chat_model,
        "ollama_base_url": settings.ollama_base_url,
        # Telegram
        "telegram_enabled": settings.telegram_enabled,
        "telegram_bot_token": "***" if settings.telegram_bot_token else "",
        "telegram_api_base_url": settings.telegram_api_base_url,
        "telegram_poll_interval_seconds": settings.telegram_poll_interval_seconds,
        "telegram_update_timeout_seconds": settings.telegram_update_timeout_seconds,
        "telegram_request_timeout_seconds": settings.telegram_request_timeout_seconds,
        "telegram_allowed_chat_ids": settings.telegram_allowed_chat_ids,
        "telegram_history_turns": settings.telegram_history_turns,
        "telegram_max_reply_chars": settings.telegram_max_reply_chars,
        "has_telegram_token": bool(settings.telegram_bot_token),
        # Never return the actual token value to the frontend
        "has_github_token": bool(settings.github_token),
    }


@router.put("/config")
async def save_config(payload: ConfigPayload, request: Request) -> dict:
    """Persist updated config values to .env and reload in-process settings."""
    mapping: dict[str, str | None] = {
        "LM_STUDIO_BASE_URL": payload.lm_studio_base_url,
        "LM_STUDIO_API_KEY": payload.lm_studio_api_key,
        "LM_STUDIO_MODEL": payload.lm_studio_model,
        "LM_STUDIO_EMBEDDING_MODEL": payload.lm_studio_embedding_model,
        "GITHUB_TOKEN": payload.github_token,
        "LLM_PROVIDER": payload.llm_provider,
        "COPILOT_MODEL": payload.copilot_model,
        "OPENCODE_API_KEY": payload.opencode_api_key,
        "OPENCODE_MODEL": payload.opencode_model,
        "OPENCODE_BASE_URL": payload.opencode_base_url,
        "OPENROUTER_API_KEY": payload.openrouter_api_key,
        "OPENROUTER_MODEL": payload.openrouter_model,
        "OPENROUTER_BASE_URL": payload.openrouter_base_url,
        "OPENAI_API_KEY": payload.openai_api_key,
        "OPENAI_MODEL": payload.openai_model,
        "OPENAI_BASE_URL": payload.openai_base_url,
        "GROQ_API_KEY": payload.groq_api_key,
        "GROQ_MODEL": payload.groq_model,
        "ANTHROPIC_API_KEY": payload.anthropic_api_key,
        "ANTHROPIC_MODEL": payload.anthropic_model,
        "OLLAMA_CHAT_MODEL": payload.ollama_chat_model,
        "OLLAMA_BASE_URL": payload.ollama_base_url,
        "TELEGRAM_ENABLED": payload.telegram_enabled,
        "TELEGRAM_BOT_TOKEN": payload.telegram_bot_token,
        "TELEGRAM_API_BASE_URL": payload.telegram_api_base_url,
        "TELEGRAM_POLL_INTERVAL_SECONDS": payload.telegram_poll_interval_seconds,
        "TELEGRAM_UPDATE_TIMEOUT_SECONDS": payload.telegram_update_timeout_seconds,
        "TELEGRAM_REQUEST_TIMEOUT_SECONDS": payload.telegram_request_timeout_seconds,
        "TELEGRAM_ALLOWED_CHAT_IDS": payload.telegram_allowed_chat_ids,
        "TELEGRAM_HISTORY_TURNS": payload.telegram_history_turns,
        "TELEGRAM_MAX_REPLY_CHARS": payload.telegram_max_reply_chars,
    }

    for env_key, value in mapping.items():
        if value is not None:
            _set_env_key(env_key, _to_env_value(value))

    # Hot-reload the singleton so subsequent API calls see new values
    _reload_settings()
    telegram_runtime = await _apply_telegram_bridge_runtime(request)

    return {"ok": True, "telegram_runtime": telegram_runtime}


def _reload_settings() -> None:
    """Re-read .env into the global settings singleton (best-effort)."""
    try:
        new = settings.__class__()
        for field in settings.model_fields:
            object.__setattr__(settings, field, getattr(new, field))
    except Exception as exc:
        logger.warning("Settings hot-reload failed: %s", exc)


async def _apply_telegram_bridge_runtime(request: Request) -> str:
    """Apply Telegram bridge config immediately to the running FastAPI app."""
    app = request.app
    existing_bridge = getattr(app.state, "telegram_bridge", None)

    if existing_bridge is not None:
        try:
            await existing_bridge.stop()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed stopping existing Telegram bridge: %s", exc)
        finally:
            app.state.telegram_bridge = None

    if not settings.telegram_enabled:
        logger.info("Telegram bridge runtime apply: disabled")
        return "disabled"

    if not settings.telegram_bot_token.strip():
        logger.warning(
            "Telegram enabled in config but token is empty — bridge remains stopped"
        )
        return "enabled_without_token"

    try:
        from echo.integrations.telegram_bot import TelegramBotBridge  # noqa: PLC0415

        bridge = TelegramBotBridge()
        bridge.start()
        app.state.telegram_bridge = bridge
        logger.info("Telegram bridge runtime apply: running")
        return "running"
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to apply Telegram bridge runtime config: %s", exc, exc_info=True)
        return f"error: {exc}"


# ── GitHub Device Authorization Flow ─────────────────────────────────────────


@router.post("/github/device")
async def start_device_flow() -> dict:
    """
    Initiate the GitHub OAuth device authorization flow.

    Uses VS Code's public GitHub OAuth App (client ID Iv1.b507a08c87ecfe98),
    the same used by the official GitHub Copilot extension — no secret required.

    Returns device_code, user_code, verification_uri, expires_in, interval.
    The caller should display user_code + verification_uri to the user and
    then begin polling /github/poll until a token is received.
    """
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://github.com/login/device/code",
            data={"client_id": VSCODE_CLIENT_ID, "scope": VSCODE_SCOPE},
            headers={"Accept": "application/json"},
            timeout=15.0,
        )

    if r.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub returned HTTP {r.status_code}: {r.text}",
        )

    data = r.json()
    if "error" in data:
        raise HTTPException(
            status_code=400,
            detail=data.get("error_description", data["error"]),
        )

    return data


@router.post("/github/poll")
async def poll_device_flow(req: PollRequest) -> dict:
    """
    Poll GitHub for the device flow access token.

    Returns either:
      - {"access_token": "...", "scope": "...", "token_type": "bearer"}  → success
      - {"error": "authorization_pending"}                               → keep polling
      - {"error": "slow_down"}                                           → increase interval
      - {"error": "expired_token"}                                       → restart flow
      - {"error": "access_denied"}                                       → user denied
    """
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": VSCODE_CLIENT_ID,
                "device_code": req.device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            headers={"Accept": "application/json"},
            timeout=15.0,
        )

    if r.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub returned HTTP {r.status_code}: {r.text}",
        )

    return r.json()


# ── GitHub Copilot Token ──────────────────────────────────────────────────────


@router.get("/github/copilot-token")
async def get_copilot_token() -> dict:
    """
    Exchange the stored GitHub OAuth token for a short-lived Copilot API token.

    The token is cached in memory and auto-refreshed when it nears expiry.
    The returned `endpoint` URL is the base URL for OpenAI-compatible Copilot completions.
    """
    return await _get_copilot_token_cached()


# ── Copilot connectivity test ─────────────────────────────────────────────────


@router.post("/copilot/test")
async def test_copilot_connection() -> dict:
    """
    Verify that the Copilot API is reachable and the stored token works.

    Automatically refreshes the Copilot token if it has expired.
    Returns { ok, model, error }.
    """
    # 1. Get (or refresh) the Copilot token
    try:
        token_data = await _get_copilot_token_cached()
    except HTTPException as exc:
        return {"ok": False, "error": exc.detail}

    # 2. Send a minimal chat completion to verify end-to-end connectivity
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{token_data['endpoint']}/chat/completions",
                headers={
                    "Authorization": f"Bearer {token_data['token']}",
                    "Content-Type": "application/json",
                    "Editor-Version": "vscode/1.99.3",
                    "Editor-Plugin-Version": "copilot-chat/0.22.4",
                    "User-Agent": "GitHubCopilotChat/0.22.4",
                    "Copilot-Integration-Id": "vscode-chat",
                },
                json={
                    "model": settings.copilot_model,
                    "messages": [{"role": "user", "content": "Reply with just the word 'ok'."}],
                    "max_tokens": 5,
                    "temperature": 0,
                },
                timeout=20.0,
            )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    if r.status_code == 401:
        # Stale token despite refresh — clear cache so next call re-fetches
        _copilot_token_cache.clear()
        return {"ok": False, "error": "Unauthorized — try reconnecting GitHub."}

    if r.status_code != 200:
        return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:300]}"}

    return {"ok": True, "model": settings.copilot_model}


# ── LM Studio Test ────────────────────────────────────────────────────────────


@router.post("/lmstudio/test")
async def test_lmstudio_connection(base_url: str | None = None) -> dict:
    """Probe LM Studio and return the list of loaded models."""
    url = (base_url or settings.lm_studio_base_url).rstrip("/")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{url}/models", timeout=5.0)
        if r.status_code == 200:
            models = [m["id"] for m in r.json().get("data", [])]
            return {"ok": True, "models": models}
        return {"ok": False, "error": f"HTTP {r.status_code}"}
    except httpx.ConnectError:
        return {"ok": False, "error": "Connection refused — is LM Studio running?"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.post("/telegram/test")
async def test_telegram_connection(payload: TelegramTestPayload) -> dict:
    """Verify Telegram bot API reachability and token validity via getMe."""
    bot_token = (payload.bot_token or settings.telegram_bot_token or "").strip()
    api_base_url = (payload.api_base_url or settings.telegram_api_base_url).rstrip("/")

    if not bot_token:
        return {"ok": False, "error": "Telegram bot token is empty."}

    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{api_base_url}/bot{bot_token}/getMe",
                timeout=10.0,
            )
    except httpx.ConnectError:
        return {"ok": False, "error": "Connection refused to Telegram API base URL."}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    if r.status_code != 200:
        return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}

    data = r.json()
    if not data.get("ok"):
        return {"ok": False, "error": data.get("description", "Telegram API error")}

    result = data.get("result", {})
    return {
        "ok": True,
        "bot_username": result.get("username", ""),
        "bot_name": result.get("first_name", ""),
    }
