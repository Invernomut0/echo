"""Cron API router — /api/cron."""

from __future__ import annotations

import contextlib
import json
from typing import Any

from fastapi import APIRouter, HTTPException

from echo.core.pipeline import pipeline
from echo.cron.models import (
    CronRunSchema,
    CronTaskCreate,
    CronTaskSchema,
    CronTaskUpdate,
    ScheduleType,
    TaskType,
)

router = APIRouter(prefix="/api/cron", tags=["cron"])


def _task_to_schema(row) -> CronTaskSchema:
    """Convert a CronTaskRow ORM object to the Pydantic schema."""
    config: dict[str, Any] = {}
    with contextlib.suppress(json.JSONDecodeError, TypeError):
        config = json.loads(row.task_config or "{}")
    return CronTaskSchema(
        id=row.id,
        name=row.name,
        description=row.description or "",
        schedule_type=row.schedule_type,
        schedule=row.schedule,
        task_type=row.task_type,
        task_config=config,
        enabled=row.enabled,
        last_run_at=row.last_run_at,
        next_run_at=row.next_run_at,
        run_count=row.run_count or 0,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _run_to_schema(row) -> CronRunSchema:
    result = None
    try:
        result = json.loads(row.result) if row.result else None
    except (json.JSONDecodeError, TypeError):
        result = row.result
    return CronRunSchema(
        id=row.id,
        task_id=row.task_id,
        started_at=row.started_at,
        finished_at=row.finished_at,
        status=row.status,
        result=result,
        duration_ms=row.duration_ms,
    )


# ---------------------------------------------------------------------------
# Metadata endpoints
# ---------------------------------------------------------------------------

@router.get("/task-types")
async def list_task_types() -> dict[str, Any]:
    """Return supported task types with descriptions."""
    return {
        "task_types": [
            {
                "type": TaskType.REFLECTION,
                "description": (
                    "Trigger a manual reflection cycle — ECHO reviews recent"
                    " memories and updates beliefs."
                ),
                "config_example": {
                    "trigger_input": "Review recent experiences.",
                    "memory_limit": 5,
                },
            },
            {
                "type": TaskType.CONSOLIDATION_LIGHT,
                "description": (
                    "Trigger a light consolidation cycle"
                    " (memory decay, dedup, pattern extraction)."
                ),
                "config_example": {},
            },
            {
                "type": TaskType.CONSOLIDATION_DEEP,
                "description": (
                    "Trigger a full deep/REM consolidation cycle"
                    " including dream generation."
                ),
                "config_example": {},
            },
            {
                "type": TaskType.CURIOSITY_CYCLE,
                "description": (
                    "Trigger an autonomous curiosity exploration cycle"
                    " (web/arxiv research)."
                ),
                "config_example": {"force": True},
            },
            {
                "type": TaskType.LLM_TASK,
                "description": (
                    "Execute an arbitrary LLM prompt and optionally"
                    " store the result as a memory."
                ),
                "config_example": {
                    "prompt": "Reflect on recent events and generate a short insight.",
                    "system_prompt": "You are ECHO, a cognitive AI.",
                    "store_as_memory": True,
                    "memory_tags": ["cron", "insight"],
                    "temperature": 0.7,
                    "max_tokens": 512,
                },
            },
            {
                "type": TaskType.MEMORY_STORE,
                "description": "Store a fixed memory entry on every execution.",
                "config_example": {
                    "content": "Periodic reminder: maintain coherence between beliefs.",
                    "importance": 0.6,
                    "tags": ["cron", "reminder"],
                },
            },
            {
                "type": TaskType.GOAL_REFLECT,
                "description": (
                    "Trigger goal reflection — ECHO reviews active goals"
                    " and plans next actions."
                ),
                "config_example": {"max_goals": 3},
            },
        ],
        "schedule_types": [
            {
                "type": ScheduleType.INTERVAL,
                "description": "Fixed interval in seconds. Example: '3600' for every hour.",
                "example": "3600",
            },
            {
                "type": ScheduleType.CRON,
                "description": (
                    "Standard 5-field cron expression (minute hour dom month dow)."
                    " Example: '0 */6 * * *' for every 6 hours."
                ),
                "example": "0 */6 * * *",
            },
        ],
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("/tasks", response_model=list[CronTaskSchema])
async def list_tasks() -> list[CronTaskSchema]:
    """List all cron tasks."""
    tasks = await pipeline.cron.list_tasks()
    return [_task_to_schema(t) for t in tasks]


@router.post("/tasks", response_model=CronTaskSchema, status_code=201)
async def create_task(body: CronTaskCreate) -> CronTaskSchema:
    """Create a new cron task."""
    try:
        row = await pipeline.cron.create_task(
            name=body.name,
            description=body.description,
            schedule_type=body.schedule_type,
            schedule=body.schedule,
            task_type=body.task_type,
            task_config=body.task_config,
            enabled=body.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _task_to_schema(row)


@router.get("/tasks/{task_id}", response_model=CronTaskSchema)
async def get_task(task_id: str) -> CronTaskSchema:
    """Get a specific cron task."""
    try:
        row = await pipeline.cron.get_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _task_to_schema(row)


@router.put("/tasks/{task_id}", response_model=CronTaskSchema)
async def update_task(task_id: str, body: CronTaskUpdate) -> CronTaskSchema:
    """Update a cron task. Only provided fields are updated."""
    update_fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=422, detail="No fields to update")
    try:
        row = await pipeline.cron.update_task(task_id, **update_fields)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _task_to_schema(row)


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: str) -> None:
    """Delete a cron task permanently."""
    try:
        await pipeline.cron.delete_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Enable / Disable
# ---------------------------------------------------------------------------

@router.post("/tasks/{task_id}/enable", response_model=CronTaskSchema)
async def enable_task(task_id: str) -> CronTaskSchema:
    """Enable a disabled task."""
    try:
        row = await pipeline.cron.update_task(task_id, enabled=True)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _task_to_schema(row)


@router.post("/tasks/{task_id}/disable", response_model=CronTaskSchema)
async def disable_task(task_id: str) -> CronTaskSchema:
    """Disable a task without deleting it."""
    try:
        row = await pipeline.cron.update_task(task_id, enabled=False)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _task_to_schema(row)


# ---------------------------------------------------------------------------
# Manual trigger
# ---------------------------------------------------------------------------

@router.post("/tasks/{task_id}/trigger")
async def trigger_task(task_id: str) -> dict[str, Any]:
    """Manually execute a cron task immediately, outside its schedule."""
    try:
        result = await pipeline.cron.trigger_now(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "ok", "result": result}


# ---------------------------------------------------------------------------
# Run history
# ---------------------------------------------------------------------------

@router.get("/tasks/{task_id}/runs", response_model=list[CronRunSchema])
async def get_runs(task_id: str, limit: int = 50) -> list[CronRunSchema]:
    """Get the execution history for a cron task."""
    try:
        await pipeline.cron.get_task(task_id)  # 404 if not found
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    runs = await pipeline.cron.get_runs(task_id, limit=min(limit, 200))
    return [_run_to_schema(r) for r in runs]
