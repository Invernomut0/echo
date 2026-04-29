"""Consolidation router — /api/consolidation."""

from __future__ import annotations

from fastapi import APIRouter, Query

from echo.api.schemas import ConsolidationTriggerResponse
from echo.core.pipeline import pipeline

router = APIRouter(prefix="/api/consolidation", tags=["consolidation"])


@router.post("/trigger", response_model=ConsolidationTriggerResponse)
async def trigger_consolidation() -> ConsolidationTriggerResponse:
    """Manually trigger a light consolidation cycle."""
    report = await pipeline.consolidation.trigger_now()
    return ConsolidationTriggerResponse(status="completed", report=report)


@router.get("/status")
async def consolidation_status():
    report = pipeline.consolidation._last_report
    if report is None:
        return {"status": "no_consolidation_run_yet"}
    return {"status": "completed", "report": report.model_dump()}


@router.get("/heartbeat")
async def heartbeat_status():
    """Return the current heartbeat scheduler status (timings, intervals)."""
    return pipeline.consolidation.heartbeat_status


@router.post("/trigger-rem")
async def trigger_rem():
    """Manually trigger the full REM (deep) consolidation + dream generation."""
    dream = await pipeline.consolidation.trigger_rem_now()
    return {"status": "ok", "dream": dream.model_dump()}


@router.get("/dreams")
async def get_dreams(limit: int = Query(default=20, ge=1, le=100)):
    """Return the most recent dream entries."""
    from echo.memory.dream_store import DreamStore

    dreams = await DreamStore().get_all(limit=limit)
    return [d.model_dump() for d in dreams]
