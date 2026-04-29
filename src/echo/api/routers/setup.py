"""Setup and configuration API router.

Exposes endpoints for:
- Reading / updating .env-backed settings (LM Studio, GitHub OAuth)
- Initiating the GitHub OAuth Device Authorization Flow
- Polling GitHub for the resulting access token
- Fetching a GitHub Copilot API token from the GitHub REST API
- Testing the LM Studio connection
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
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


async def _get_copilot_token_cached() -> dict:
    """Return a valid Copilot API token, auto-refreshing if nearly expired."""
    global _copilot_token_cache

    # Return cached token if it still has > 60 s of life
    if _copilot_token_cache.get("token") and _copilot_token_cache.get("expires_at"):
        try:
            expires = datetime.fromisoformat(_copilot_token_cache["expires_at"])
            remaining = (expires - datetime.now(timezone.utc)).total_seconds()
            if remaining > 60:
                return _copilot_token_cache
            logger.debug("Copilot token expires in %.0fs — refreshing", remaining)
        except Exception:
            pass  # bad cache entry → fall through to refetch

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
    llm_provider: Literal["copilot", "lm_studio"] | None = None
    copilot_model: str | None = None


class PollRequest(BaseModel):
    device_code: str


# ── Helper ────────────────────────────────────────────────────────────────────


def _set_env_key(key: str, value: str) -> None:
    """Update (or append) a single key in the .env file."""
    try:
        from dotenv import set_key  # python-dotenv is already a dependency

        set_key(str(ENV_PATH), key, value, quote_mode="never")
    except Exception as exc:
        logger.warning("Could not write to .env: %s", exc)


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
        # Never return the actual token value to the frontend
        "has_github_token": bool(settings.github_token),
    }


@router.put("/config")
async def save_config(payload: ConfigPayload) -> dict:
    """Persist updated config values to .env and reload in-process settings."""
    mapping: dict[str, str | None] = {
        "LM_STUDIO_BASE_URL": payload.lm_studio_base_url,
        "LM_STUDIO_API_KEY": payload.lm_studio_api_key,
        "LM_STUDIO_MODEL": payload.lm_studio_model,
        "LM_STUDIO_EMBEDDING_MODEL": payload.lm_studio_embedding_model,
        "GITHUB_TOKEN": payload.github_token,
        "LLM_PROVIDER": payload.llm_provider,
        "COPILOT_MODEL": payload.copilot_model,
    }

    for env_key, value in mapping.items():
        if value is not None:
            _set_env_key(env_key, value)

    # Hot-reload the singleton so subsequent API calls see new values
    _reload_settings()

    return {"ok": True}


def _reload_settings() -> None:
    """Re-read .env into the global settings singleton (best-effort)."""
    try:
        new = settings.__class__()
        for field in settings.model_fields:
            object.__setattr__(settings, field, getattr(new, field))
    except Exception as exc:
        logger.warning("Settings hot-reload failed: %s", exc)


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
