"""Main cognitive pipeline — connects all components into a single interaction flow."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

from echo.agents.orchestrator import Orchestrator
from echo.consolidation.scheduler import ConsolidationScheduler
from echo.core.event_bus import bus
from echo.core.types import (
    CognitiveEvent,
    EventTopic,
    InteractionRecord,
    MetaState,
    WorkspaceSnapshot,
)
from echo.memory.decay import DecayScheduler
from echo.memory.episodic import EpisodicMemoryStore, MemoryEntry
from echo.motivation.drives import adjust_drives_from_interaction
from echo.plasticity.adapter import PlasticityAdapter
from echo.reflection.engine import ReflectionEngine
from echo.self_model.identity_graph import IdentityGraph
from echo.self_model.meta_state import MetaStateTracker
from echo.workspace.global_workspace import GlobalWorkspace

logger = logging.getLogger(__name__)


class CognitivePipeline:
    """Top-level controller for a single interact() call."""

    def __init__(self) -> None:
        self.identity_graph = IdentityGraph()
        self.meta_tracker = MetaStateTracker()
        self.workspace = GlobalWorkspace()
        self.episodic = EpisodicMemoryStore()
        self.orchestrator = Orchestrator()
        self.reflection = ReflectionEngine(self.identity_graph)
        self.plasticity = PlasticityAdapter()
        self.consolidation = ConsolidationScheduler()
        self.decay = DecayScheduler()
        self._interaction_count = 0
        self._ready = False

    async def startup(self) -> None:
        """Initialise all stateful components."""
        from echo.core.db import startup as db_startup

        await db_startup()
        await self.identity_graph.load()
        await self.meta_tracker.load_latest()
        self.consolidation.start()
        self.decay.start()
        self._ready = True
        logger.info("CognitivePipeline ready")

    async def shutdown(self) -> None:
        self.consolidation.stop()
        self.decay.stop()
        from echo.core.llm_client import llm

        await llm.aclose()
        logger.info("CognitivePipeline shutdown")

    @property
    def meta_state(self) -> MetaState:
        return self.meta_tracker.current

    # ------------------------------------------------------------------
    # Core interact()
    # ------------------------------------------------------------------

    async def interact(
        self,
        user_input: str,
        history: list[dict[str, str]] | None = None,
    ) -> InteractionRecord:
        """Full synchronous interact — returns complete record."""
        response, _ = await self._run_pipeline(user_input, history)
        return response

    async def stream_interact(
        self,
        user_input: str,
        history: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Streaming interact — yields response deltas, fires reflection in background."""
        interaction_id = str(uuid.uuid4())

        # Publish input event
        await bus.publish(
            CognitiveEvent(
                topic=EventTopic.USER_INPUT,
                payload={"text": user_input, "interaction_id": interaction_id},
            )
        )

        # Retrieve memories + build workspace
        memories = await self.episodic.retrieve_similar(user_input, n_results=5)
        self.workspace.clear()
        self.workspace.load_memories(memories, "archivist")

        context: dict[str, Any] = {"memories": memories, "interaction_id": interaction_id}
        meta_state = self.meta_tracker.current

        full_response = []
        async for delta in self.orchestrator.stream(
            user_input, self.workspace.snapshot, meta_state, context
        ):
            full_response.append(delta)
            yield delta

        # Post-interaction (async, non-blocking)
        response_text = "".join(full_response)
        asyncio.create_task(
            self._post_interact(interaction_id, user_input, response_text, memories)
        )

    # ------------------------------------------------------------------
    # Internal pipeline steps
    # ------------------------------------------------------------------

    async def _run_pipeline(
        self,
        user_input: str,
        history: list[dict[str, str]] | None = None,
    ) -> tuple[InteractionRecord, dict[str, str]]:
        interaction_id = str(uuid.uuid4())

        # Publish input event
        await bus.publish(
            CognitiveEvent(
                topic=EventTopic.USER_INPUT,
                payload={"text": user_input, "interaction_id": interaction_id},
            )
        )

        # Retrieve memories
        memories = await self.episodic.retrieve_similar(user_input, n_results=5)
        self.workspace.clear()
        self.workspace.load_memories(memories, "archivist")

        context: dict[str, Any] = {"memories": memories, "history": history or []}
        meta_state_before = self.meta_tracker.current.model_copy(deep=True)
        meta_state = self.meta_tracker.current

        # Run orchestrator
        response, agent_outputs = await self.orchestrator.run(
            user_input, self.workspace.snapshot, meta_state, context
        )

        # Post-interaction (blocking in this code path)
        await self._post_interact(interaction_id, user_input, response, memories)

        record = InteractionRecord(
            id=interaction_id,
            user_input=user_input,
            assistant_response=response,
            meta_state_before=meta_state_before,
            meta_state_after=self.meta_tracker.current,
            memories_retrieved=[m.id for m in memories],
        )
        return record, agent_outputs

    async def _post_interact(
        self,
        interaction_id: str,
        user_input: str,
        response: str,
        memories: list[MemoryEntry],
    ) -> None:
        """Store memory, reflect, adapt weights — runs async fire-and-forget."""
        try:
            # Store interaction as episodic memory
            mem = MemoryEntry(
                content=f"User: {user_input}\nECHO: {response}",
                importance=0.6,
                novelty=0.5,
                self_relevance=0.6,
                emotional_weight=0.2,
                source_agent="pipeline",
            )
            await self.episodic.store(mem)

            self._interaction_count += 1

            # Reflect every N interactions
            if self._interaction_count % max(1, 1) == 0:
                reflection = await self.reflection.reflect(
                    interaction_id, user_input, response, self.meta_tracker.current
                )

                # Apply drive adjustments
                drive_deltas = adjust_drives_from_interaction(
                    self.meta_tracker.current.drives,
                    user_input,
                    response,
                    reflection.insights,
                )
                # Merge reflection deltas
                for k, v in reflection.drive_adjustments.items():
                    drive_deltas[k] = drive_deltas.get(k, 0.0) + v

                self.meta_tracker.update_drives(drive_deltas)

                # Plasticity
                self.plasticity.apply(self.meta_tracker.current, reflection.insights)

                # Save state
                await self.meta_tracker.save()

                await bus.publish(
                    CognitiveEvent(
                        topic=EventTopic.REFLECTION_COMPLETE,
                        payload={
                            "interaction_id": interaction_id,
                            "insights": reflection.insights,
                            "new_beliefs": len(reflection.new_beliefs),
                        },
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("Post-interact error: %s", exc)


# Module-level singleton (lazily initialised at startup)
pipeline: CognitivePipeline = CognitivePipeline()
