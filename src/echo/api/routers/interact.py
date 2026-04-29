"""Interact router — /api/interact (SSE streaming) and /api/chat (sync)."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from echo.api.schemas import ChatRequest, ChatResponse
from echo.core.pipeline import pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["interact"])


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest) -> ChatResponse:
    """Synchronous single-turn interaction."""
    record = await pipeline.interact(body.message, body.history)
    return ChatResponse(
        interaction_id=record.id,
        response=record.assistant_response,
        meta_state=pipeline.meta_state,
        memories_used=len(record.memories_retrieved),
        timestamp=record.created_at,
    )


@router.post("/interact")
async def interact_stream(body: ChatRequest, request: Request) -> StreamingResponse:
    """SSE streaming interaction."""

    async def event_stream():
        try:
            async for delta in pipeline.stream_interact(body.message, body.history):
                payload = json.dumps({"type": "delta", "content": delta})
                yield f"data: {payload}\n\n"

            # Normal completion — send done event.
            # Use model_dump(mode='json') so datetime fields are ISO strings,
            # not bare Python datetime objects (which json.dumps cannot handle).
            ms = pipeline.meta_state.model_dump(mode="json")
            mem_sources = getattr(pipeline, "_last_memory_sources", {"episodic": 0, "semantic": 0})
            yield f"data: {json.dumps({'type': 'done', 'meta_state': ms, 'memory_sources': mem_sources})}\n\n"

        except Exception as exc:  # noqa: BLE001
            logger.error("Streaming error: %s", exc, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"
            # Always send done to unblock the client even on error
            try:
                ms = pipeline.meta_state.model_dump(mode="json")
                yield f"data: {json.dumps({'type': 'done', 'meta_state': ms})}\n\n"
            except Exception:  # noqa: BLE001
                yield f"data: {json.dumps({'type': 'done', 'meta_state': {}})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
