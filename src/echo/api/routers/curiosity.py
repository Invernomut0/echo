"""Curiosity router — /api/curiosity."""

from __future__ import annotations

from fastapi import APIRouter, Query

from echo.curiosity.engine import (
    CuriosityEngine,
    _activity_log,
    _is_running,
    _recently_searched,
)

router = APIRouter(prefix="/api/curiosity", tags=["curiosity"])

# Shared engine instance for manual triggers (stateless beyond memory stores)
_engine = CuriosityEngine()


@router.get("/activity")
async def get_activity(limit: int = Query(default=50, ge=1, le=200)):
    """Return recent curiosity cycle records, newest-first."""
    cycles = list(reversed(_activity_log))[:limit]
    total_stored = sum(c.get("total_stored", 0) for c in _activity_log)
    total_cycles = len(_activity_log)
    completed = sum(1 for c in _activity_log if c.get("status") == "completed")
    skipped = sum(1 for c in _activity_log if c.get("status") == "skipped")
    return {
        "is_running": _is_running,
        "recently_searched": sorted(_recently_searched),
        "stats": {
            "total_cycles": total_cycles,
            "completed": completed,
            "skipped": skipped,
            "total_stored": total_stored,
        },
        "cycles": cycles,
    }


@router.post("/trigger")
async def trigger_cycle():
    """Manually trigger one curiosity cycle (bypasses idle guard via force param)."""
    if _is_running:
        return {"status": "already_running", "stored": 0}
    stored = await _engine.run_cycle()
    return {"status": "completed", "stored": stored}
