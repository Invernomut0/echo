"""CronScheduler — APScheduler-backed persistent cron engine for ECHO.

Tasks are stored in SQLite (CronTaskRow) and dynamically registered with
APScheduler's AsyncIOScheduler.  Each execution creates a CronRunRow record
for full history and observability.

Schedule formats:
  - "cron"     → standard cron expression "minute hour dom month dow"
                 e.g. "0 */6 * * *"  (every 6 hours)
  - "interval" → fixed number of seconds as a string
                 e.g. "3600"  (every hour)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from echo.core.db import get_session_factory
from echo.cron.models import CronRunRow, CronTaskRow, ScheduleType

if TYPE_CHECKING:
    from echo.core.pipeline import CognitivePipeline

logger = logging.getLogger(__name__)


class CronScheduler:
    """Manages persistent recurring tasks for ECHO using APScheduler."""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler(timezone="UTC")
        self._pipeline: CognitivePipeline | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def attach_pipeline(self, pipeline: CognitivePipeline) -> None:
        """Bind the scheduler to the cognitive pipeline after it's created."""
        self._pipeline = pipeline

    async def _migrate_task_types(self) -> None:
        """One-time migration: convert known llm_task entries to proper types."""
        from echo.cron.models import CronTaskRow, TaskType  # noqa: PLC0415
        from echo.core.db import get_session_factory  # noqa: PLC0415
        from sqlalchemy import select  # noqa: PLC0415

        MIGRATIONS = {
            # title pattern → new task_type
            "self-modification": TaskType.SELF_MODIFICATION,
            "self modification": TaskType.SELF_MODIFICATION,
            "selfmod": TaskType.SELF_MODIFICATION,
        }
        factory = get_session_factory()
        try:
            async with factory() as session:
                rows = (await session.execute(
                    select(CronTaskRow).where(CronTaskRow.task_type == TaskType.LLM_TASK)
                )).scalars().all()
                changed = 0
                for row in rows:
                    title_lower = row.name.lower()
                    for pattern, new_type in MIGRATIONS.items():
                        if pattern in title_lower:
                            logger.info(
                                "Migrating cron task '%s': llm_task → %s",
                                row.name, new_type,
                            )
                            row.task_type = new_type
                            changed += 1
                            break
                if changed:
                    await session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cron task type migration failed: %s", exc)

    async def startup(self) -> None:
        """Load all enabled tasks from DB and start the APScheduler."""
        if self._running:
            return
        await self._migrate_task_types()
        self._scheduler.start()
        self._running = True

        # Register all enabled tasks persisted in the database
        tasks = await self._load_all_tasks()
        for task in tasks:
            if task.enabled:
                self._register_job(task)
        enabled_count = sum(1 for t in tasks if t.enabled)
        logger.info("CronScheduler started — %d task(s) registered", enabled_count)

    async def shutdown(self) -> None:
        """Stop the scheduler gracefully."""
        if not self._running:
            return
        self._scheduler.shutdown(wait=False)
        self._running = False
        logger.info("CronScheduler stopped")

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create_task(
        self,
        name: str,
        description: str,
        schedule_type: str,
        schedule: str,
        task_type: str,
        task_config: dict[str, Any],
        enabled: bool = True,
    ) -> CronTaskRow:
        """Persist a new task and register it with APScheduler if enabled."""
        self._validate_schedule(schedule_type, schedule)

        factory = get_session_factory()
        async with factory() as session:
            row = CronTaskRow(
                id=str(uuid.uuid4()),
                name=name,
                description=description,
                schedule_type=schedule_type,
                schedule=schedule,
                task_type=task_type,
                task_config=json.dumps(task_config),
                enabled=enabled,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)

        if enabled and self._running:
            self._register_job(row)
        logger.info("CronTask created: %s (%s)", row.name, row.id)
        return row

    async def update_task(self, task_id: str, **fields: Any) -> CronTaskRow:
        """Update an existing task and sync its APScheduler job."""
        factory = get_session_factory()
        async with factory() as session:
            row = await session.get(CronTaskRow, task_id)
            if row is None:
                raise KeyError(f"CronTask {task_id!r} not found")

            # Validate schedule before committing
            new_schedule_type = fields.get("schedule_type", row.schedule_type)
            new_schedule = fields.get("schedule", row.schedule)
            self._validate_schedule(new_schedule_type, new_schedule)

            if "task_config" in fields and isinstance(fields["task_config"], dict):
                fields["task_config"] = json.dumps(fields["task_config"])

            for key, value in fields.items():
                setattr(row, key, value)
            row.updated_at = datetime.now(UTC)
            await session.commit()
            await session.refresh(row)

        # Re-register APScheduler job
        self._unregister_job(task_id)
        if row.enabled and self._running:
            self._register_job(row)
        return row

    async def delete_task(self, task_id: str) -> None:
        """Remove a task permanently."""
        factory = get_session_factory()
        async with factory() as session:
            row = await session.get(CronTaskRow, task_id)
            if row is None:
                raise KeyError(f"CronTask {task_id!r} not found")
            await session.delete(row)
            await session.commit()

        self._unregister_job(task_id)
        logger.info("CronTask deleted: %s", task_id)

    async def get_task(self, task_id: str) -> CronTaskRow:
        factory = get_session_factory()
        async with factory() as session:
            row = await session.get(CronTaskRow, task_id)
            if row is None:
                raise KeyError(f"CronTask {task_id!r} not found")
            return row

    async def list_tasks(self) -> list[CronTaskRow]:
        return await self._load_all_tasks()

    async def trigger_now(self, task_id: str) -> dict[str, Any]:
        """Manually execute a task immediately, outside its schedule."""
        task = await self.get_task(task_id)
        return await self._run_task(task)

    # ------------------------------------------------------------------
    # Run history
    # ------------------------------------------------------------------

    async def get_runs(self, task_id: str, limit: int = 50) -> list[CronRunRow]:
        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(CronRunRow)
                .where(CronRunRow.task_id == task_id)
                .order_by(CronRunRow.started_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    # ------------------------------------------------------------------
    # APScheduler job management
    # ------------------------------------------------------------------

    def _register_job(self, task: CronTaskRow) -> None:
        job_id = self._job_id(task.id)
        # Remove any existing job with the same id before re-adding
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

        trigger = self._build_trigger(task.schedule_type, task.schedule)

        job = self._scheduler.add_job(
            self._job_wrapper,
            trigger=trigger,
            id=job_id,
            name=task.name,
            args=[task.id],
            misfire_grace_time=300,
            coalesce=True,
            max_instances=1,
        )
        # Persist next_run_at
        if job.next_run_time:
            import asyncio
            asyncio.create_task(self._update_next_run(task.id, job.next_run_time))

        logger.debug("Registered cron job %s — next run: %s", task.name, job.next_run_time)

    def _unregister_job(self, task_id: str) -> None:
        job_id = self._job_id(task_id)
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

    @staticmethod
    def _job_id(task_id: str) -> str:
        return f"echo_cron_{task_id}"

    # ------------------------------------------------------------------
    # Job wrapper (called by APScheduler)
    # ------------------------------------------------------------------

    async def _job_wrapper(self, task_id: str) -> None:
        """APScheduler calls this on each tick; it fetches the task and runs it."""
        try:
            task = await self.get_task(task_id)
        except KeyError:
            logger.warning("CronTask %s no longer exists — skipping", task_id)
            return
        await self._run_task(task)

    async def _run_task(self, task: CronTaskRow) -> dict[str, Any]:
        """Execute a task, persist the CronRun record, and return the result."""
        from echo.cron.executor import execute_task

        run_id = str(uuid.uuid4())
        started_at = datetime.now(UTC)
        factory = get_session_factory()

        # Create running record
        async with factory() as session:
            run = CronRunRow(
                id=run_id,
                task_id=task.id,
                started_at=started_at,
                status="running",
            )
            session.add(run)
            await session.commit()

        result: dict[str, Any] = {}
        status = "success"
        try:
            if self._pipeline is None:
                raise RuntimeError("CronScheduler has no pipeline attached")
            config = json.loads(task.task_config or "{}")
            # Inject task metadata so executors can use description/name as fallbacks
            config.setdefault("_task_name", task.name)
            config.setdefault("_task_description", task.description or "")
            result = await execute_task(task.task_type, config, self._pipeline)
        except Exception as exc:  # noqa: BLE001
            status = "error"
            result = {"error": str(exc)}
            logger.exception("CronTask %s (%s) failed: %s", task.name, task.id, exc)
        else:
            logger.info("CronTask %s (%s) completed: %s", task.name, task.id, status)

        finished_at = datetime.now(UTC)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)

        # Update run record
        async with factory() as session:
            run_row = await session.get(CronRunRow, run_id)
            if run_row:
                run_row.finished_at = finished_at
                run_row.status = status

                def _safe(v: object) -> object:
                    if isinstance(v, (str, int, float, bool, type(None))):
                        return v
                    if isinstance(v, dict):
                        return {k: _safe(w) for k, w in v.items()}  # type: ignore[return-value]
                    if isinstance(v, (list, tuple)):
                        return [_safe(w) for w in v]
                    return str(v)

                run_row.result = json.dumps(_safe(result))
                run_row.duration_ms = duration_ms
                await session.commit()

        # Update task metadata
        await self._post_run_update(task.id)

        # Notify Telegram if task succeeded and produced content
        if status == "success":
            await self._notify_telegram(task, result, duration_ms)

        return result

    async def _notify_telegram(
        self,
        task: "CronTaskRow",
        result: dict[str, Any],
        duration_ms: int,
    ) -> None:
        """Send cron task result to Telegram if there is something worth reporting."""
        try:
            from echo.integrations.telegram_send import broadcast  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            return

        # Build a concise notification from whatever the executor returned
        lines: list[str] = [f"⏰ *{task.name}*"]

        # llm_task: show the LLM response
        response = result.get("response")
        if response and isinstance(response, str) and response.strip():
            lines.append(response.strip()[:1800])

        # curiosity cycle: show stored count
        stored = result.get("result") if task.task_type == "curiosity_cycle" else None
        if isinstance(stored, int) and stored > 0:
            lines.append(f"📚 {stored} new memories stored")

        # goal planning: show created/completed goals
        goals_created = result.get("goals_created", 0)
        goals_achieved = result.get("goals_achieved", 0)
        if goals_created:
            lines.append(f"🎯 {goals_created} new goal(s) created")
        if goals_achieved:
            lines.append(f"✅ {goals_achieved} goal(s) achieved")

        # reflection: show insights count
        insights = result.get("insights")
        if isinstance(insights, list) and insights:
            lines.append(f"💡 {len(insights)} insight(s): {'; '.join(str(i)[:80] for i in insights[:3])}")

        # Generic fallback: if result has any string values, show them
        if len(lines) == 1:  # only the header, nothing added
            for v in result.values():
                if isinstance(v, str) and v.strip() and v not in ("ok",):
                    lines.append(v.strip()[:400])
                    break

        # Skip if nothing to say beyond the header
        if len(lines) <= 1:
            logger.debug("Cron Telegram notification skipped — no content to report for %s", task.name)
            return

        lines.append(f"_({duration_ms}ms)_")
        text = "\n\n".join(lines)

        sent = await broadcast(text)
        if sent:
            logger.info("Cron result sent to %d Telegram chat(s): %s", sent, task.name)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _load_all_tasks(self) -> list[CronTaskRow]:
        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(CronTaskRow).order_by(CronTaskRow.created_at)
            )
            return list(result.scalars().all())

    async def _post_run_update(self, task_id: str) -> None:
        """Increment run_count and update last_run_at / next_run_at."""
        factory = get_session_factory()
        now = datetime.now(UTC)
        job = self._scheduler.get_job(self._job_id(task_id))
        next_run = job.next_run_time if job else None

        async with factory() as session:
            row = await session.get(CronTaskRow, task_id)
            if row:
                row.run_count = (row.run_count or 0) + 1
                row.last_run_at = now
                row.next_run_at = next_run
                await session.commit()

    async def _update_next_run(self, task_id: str, next_run: datetime) -> None:
        factory = get_session_factory()
        async with factory() as session:
            row = await session.get(CronTaskRow, task_id)
            if row:
                row.next_run_at = next_run
                await session.commit()

    @staticmethod
    def _build_trigger(schedule_type: str, schedule: str):
        if schedule_type == ScheduleType.INTERVAL:
            seconds = int(schedule)
            return IntervalTrigger(seconds=seconds, timezone="UTC")
        elif schedule_type == ScheduleType.CRON:
            parts = schedule.strip().split()
            if len(parts) != 5:
                raise ValueError(
                    f"Invalid cron expression {schedule!r} — expected 5 fields "
                    "(minute hour dom month dow)"
                )
            minute, hour, day, month, day_of_week = parts
            return CronTrigger(
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week,
                timezone="UTC",
            )
        raise ValueError(f"Unknown schedule_type: {schedule_type!r}")

    @staticmethod
    def _validate_schedule(schedule_type: str, schedule: str) -> None:
        if schedule_type == ScheduleType.INTERVAL:
            try:
                seconds = int(schedule)
                if seconds < 10:
                    raise ValueError("Interval must be at least 10 seconds")
            except ValueError as e:
                raise ValueError(f"Invalid interval schedule {schedule!r}: {e}") from e
        elif schedule_type == ScheduleType.CRON:
            parts = schedule.strip().split()
            if len(parts) != 5:
                raise ValueError(
                    f"Invalid cron expression {schedule!r} — expected 5 fields"
                )
        else:
            raise ValueError(f"Unknown schedule_type: {schedule_type!r}")
