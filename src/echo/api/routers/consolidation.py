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


@router.get("/heartbeat-log")
async def heartbeat_log(limit: int = Query(default=30, ge=1, le=50)):
    """Return last N heartbeat events (newest first) with actions and results."""
    return pipeline.consolidation.event_log[:limit]


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


# ---------------------------------------------------------------------------
# echo.md — ECHO's self-maintained personality file
# ---------------------------------------------------------------------------

@router.get("/echo-md")
async def get_echo_md():
    """Return the current content of ECHO's personality file (echo.md)."""
    from echo.self_model.echo_md import EchoMdManager  # noqa: PLC0415
    content = EchoMdManager().read()
    return {"content": content}


@router.post("/echo-md/review")
async def review_echo_md():
    """Manually trigger an echo.md review/update cycle."""
    from echo.self_model.echo_md import EchoMdManager  # noqa: PLC0415

    manager = EchoMdManager()
    _meta_state = None
    try:
        if pipeline._ready:
            _meta_state = pipeline.meta_state
    except Exception:  # noqa: BLE001
        pass

    last_report = pipeline.consolidation._last_report
    patterns = last_report.patterns_found if last_report else []

    updated = await manager.review_and_update(meta_state=_meta_state, patterns=patterns)
    content = manager.read()
    return {"updated": updated, "content": content}


# ---------------------------------------------------------------------------
# self_growth.md — ECHO's autonomous growth journal
# ---------------------------------------------------------------------------

@router.get("/self-growth")
async def get_self_growth():
    """Return the current content of ECHO's self-growth journal."""
    from pathlib import Path  # noqa: PLC0415

    repo_root = Path(__file__).parent.parent.parent.parent.parent
    path = repo_root / "notes" / "self_growth.md"
    if not path.exists():
        return {"content": "*(no entries yet)*"}
    return {"content": path.read_text(encoding="utf-8")}


# ---------------------------------------------------------------------------
# notes/ — individual commit/change notes written by the self-mod engine
# ---------------------------------------------------------------------------

@router.get("/notes")
async def list_notes():
    """Return a sorted list of note filenames in the notes/ folder (newest first).

    Excludes self_growth.md which is served separately.
    Each entry: {"name": str, "date": str, "title": str}
    """
    from pathlib import Path  # noqa: PLC0415

    repo_root = Path(__file__).parent.parent.parent.parent.parent
    notes_dir = repo_root / "notes"
    if not notes_dir.exists():
        return {"notes": []}

    items = []
    for p in sorted(notes_dir.glob("*.md"), reverse=True):
        if p.name == "self_growth.md":
            continue
        # Try to extract the title from the first non-empty line
        title = p.stem
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                stripped = line.strip().lstrip("#").strip()
                if stripped:
                    title = stripped
                    break
        except OSError:
            pass
        # Extract date prefix (YYYY-MM-DD) from filename if present
        date = p.stem[:10] if len(p.stem) >= 10 and p.stem[4] == "-" else ""
        items.append({"name": p.name, "date": date, "title": title})

    return {"notes": items}


@router.get("/notes/{note_name}")
async def get_note(note_name: str):
    """Return the content of a single note file.

    Only `.md` files inside the notes/ directory are accessible.
    """
    from pathlib import Path  # noqa: PLC0415

    # Security: reject path traversal attempts
    if "/" in note_name or "\\" in note_name or not note_name.endswith(".md"):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid note name.")

    repo_root = Path(__file__).parent.parent.parent.parent.parent
    path = (repo_root / "notes" / note_name).resolve()
    notes_dir = (repo_root / "notes").resolve()

    # Ensure resolved path is still inside notes/
    if not str(path).startswith(str(notes_dir) + "/"):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid note name.")

    if not path.exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Note not found.")

    return {"name": note_name, "content": path.read_text(encoding="utf-8")}
