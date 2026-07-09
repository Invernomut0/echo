"""SQLAlchemy ORM models and Pydantic schemas for the internal cron system."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from echo.core.db import Base

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(UTC)


def _uid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Task type registry
# ---------------------------------------------------------------------------

class TaskType:
    """Supported task types for cron jobs."""
    REFLECTION = "reflection"
    CONSOLIDATION_LIGHT = "consolidation_light"
    CONSOLIDATION_DEEP = "consolidation_deep"
    CURIOSITY_CYCLE = "curiosity_cycle"
    LLM_TASK = "llm_task"
    MEMORY_STORE = "memory_store"
    GOAL_REFLECT = "goal_reflect"
    SELF_MODIFICATION = "self_modification"   # calls SelfModificationEngine directly

    ALL: list[str] = [
        REFLECTION,
        CONSOLIDATION_LIGHT,
        CONSOLIDATION_DEEP,
        CURIOSITY_CYCLE,
        LLM_TASK,
        MEMORY_STORE,
        GOAL_REFLECT,
        SELF_MODIFICATION,
    ]


class ScheduleType:
    """Supported schedule types."""
    CRON = "cron"       # Standard cron expression: "0 */6 * * *"
    INTERVAL = "interval"  # Fixed interval in seconds: "3600"


# ---------------------------------------------------------------------------
# SQLAlchemy ORM
# ---------------------------------------------------------------------------

class CronTaskRow(Base):
    """Persistent cron task definition."""

    __tablename__ = "cron_tasks"

    id = Column(String(36), primary_key=True, default=_uid)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default="")

    # Scheduling
    schedule_type = Column(String(20), nullable=False, default=ScheduleType.INTERVAL)
    # For "cron": standard cron expression like "0 */6 * * *" (minute hour dom month dow)
    # For "interval": number of seconds as string, e.g. "3600"
    schedule = Column(String(200), nullable=False)

    # Execution
    task_type = Column(String(50), nullable=False)
    # JSON-serialised dict passed to the executor
    task_config = Column(Text, nullable=False, default="{}")

    enabled = Column(Boolean, nullable=False, default=True)

    # Tracking
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    run_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class CronRunRow(Base):
    """Execution history record for a cron task."""

    __tablename__ = "cron_runs"

    id = Column(String(36), primary_key=True, default=_uid)
    task_id = Column(String(36), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="running")  # running | success | error
    result = Column(Text, nullable=True)   # JSON-serialised result or error message
    duration_ms = Column(Integer, nullable=True)


# ---------------------------------------------------------------------------
# Pydantic schemas (API layer)
# ---------------------------------------------------------------------------

class CronTaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    schedule_type: str = Field(default=ScheduleType.INTERVAL)
    schedule: str = Field(..., description="Cron expression or interval seconds")
    task_type: str
    task_config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class CronTaskUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    schedule_type: str | None = None
    schedule: str | None = None
    task_type: str | None = None
    task_config: dict[str, Any] | None = None
    enabled: bool | None = None


class CronTaskSchema(BaseModel):
    id: str
    name: str
    description: str
    schedule_type: str
    schedule: str
    task_type: str
    task_config: dict[str, Any]
    enabled: bool
    last_run_at: datetime | None
    next_run_at: datetime | None
    run_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CronRunSchema(BaseModel):
    id: str
    task_id: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    result: Any | None
    duration_ms: int | None

    model_config = {"from_attributes": True}
