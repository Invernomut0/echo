"""Goals API router — /api/goals"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from echo.memory.goals import goal_store, MAX_ACTIVE_GOALS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/goals", tags=["goals"])


# ── Pydantic models ───────────────────────────────────────────────────────────

class CreateGoalRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    priority: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)


class UpdateGoalRequest(BaseModel):
    status: Literal["active", "achieved", "abandoned"] | None = None
    description: str | None = None


class AddActionRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=500)
    result: str = Field(default="", max_length=1000)
    status: Literal["done", "failed", "pending"] = "done"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_goals() -> dict:
    """Return active goals and history."""
    active = await goal_store.list_active()
    history = await goal_store.list_history(limit=50)
    return {
        "active": active,
        "history": history,
        "max_active": MAX_ACTIVE_GOALS,
    }


@router.post("", status_code=201)
async def create_goal(payload: CreateGoalRequest) -> dict:
    """Create a new active goal (max 5 active at a time)."""
    try:
        goal = await goal_store.create(
            title=payload.title,
            description=payload.description,
            priority=payload.priority,
            tags=payload.tags,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return goal


@router.get("/{goal_id}")
async def get_goal(goal_id: str) -> dict:
    goal = await goal_store.get(goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


@router.patch("/{goal_id}")
async def update_goal(goal_id: str, payload: UpdateGoalRequest) -> dict:
    """Update goal status and/or description."""
    goal = await goal_store.update_status(
        goal_id,
        status=payload.status or (await goal_store.get(goal_id) or {}).get("status", "active"),
        description=payload.description,
    )
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


@router.delete("/{goal_id}", status_code=204)
async def delete_goal(goal_id: str) -> None:
    deleted = await goal_store.delete(goal_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Goal not found")


@router.post("/{goal_id}/actions", status_code=201)
async def add_action(goal_id: str, payload: AddActionRequest) -> dict:
    """Append an action step to a goal."""
    goal = await goal_store.get(goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    action = await goal_store.add_action(
        goal_id=goal_id,
        description=payload.description,
        result=payload.result,
        status=payload.status,
    )
    return action
