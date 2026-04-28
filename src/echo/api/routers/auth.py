"""GitHub OAuth2 Device Flow endpoints (RFC 8628)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ── In-memory state ────────────────────────────────────────────────────────
_github_token: str | None = None
_github_username: str | None = None
_github_avatar: str | None = None
_copilot_available: bool = False

AUTH_FILE = Path("data/auth.json")

GITHUB_DEVICE_URL = "https://github.com/login/device/code"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API = "https://api.github.com"


# ── Persistence ────────────────────────────────────────────────────────────

def _load_persisted() -> None:
    global _github_token, _github_username, _github_avatar, _copilot_available
    if AUTH_FILE.exists():
        try:
            data = json.loads(AUTH_FILE.read_text())
            _github_token = data.get("token")
            _github_username = data.get("username")
            _github_avatar = data.get("avatar")
            _copilot_available = data.get("copilot_available", False)
            logger.info("Loaded persisted auth for user: %s", _github_username)
        except Exception as exc:
            logger.warning("Failed to load auth.json: %s", exc)


def _save_persisted() -> None:
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTH_FILE.write_text(
        json.dumps(
            {
                "token": _github_token,
                "username": _github_username,
                "avatar": _github_avatar,
                "copilot_available": _copilot_available,
            },
            indent=2,
        )
    )


# Load auth state at import time
_load_persisted()


# ── Request / Response models ──────────────────────────────────────────────

class DeviceStartRequest(BaseModel):
    client_id: str
    scope: str = "read:user"


class DeviceStartResponse(BaseModel):
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


class DevicePollRequest(BaseModel):
    device_code: str
    client_id: str


class DevicePollResponse(BaseModel):
    status: str  # "pending" | "success" | "error"
    message: str | None = None
    username: str | None = None
    avatar_url: str | None = None
    copilot_available: bool = False


class AuthStatusResponse(BaseModel):
    github_connected: bool
    github_username: str | None = None
    github_avatar: str | None = None
    copilot_available: bool = False


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/status", response_model=AuthStatusResponse)
async def auth_status() -> AuthStatusResponse:
    """Return current GitHub authentication status."""
    return AuthStatusResponse(
        github_connected=_github_token is not None,
        github_username=_github_username,
        github_avatar=_github_avatar,
        copilot_available=_copilot_available,
    )


@router.post("/github/device/start", response_model=DeviceStartResponse)
async def device_start(req: DeviceStartRequest) -> DeviceStartResponse:
    """Initiate the GitHub device-code flow. Returns the user_code to display."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GITHUB_DEVICE_URL,
            data={"client_id": req.client_id, "scope": req.scope},
            headers={"Accept": "application/json"},
            timeout=15,
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail=f"GitHub returned {resp.status_code}: {resp.text}")

    data = resp.json()
    if "error" in data:
        raise HTTPException(
            status_code=400,
            detail=data.get("error_description", data["error"]),
        )

    return DeviceStartResponse(
        device_code=data["device_code"],
        user_code=data["user_code"],
        verification_uri=data["verification_uri"],
        expires_in=data.get("expires_in", 900),
        interval=data.get("interval", 5),
    )


@router.post("/github/device/poll", response_model=DevicePollResponse)
async def device_poll(req: DevicePollRequest) -> DevicePollResponse:
    """Poll GitHub for the access token. Call this every `interval` seconds."""
    global _github_token, _github_username, _github_avatar, _copilot_available

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": req.client_id,
                "device_code": req.device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            headers={"Accept": "application/json"},
            timeout=15,
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail=f"GitHub returned {resp.status_code}: {resp.text}")

    data = resp.json()
    error = data.get("error")

    if error == "authorization_pending":
        return DevicePollResponse(status="pending", message="Waiting for authorization…")
    elif error == "slow_down":
        return DevicePollResponse(status="pending", message="Slow down — polling too fast")
    elif error == "expired_token":
        return DevicePollResponse(status="error", message="Device code expired. Please restart the flow.")
    elif error == "access_denied":
        return DevicePollResponse(status="error", message="Access denied by user.")
    elif error:
        return DevicePollResponse(status="error", message=data.get("error_description", error))

    token = data.get("access_token")
    if not token:
        return DevicePollResponse(status="error", message="No access token received.")

    # ── Fetch user info ────────────────────────────────────────────────────
    username: str | None = None
    avatar: str | None = None
    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            f"{GITHUB_API}/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=10,
        )
        if user_resp.status_code == 200:
            user_data = user_resp.json()
            username = user_data.get("login")
            avatar = user_data.get("avatar_url")

    # ── Check Copilot access ───────────────────────────────────────────────
    copilot = False
    async with httpx.AsyncClient() as client:
        cop_resp = await client.get(
            f"{GITHUB_API}/user/copilot_billing",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=10,
        )
        copilot = cop_resp.status_code == 200

    # ── Persist ────────────────────────────────────────────────────────────
    _github_token = token
    _github_username = username
    _github_avatar = avatar
    _copilot_available = copilot
    _save_persisted()

    logger.info("GitHub auth complete: user=%s copilot=%s", username, copilot)

    return DevicePollResponse(
        status="success",
        username=username,
        avatar_url=avatar,
        copilot_available=copilot,
    )


@router.delete("/github")
async def revoke_github() -> dict:
    """Clear stored GitHub credentials."""
    global _github_token, _github_username, _github_avatar, _copilot_available
    _github_token = None
    _github_username = None
    _github_avatar = None
    _copilot_available = False
    if AUTH_FILE.exists():
        AUTH_FILE.unlink()
    return {"status": "disconnected"}
