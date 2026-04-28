"""Consolidation router — /api/consolidation."""

from __future__ import annotations

from fastapi import APIRouter

from echo.api.schemas import ConsolidationTriggerResponse
from echo.core.pipeline import pipeline

router = APIRouter(prefix="/api/consolidation", tags=["consolidation"])


@router.post("/trigger", response_model=ConsolidationTriggerResponse)
async def trigger_consolidation() -> ConsolidationTriggerResponse:
    """Manually trigger a consolidation cycle."""
    report = await pipeline.consolidation.trigger_now()
    return ConsolidationTriggerResponse(status="completed", report=report)


@router.get("/status")
async def consolidation_status():
    report = pipeline.consolidation._last_report
    if report is None:
        return {"status": "no_consolidation_run_yet"}
    return {"status": "completed", "report": report.model_dump()}
