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
    status: Literal["done", "failed", "pending"] = "pending"


class UpdateActionRequest(BaseModel):
    status: Literal["done", "failed", "pending"]
    result: str | None = None


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
    """Update goal status and/or description.

    When status transitions to 'achieved', the goal and all its done actions
    are automatically distilled into a semantic memory and optionally a wiki page.
    """
    # Snapshot before the update so we can detect the achieved transition
    prev = await goal_store.get(goal_id)
    if prev is None:
        raise HTTPException(status_code=404, detail="Goal not found")

    goal = await goal_store.update_status(
        goal_id,
        status=payload.status or prev.get("status", "active"),
        description=payload.description,
    )
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")

    # Auto-consolidate achieved goals into semantic memory
    if payload.status == "achieved" and prev.get("status") != "achieved":
        try:
            await _consolidate_achieved_goal(goal)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Goal consolidation to semantic failed: %s", exc)

    return goal


async def _consolidate_achieved_goal(goal: dict) -> None:
    """Distil an achieved goal + its actions into a semantic memory.

    Builds a structured summary and stores it in the semantic memory store
    with high salience so it persists across decay cycles.
    """
    import json as _json
    from echo.memory.semantic import SemanticMemoryStore

    actions = goal.get("actions", [])
    done_actions = [a for a in actions if a.get("status") == "done"]

    # Build a rich narrative summary
    lines = [
        f"Goal achieved: {goal['title']}",
    ]
    if goal.get("description"):
        lines.append(f"Description: {goal['description']}")
    if done_actions:
        lines.append("Completed steps:")
        for a in done_actions:
            step_line = f"  - {a['description']}"
            if a.get("result"):
                step_line += f" → {a['result']}"
            lines.append(step_line)

    content = "\n".join(lines)
    tags = ["goal_achieved"] + goal.get("tags", [])
    # Priority feeds salience: high-priority goals produce high-salience memories
    salience = 0.7 + goal.get("priority", 0.5) * 0.25  # range 0.70–0.95

    semantic = SemanticMemoryStore()
    await semantic.store(content=content, tags=tags, salience=round(salience, 3))
    logger.info(
        "Achieved goal '%s' consolidated → semantic memory (salience=%.3f, actions=%d)",
        goal["title"], salience, len(done_actions),
    )


@router.delete("/{goal_id}", status_code=204)
async def delete_goal(goal_id: str) -> None:
    deleted = await goal_store.delete(goal_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Goal not found")


@router.post("/{goal_id}/actions", status_code=201)
async def add_action(goal_id: str, payload: AddActionRequest) -> dict:
    """Append an action step to a goal (pending by default)."""
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


@router.patch("/{goal_id}/actions/{action_id}")
async def update_action(goal_id: str, action_id: str, payload: UpdateActionRequest) -> dict:
    """Update an action's status (mark done/failed/pending)."""
    action = await goal_store.update_action(
        action_id=action_id,
        status=payload.status,
        result=payload.result,
    )
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")
    return action
