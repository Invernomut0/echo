"""Internal LLM tool definitions for ECHO's cron system.

Exposes five tools that the LLM can call during conversation or autonomous
cognitive cycles to manage its own recurring task schedule:

  echo__cron_list_tasks    — list all scheduled tasks
  echo__cron_create_task   — create a new recurring task
  echo__cron_update_task   — modify an existing task
  echo__cron_delete_task   — permanently remove a task
  echo__cron_trigger_task  — run a task immediately outside its schedule

All tools are registered into the MCPClientManager's internal tool registry
so they appear in the LLM's tool list alongside any external MCP tools.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from echo.cron.scheduler import CronScheduler
    from echo.mcp.client import MCPClientManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool schemas (OpenAI function-call format)
# ---------------------------------------------------------------------------

_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "echo__cron_list_tasks",
            "description": (
                "List all of ECHO's scheduled recurring tasks with their current status, "
                "schedule, type, run count, and next execution time."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "echo__cron_create_task",
            "description": (
                "Create a new recurring task in ECHO's cron system. "
                "Use schedule_type='interval' with schedule as seconds "
                "(e.g. '3600' for every hour), "
                "or schedule_type='cron' with a standard 5-field cron expression "
                "(minute hour dom month dow, e.g. '0 */6 * * *' for every 6 hours). "
                "Available task_type values: reflection, consolidation_light, consolidation_deep, "
                "curiosity_cycle, llm_task, memory_store, goal_reflect."
            ),
            "parameters": {
                "type": "object",
                "required": ["name", "schedule_type", "schedule", "task_type"],
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Short descriptive name for the task.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional longer description of the task's purpose.",
                        "default": "",
                    },
                    "schedule_type": {
                        "type": "string",
                        "enum": ["interval", "cron"],
                        "description": "'interval' for fixed seconds, 'cron' for cron expression.",
                    },
                    "schedule": {
                        "type": "string",
                        "description": (
                            "Interval in seconds (e.g. '3600') or cron expression "
                            "(e.g. '0 */6 * * *'). Minimum interval is 10 seconds."
                        ),
                    },
                    "task_type": {
                        "type": "string",
                        "enum": [
                            "reflection",
                            "consolidation_light",
                            "consolidation_deep",
                            "curiosity_cycle",
                            "llm_task",
                            "memory_store",
                            "goal_reflect",
                        ],
                        "description": "The cognitive action to perform on each run.",
                    },
                    "task_config": {
                        "type": "object",
                        "description": (
                            "Optional configuration dict for the task executor. "
                            "For 'llm_task': {\"prompt\": \"...\"}. "
                            "For 'memory_store': "
                            "{\"content\": \"...\", \"memory_type\": \"semantic\"}."
                        ),
                        "default": {},
                    },
                    "enabled": {
                        "type": "boolean",
                        "description": "Whether to start the task immediately (default: true).",
                        "default": True,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "echo__cron_update_task",
            "description": (
                "Modify an existing cron task: change its schedule, name, description, "
                "task_config, task_type, or enabled state. Only supplied fields are updated."
            ),
            "parameters": {
                "type": "object",
                "required": ["task_id"],
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "UUID of the task to update.",
                    },
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "schedule_type": {
                        "type": "string",
                        "enum": ["interval", "cron"],
                    },
                    "schedule": {"type": "string"},
                    "task_type": {
                        "type": "string",
                        "enum": [
                            "reflection",
                            "consolidation_light",
                            "consolidation_deep",
                            "curiosity_cycle",
                            "llm_task",
                            "memory_store",
                            "goal_reflect",
                        ],
                    },
                    "task_config": {"type": "object"},
                    "enabled": {"type": "boolean"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "echo__cron_delete_task",
            "description": (
                "Permanently delete a cron task. This removes it from the scheduler "
                "and the database. The action cannot be undone."
            ),
            "parameters": {
                "type": "object",
                "required": ["task_id"],
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "UUID of the task to delete.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "echo__cron_trigger_task",
            "description": (
                "Immediately run a cron task outside its normal schedule. "
                "Useful for testing a task or forcing an early execution."
            ),
            "parameters": {
                "type": "object",
                "required": ["task_id"],
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "UUID of the task to trigger.",
                    },
                },
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _make_handlers(cron: CronScheduler) -> dict[str, Any]:
    """Return a mapping of tool_name → async handler, bound to *cron*."""

    async def _list_tasks(_args: dict[str, Any]) -> str:
        tasks = await cron.list_tasks()
        result = []
        for t in tasks:
            result.append({
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "schedule_type": t.schedule_type,
                "schedule": t.schedule,
                "task_type": t.task_type,
                "task_config": json.loads(t.task_config or "{}"),
                "enabled": t.enabled,
                "run_count": t.run_count,
                "last_run_at": t.last_run_at.isoformat() if t.last_run_at else None,
                "next_run_at": t.next_run_at.isoformat() if t.next_run_at else None,
                "created_at": t.created_at.isoformat(),
            })
        return json.dumps({"tasks": result, "total": len(result)})

    async def _create_task(args: dict[str, Any]) -> str:
        try:
            row = await cron.create_task(
                name=args["name"],
                description=args.get("description", ""),
                schedule_type=args["schedule_type"],
                schedule=args["schedule"],
                task_type=args["task_type"],
                task_config=args.get("task_config") or {},
                enabled=args.get("enabled", True),
            )
            return json.dumps({
                "ok": True,
                "task_id": row.id,
                "name": row.name,
                "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
            })
        except Exception as exc:  # noqa: BLE001
            logger.warning("cron_create_task failed: %s", exc)
            return json.dumps({"ok": False, "error": str(exc)})

    async def _update_task(args: dict[str, Any]) -> str:
        task_id = args.pop("task_id")
        try:
            row = await cron.update_task(task_id, **args)
            return json.dumps({
                "ok": True,
                "task_id": row.id,
                "name": row.name,
                "enabled": row.enabled,
                "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
            })
        except Exception as exc:  # noqa: BLE001
            logger.warning("cron_update_task failed: %s", exc)
            return json.dumps({"ok": False, "error": str(exc)})

    async def _delete_task(args: dict[str, Any]) -> str:
        task_id = args["task_id"]
        try:
            await cron.delete_task(task_id)
            return json.dumps({"ok": True, "deleted_task_id": task_id})
        except Exception as exc:  # noqa: BLE001
            logger.warning("cron_delete_task failed: %s", exc)
            return json.dumps({"ok": False, "error": str(exc)})

    async def _trigger_task(args: dict[str, Any]) -> str:
        task_id = args["task_id"]
        try:
            result = await cron.trigger_now(task_id)
            return json.dumps({"ok": True, "task_id": task_id, "result": result})
        except Exception as exc:  # noqa: BLE001
            logger.warning("cron_trigger_task failed: %s", exc)
            return json.dumps({"ok": False, "error": str(exc)})

    return {
        "echo__cron_list_tasks": _list_tasks,
        "echo__cron_create_task": _create_task,
        "echo__cron_update_task": _update_task,
        "echo__cron_delete_task": _delete_task,
        "echo__cron_trigger_task": _trigger_task,
    }


# ---------------------------------------------------------------------------
# Registration entry point
# ---------------------------------------------------------------------------

def register_cron_tools(mcp_manager: MCPClientManager, cron: CronScheduler) -> None:
    """Register all cron management tools into the MCP manager's internal registry.

    Called from ``CognitivePipeline.startup()`` after the cron scheduler is
    ready, so handlers have a live reference to the running *CronScheduler*.
    """
    handlers = _make_handlers(cron)
    for tool_def in _TOOLS:
        name = tool_def["function"]["name"]
        mcp_manager.register_internal_tool(
            qualified_name=name,
            openai_def=tool_def,
            handler=handlers[name],
        )
    logger.info("[Cron] Registered %d cron tools into MCP manager", len(_TOOLS))
