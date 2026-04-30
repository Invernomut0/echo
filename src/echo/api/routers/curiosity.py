"""Curiosity router — /api/curiosity."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

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


# ---------------------------------------------------------------------------
# Co-evolution endpoints
# ---------------------------------------------------------------------------

@router.get("/profile")
async def get_interest_profile():
    """Return the user's current interest profile: primary topics, ZPD candidates, excluded topics."""
    from echo.curiosity.interest_profile import interest_profile  # noqa: PLC0415

    primary = await interest_profile.primary_interests(n=10)
    zpd = await interest_profile.zpd_topics(n=4)
    excluded = await interest_profile.excluded_topics()
    all_topics = await interest_profile.all_topics()
    return {
        "primary_interests": primary,
        "zpd_topics": zpd,
        "excluded_topics": excluded,
        "total_topics": len(all_topics),
    }


@router.get("/findings")
async def get_findings(limit: int = Query(default=20, ge=1, le=100)):
    """Return pending (unshown) stimuli from the queue, ranked by affinity."""
    from echo.curiosity.stimulus_queue import stimulus_queue  # noqa: PLC0415

    pending = await stimulus_queue.pending(limit=limit)
    return {"pending": pending, "count": len(pending)}


@router.get("/findings/all")
async def get_all_findings(limit: int = Query(default=50, ge=1, le=200)):
    """Return all findings (including presented ones), newest first."""
    from echo.curiosity.stimulus_queue import stimulus_queue  # noqa: PLC0415

    items = await stimulus_queue.all_items(limit=limit)
    return {"items": items, "count": len(items)}


class FeedbackRequest(BaseModel):
    stimulus_id: str
    score: float  # 0.0–1.0


@router.post("/feedback")
async def submit_feedback(body: FeedbackRequest):
    """Record user feedback on a curiosity stimulus (0 = not relevant, 1 = very relevant)."""
    from echo.curiosity.stimulus_queue import stimulus_queue  # noqa: PLC0415

    if not (0.0 <= body.score <= 1.0):
        raise HTTPException(status_code=422, detail="score must be in [0, 1]")
    await stimulus_queue.record_feedback(body.stimulus_id, body.score)
    return {"status": "ok", "stimulus_id": body.stimulus_id, "score": body.score}


class GuideRequest(BaseModel):
    preferred: list[str] = []
    excluded: list[str] = []


@router.post("/guide")
async def guide_topics(body: GuideRequest):
    """Explicitly mark topics as preferred (+affinity) or excluded (hidden)."""
    from echo.curiosity.interest_profile import interest_profile  # noqa: PLC0415

    for topic in body.preferred:
        if topic.strip():
            await interest_profile.mark_preferred(topic.strip())
    for topic in body.excluded:
        if topic.strip():
            await interest_profile.mark_excluded(topic.strip())
    return {
        "status": "ok",
        "preferred_count": len(body.preferred),
        "excluded_count": len(body.excluded),
    }
