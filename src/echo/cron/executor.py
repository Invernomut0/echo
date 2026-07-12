"""Task executors for the internal cron system.

Each executor receives:
  - task_config: dict with task-specific parameters
  - pipeline: CognitivePipeline (for access to all cognitive subsystems)

Returns a JSON-serialisable dict as the execution result.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from echo.cron.models import TaskType

if TYPE_CHECKING:
    from echo.core.pipeline import CognitivePipeline

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Executor registry
# ---------------------------------------------------------------------------

async def execute_task(
    task_type: str,
    task_config: dict[str, Any],
    pipeline: CognitivePipeline,
) -> dict[str, Any]:
    """Dispatch to the appropriate executor and return a result dict."""
    executors = {
        TaskType.REFLECTION: _exec_reflection,
        TaskType.CONSOLIDATION_LIGHT: _exec_consolidation_light,
        TaskType.CONSOLIDATION_DEEP: _exec_consolidation_deep,
        TaskType.CURIOSITY_CYCLE: _exec_curiosity_cycle,
        TaskType.LLM_TASK: _exec_llm_task,
        TaskType.MEMORY_STORE: _exec_memory_store,
        TaskType.GOAL_REFLECT: _exec_goal_reflect,
        TaskType.SELF_MODIFICATION: _exec_self_modification,
    }
    executor = executors.get(task_type)
    if executor is None:
        raise ValueError(f"Unknown task type: {task_type!r}")
    return await executor(task_config, pipeline)


# ---------------------------------------------------------------------------
# Individual executors
# ---------------------------------------------------------------------------

async def _exec_reflection(config: dict[str, Any], pipeline: CognitivePipeline) -> dict[str, Any]:
    """Trigger a manual reflection cycle.

    config keys (all optional):
      trigger_input: str — synthetic "input" passed to the reflection engine.
        Defaults to a generic introspection prompt.
    """
    trigger_input = config.get(
        "trigger_input",
        "Cron-triggered introspection: review recent experiences and update beliefs.",
    )

    recent_mems = await pipeline.episodic.get_recent(n=config.get("memory_limit", 5))
    if not recent_mems:
        return {"status": "skipped", "reason": "no recent memories"}

    interaction_id = f"cron-reflection-{id(trigger_input)}"
    result = await pipeline.reflection.reflect(
        interaction_id=interaction_id,
        user_input=trigger_input,
        assistant_response="",
        recent_memories=[m.content for m in recent_mems],
        workspace_context=[i.content[:200] for i in pipeline.workspace.snapshot.items[:3]],
    )

    return {
        "status": "ok",
        "insights": result.insights,
        "new_beliefs": len(result.new_beliefs),
        "updated_beliefs": len(result.updated_belief_ids),
    }


async def _exec_consolidation_light(
    config: dict[str, Any], pipeline: CognitivePipeline
) -> dict[str, Any]:
    """Trigger a light (standard) consolidation cycle."""
    report = await pipeline.consolidation.trigger_now()
    return {
        "status": "ok",
        "memories_processed": report.memories_processed if report else 0,
        "memories_pruned": report.memories_pruned if report else 0,
        "patterns_found": report.patterns_found if report else [],
    }


async def _exec_consolidation_deep(
    config: dict[str, Any], pipeline: CognitivePipeline
) -> dict[str, Any]:
    """Trigger the full deep / REM consolidation + dream generation."""
    dream = await pipeline.consolidation.trigger_rem_now()
    return {
        "status": "ok",
        "dream_id": dream.id,
        "dream_excerpt": dream.dream[:200] + "…" if len(dream.dream) > 200 else dream.dream,
        "synthesis_count": dream.synthesis_count,
    }


async def _exec_curiosity_cycle(
    config: dict[str, Any], pipeline: CognitivePipeline
) -> dict[str, Any]:
    """Trigger an autonomous curiosity exploration cycle.

    config keys (all optional):
      force: bool — bypass idle-time check (default True for cron).
    """
    try:
        from echo.curiosity.engine import curiosity_engine  # lazy import
    except ImportError:
        return {"status": "skipped", "reason": "curiosity module not available"}

    force = config.get("force", True)
    result = await curiosity_engine.run_cycle(force=force)
    return {"status": "ok", "result": result}


async def _exec_llm_task(
    config: dict[str, Any], pipeline: CognitivePipeline
) -> dict[str, Any]:
    """Execute an arbitrary LLM prompt and optionally store the result as a memory.

    config keys:
      prompt: str (required) — the system/user prompt sent to the LLM.
      system_prompt: str — optional system role prefix.
      store_as_memory: bool — if True, store the LLM output as an episodic memory (default True).
      memory_tags: list[str] — tags for the memory entry.
      temperature: float — LLM temperature (default 0.7).
      max_tokens: int — max tokens for the LLM response (default 512).
    """
    from echo.core.llm_client import llm
    from echo.memory.episodic import MemoryEntry

    prompt = config.get("prompt")
    if not prompt:
        # Fall back to task description or name if no explicit prompt set
        prompt = config.get("_task_description") or config.get("_task_name")
    if not prompt:
        raise ValueError("llm_task requires a 'prompt' in task_config")

    messages: list[dict[str, str]] = []
    system_prompt = config.get("system_prompt", "You are ECHO, a persistent cognitive AI assistant.")
    # Inject language instruction so responses match ECHO_LANGUAGE setting
    try:
        from echo.core.config import settings as _s  # noqa: PLC0415
        lang = _s.echo_language.strip().lower()
        _lang_names = {"it": "Italian", "es": "Spanish", "fr": "French", "de": "German",
                       "pt": "Portuguese", "ja": "Japanese", "zh": "Chinese"}
        _lang_name = _lang_names.get(lang, lang)
        if lang and lang != "en":
            system_prompt += f"\n\nIMPORTANT: Always respond in {_lang_name}."
    except Exception:  # noqa: BLE001
        pass
    messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    # use_tools: true → stream_chat_with_tools gives LLM access to bash, filesystem, etc.
    if config.get("use_tools", False):
        chunks: list[str] = []
        async for delta in llm.stream_chat_with_tools(
            messages,
            temperature=config.get("temperature", 0.7),
            max_tokens=config.get("max_tokens", 2048),
        ):
            if isinstance(delta, str):
                chunks.append(delta)
        response = "".join(chunks)
    else:
        response = await llm.chat(
            messages,
            temperature=config.get("temperature", 0.7),
            max_tokens=config.get("max_tokens", 512),
        )

    result: dict[str, Any] = {"status": "ok", "response": response}

    if config.get("store_as_memory", True):
        tags = config.get("memory_tags", ["cron", "llm_task"])
        entry = MemoryEntry(
            content=f"[Cron LLM task] {response}",
            importance=config.get("importance", 0.5),
            novelty=config.get("novelty", 0.6),
            self_relevance=config.get("self_relevance", 0.4),
            tags=tags,
            source_agent="cron",
        )
        entry.compute_salience()
        stored_entry = await pipeline.episodic.store(entry)
        result["memory_id"] = stored_entry.id if hasattr(stored_entry, "id") else str(stored_entry)

    return result


async def _exec_memory_store(
    config: dict[str, Any], pipeline: CognitivePipeline
) -> dict[str, Any]:
    """Store a fixed memory entry on every execution.

    config keys:
      content: str (required) — the memory content.
      importance: float
      novelty: float
      self_relevance: float
      emotional_weight: float
      tags: list[str]
    """
    from echo.memory.episodic import MemoryEntry

    content = config.get("content")
    if not content:
        raise ValueError("memory_store requires 'content' in task_config")

    entry = MemoryEntry(
        content=content,
        importance=config.get("importance", 0.5),
        novelty=config.get("novelty", 0.4),
        self_relevance=config.get("self_relevance", 0.4),
        emotional_weight=config.get("emotional_weight", 0.0),
        tags=config.get("tags", ["cron"]),
        source_agent="cron",
    )
    entry.compute_salience()
    stored = await pipeline.episodic.store(entry)
    return {"status": "ok", "memory_id": stored.id if hasattr(stored, "id") else str(stored)}


async def _exec_goal_reflect(
    config: dict[str, Any], pipeline: CognitivePipeline
) -> dict[str, Any]:
    """Trigger goal reflection — ECHO reviews its active goals and plans next actions.

    config keys (all optional):
      max_goals: int — max goals to process (default 3).
    """
    try:
        from echo.curiosity.goal_engine import GoalEngine  # lazy import
    except ImportError:
        return {"status": "skipped", "reason": "goal engine not available"}

    max_goals = config.get("max_goals", 3)
    engine = GoalEngine()
    result = await engine.reflect_and_plan(max_goals=max_goals)
    return {"status": "ok", "result": result}


async def _exec_self_modification(
    config: dict[str, Any],
    pipeline: CognitivePipeline,
) -> dict[str, Any]:
    """Run SelfModificationEngine — ECHO improves its own codebase.

    The engine:
    1. Snapshots internal state (drives, goals, knowledge gaps)
    2. Asks LLM to identify one small improvement
    3. Applies the change to src/echo/
    4. Validates with ast.parse (rolls back on failure)
    5. git commit + push
    6. Creates notes/YYYY-MM-DD_slug.md
    7. Sends Telegram notification

    config keys (all optional):
      cooldown_override: bool — bypass 6h cooldown (for manual triggers)
    """
    from echo.self_modification.engine import self_modification_engine  # noqa: PLC0415

    if config.get("cooldown_override"):
        self_modification_engine._last_modified = 0.0  # reset cooldown

    mod = await self_modification_engine.evaluate_and_modify(pipeline)

    if mod is None:
        return {
            "status": "skipped",
            "reason": "no modification warranted or cooldown active",
        }

    return {
        "status": "ok",
        "file": mod.get("file", ""),
        "description": mod.get("description", ""),
        "pushed": mod.get("pushed", False),
        "slug": mod.get("slug", ""),
    }
