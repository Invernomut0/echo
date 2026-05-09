"""GoalStore — persistent goal tracking for ECHO's autonomous reasoning.

Goals are stored in SQLite with two tables:
  - ``goals``        : one row per goal (title, description, status, priority)
  - ``goal_actions`` : append-only log of steps taken toward each goal

Status lifecycle:  active → achieved | abandoned
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import relationship

from echo.core.db import Base, get_session_factory

logger = logging.getLogger(__name__)

# Maximum active goals at any time (enforced on write)
MAX_ACTIVE_GOALS = 5

# Maximum iterations (actions) per goal before forced consolidation
MAX_GOAL_ITERATIONS = 10


def _clean_text(value: str | None, *, max_len: int = 500) -> str:
    text = (value or "").strip()
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def _build_goal_resolution_payload(goal: dict[str, Any]) -> dict[str, Any]:
    """Build a coherent, structured summary for an achieved goal."""
    title = _clean_text(goal.get("title") or "Untitled goal", max_len=200)
    description = _clean_text(goal.get("description") or "", max_len=600)
    goal_id = str(goal.get("id") or "")

    actions = goal.get("actions") or []
    done_actions = [a for a in actions if a.get("status") == "done"]
    meaningful_done = [
        a for a in done_actions
        if (a.get("description") or "").strip() and (a.get("result") or "").strip() not in {"", "Created"}
    ]

    why_chosen = description
    if not why_chosen:
        if meaningful_done:
            why_chosen = _clean_text(
                meaningful_done[0].get("description") or "Goal derivato dalla riflessione autonoma.",
                max_len=280,
            )
        elif done_actions:
            why_chosen = _clean_text(
                done_actions[0].get("description") or "Goal derivato dalla riflessione autonoma.",
                max_len=280,
            )
        else:
            why_chosen = "Goal derivato dalla riflessione autonoma per migliorare competenza e coerenza."

    findings: list[str] = []
    for action in meaningful_done[:8]:
        result = _clean_text(action.get("result") or "", max_len=240)
        if result:
            findings.append(result)

    solution_steps: list[str] = []
    for action in done_actions[:8]:
        desc = _clean_text(action.get("description") or "", max_len=200)
        if not desc:
            continue
        result = _clean_text(action.get("result") or "", max_len=180)
        if result and result not in {"Created"}:
            solution_steps.append(f"{desc} → {result}")
        else:
            solution_steps.append(desc)

    if findings:
        solution_summary = "; ".join(findings[:3])
    elif solution_steps:
        solution_summary = "; ".join(solution_steps[:3])
    else:
        solution_summary = "Il goal è stato marcato come raggiunto senza dettagli operativi aggiuntivi."
    solution_summary = _clean_text(solution_summary, max_len=700)

    achieved_at = goal.get("achieved_at") or goal.get("updated_at") or "unknown"
    semantic_lines = [
        "[Goal Resolution Report]",
        f"Goal: {title}",
        f"Goal ID: {goal_id}",
        f"Perché scelto: {why_chosen}",
        "",
    ]

    if findings:
        semantic_lines.append("Informazioni ricavate:")
        for item in findings[:8]:
            semantic_lines.append(f"- {item}")
        semantic_lines.append("")

    if solution_steps:
        semantic_lines.append("Soluzione adottata:")
        for step in solution_steps[:8]:
            semantic_lines.append(f"- {step}")
        semantic_lines.append("")

    semantic_lines.extend([
        f"Riassunto soluzione: {solution_summary}",
        f"Esito: goal achieved at {achieved_at}",
    ])

    semantic_content = "\n".join(semantic_lines)

    return {
        "goal_id": goal_id,
        "goal_title": title,
        "why_chosen": why_chosen,
        "solution_summary": solution_summary,
        "semantic_content": semantic_content,
    }


async def _persist_goal_resolution(goal: dict[str, Any]) -> None:
    """Store achieved-goal resolution in semantic memory and notify Telegram."""
    from echo.integrations import send_goal_resolution_notification  # noqa: PLC0415
    from echo.memory.semantic import SemanticMemoryStore  # noqa: PLC0415

    payload = _build_goal_resolution_payload(goal)
    goal_id = payload["goal_id"]

    tags = ["goal_achieved", "goal_resolution", f"goal:{goal_id[:8]}"]
    for tag in goal.get("tags") or []:
        if isinstance(tag, str) and tag and tag not in tags:
            tags.append(tag)

    priority = float(goal.get("priority", 0.5) or 0.5)
    salience = round(0.7 + max(0.0, min(1.0, priority)) * 0.25, 3)

    semantic = SemanticMemoryStore()
    await semantic.store(
        content=payload["semantic_content"],
        tags=tags,
        salience=salience,
    )

    sent_count = await send_goal_resolution_notification(
        goal_title=payload["goal_title"],
        why_chosen=payload["why_chosen"],
        solution_summary=payload["solution_summary"],
    )
    logger.info(
        "Goal resolution consolidated for '%s' (salience=%.3f, telegram_sent=%d)",
        payload["goal_title"],
        salience,
        sent_count,
    )


# ---------------------------------------------------------------------------
# ORM rows
# ---------------------------------------------------------------------------

class GoalRow(Base):
    __tablename__ = "goals"
    __allow_unmapped__ = True

    id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title       = Column(Text, nullable=False)
    description = Column(Text, default="")
    status      = Column(String, default="active")   # active | achieved | abandoned
    priority    = Column(Float, default=0.5)         # 0.0–1.0
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    achieved_at = Column(DateTime, nullable=True)
    tags        = Column(Text, default="[]")         # JSON list

    actions: list["GoalActionRow"] = relationship(
        "GoalActionRow",
        back_populates="goal",
        cascade="all, delete-orphan",
        order_by="GoalActionRow.created_at",
    )


class GoalActionRow(Base):
    __tablename__ = "goal_actions"
    __allow_unmapped__ = True

    id         = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    goal_id    = Column(String, ForeignKey("goals.id", ondelete="CASCADE"), nullable=False)
    step       = Column(Integer, default=0)           # sequential step counter per goal
    description= Column(Text, nullable=False)
    result     = Column(Text, default="")             # outcome / observation
    status     = Column(String, default="done")       # done | failed | pending
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    goal: GoalRow = relationship("GoalRow", back_populates="actions")


# ---------------------------------------------------------------------------
# Data classes (pure Python, no ORM)
# ---------------------------------------------------------------------------

def _row_to_goal(row: GoalRow) -> dict[str, Any]:
    actions = [
        {
            "id": a.id,
            "goal_id": a.goal_id,
            "step": a.step,
            "description": a.description,
            "result": a.result,
            "status": a.status,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in (row.actions or [])
    ]
    return {
        "id": row.id,
        "title": row.title,
        "description": row.description,
        "status": row.status,
        "priority": row.priority,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "achieved_at": row.achieved_at.isoformat() if row.achieved_at else None,
        "tags": json.loads(row.tags or "[]"),
        "actions": actions,
    }


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class GoalStore:
    """Async CRUD layer for goals and goal actions."""

    # ── Goals ──────────────────────────────────────────────────────────────────

    async def count_active(self) -> int:
        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(GoalRow).where(GoalRow.status == "active")
            )
            return len(result.scalars().all())

    async def list_active(self) -> list[dict[str, Any]]:
        factory = get_session_factory()
        async with factory() as session:
            rows = (
                await session.execute(
                    select(GoalRow)
                    .where(GoalRow.status == "active")
                    .order_by(GoalRow.priority.desc(), GoalRow.created_at)
                )
            ).scalars().all()
            # eagerly load actions
            result = []
            for row in rows:
                await session.refresh(row, ["actions"])
                result.append(_row_to_goal(row))
            return result

    async def list_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return achieved/abandoned goals, newest first."""
        factory = get_session_factory()
        async with factory() as session:
            rows = (
                await session.execute(
                    select(GoalRow)
                    .where(GoalRow.status.in_(["achieved", "abandoned"]))
                    .order_by(GoalRow.updated_at.desc())
                    .limit(limit)
                )
            ).scalars().all()
            result = []
            for row in rows:
                await session.refresh(row, ["actions"])
                result.append(_row_to_goal(row))
            return result

    async def get(self, goal_id: str) -> dict[str, Any] | None:
        factory = get_session_factory()
        async with factory() as session:
            row = await session.get(GoalRow, goal_id)
            if row is None:
                return None
            await session.refresh(row, ["actions"])
            return _row_to_goal(row)

    async def create(
        self,
        title: str,
        description: str = "",
        priority: float = 0.5,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new active goal. Returns the created goal dict."""
        active = await self.count_active()
        if active >= MAX_ACTIVE_GOALS:
            raise ValueError(
                f"Maximum active goals ({MAX_ACTIVE_GOALS}) reached — "
                "achieve or abandon an existing goal first."
            )
        factory = get_session_factory()
        async with factory() as session:
            row = GoalRow(
                id=str(uuid.uuid4()),
                title=title,
                description=description,
                status="active",
                priority=max(0.0, min(1.0, priority)),
                tags=json.dumps(tags or []),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row, ["actions"])
            return _row_to_goal(row)

    async def update_status(
        self,
        goal_id: str,
        status: str,
        description: str | None = None,
    ) -> dict[str, Any] | None:
        """Update goal status. Returns updated goal or None if not found."""
        transition_to_achieved = False
        updated_goal: dict[str, Any] | None = None

        factory = get_session_factory()
        async with factory() as session:
            row = await session.get(GoalRow, goal_id)
            if row is None:
                return None
            prev_status = row.status
            row.status = status
            row.updated_at = datetime.now(timezone.utc)
            if status == "achieved":
                row.achieved_at = datetime.now(timezone.utc)
            if description is not None:
                row.description = description
            await session.commit()
            await session.refresh(row, ["actions"])
            updated_goal = _row_to_goal(row)
            transition_to_achieved = prev_status != "achieved" and status == "achieved"

        if transition_to_achieved and updated_goal is not None:
            try:
                await _persist_goal_resolution(updated_goal)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Goal resolution persistence failed for goal_id=%s: %s",
                    goal_id,
                    exc,
                )

        return updated_goal

    async def delete(self, goal_id: str) -> bool:
        factory = get_session_factory()
        async with factory() as session:
            row = await session.get(GoalRow, goal_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    # ── Actions ────────────────────────────────────────────────────────────────

    async def add_action(
        self,
        goal_id: str,
        description: str,
        result: str = "",
        status: str = "pending",
    ) -> dict[str, Any] | None:
        """Append a new action step to a goal. Returns the action dict."""
        factory = get_session_factory()
        async with factory() as session:
            # get next step number
            existing = (
                await session.execute(
                    select(GoalActionRow)
                    .where(GoalActionRow.goal_id == goal_id)
                    .order_by(GoalActionRow.step.desc())
                    .limit(1)
                )
            ).scalars().first()
            next_step = (existing.step + 1) if existing else 1

            action = GoalActionRow(
                id=str(uuid.uuid4()),
                goal_id=goal_id,
                step=next_step,
                description=description,
                result=result,
                status=status,
            )
            session.add(action)
            await session.commit()
            await session.refresh(action)
            return {
                "id": action.id,
                "goal_id": action.goal_id,
                "step": action.step,
                "description": action.description,
                "result": action.result,
                "status": action.status,
                "created_at": action.created_at.isoformat() if action.created_at else None,
            }

    async def update_action(
        self,
        action_id: str,
        status: str,
        result: str | None = None,
    ) -> dict[str, Any] | None:
        """Update an action's status (and optionally result). Returns action dict or None."""
        factory = get_session_factory()
        async with factory() as session:
            action = await session.get(GoalActionRow, action_id)
            if action is None:
                return None
            action.status = status
            if result is not None:
                action.result = result
            await session.commit()
            await session.refresh(action)
            return {
                "id": action.id,
                "goal_id": action.goal_id,
                "step": action.step,
                "description": action.description,
                "result": action.result,
                "status": action.status,
                "created_at": action.created_at.isoformat() if action.created_at else None,
            }


    # ── Consolidation ─────────────────────────────────────────────────────────

    async def action_count(self, goal_id: str) -> int:
        """Return the total number of actions for a goal."""
        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(GoalActionRow).where(GoalActionRow.goal_id == goal_id)
            )
            return len(result.scalars().all())

    async def consolidate_goal(self, goal_id: str) -> dict[str, Any] | None:
        """Force-close a goal that reached max iterations.

        Collects all action results, synthesises knowledge, marks as achieved,
        and stores a consolidated semantic memory.
        """
        goal = await self.get(goal_id)
        if goal is None or goal["status"] != "active":
            return None

        # Collect all results from done actions
        results = [
            a["result"]
            for a in goal["actions"]
            if a["status"] == "done" and a["result"] and a["result"] != "Created"
        ]

        # Mark the final action
        await self.add_action(
            goal_id,
            description="Goal auto-consolidated: max iterations reached",
            result=f"Synthesised {len(results)} research findings into knowledge",
            status="done",
        )

        # Mark as achieved
        await self.update_status(goal_id, "achieved")

        return {
            "goal": goal,
            "results": results,
        }


# Singleton
goal_store = GoalStore()
