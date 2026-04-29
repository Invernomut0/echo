"""State router — /api/state, /api/state/history."""

from __future__ import annotations

from fastapi import APIRouter

from echo.api.schemas import HistoryPoint, StateResponse
from echo.core.pipeline import pipeline

router = APIRouter(prefix="/api/state", tags=["state"])


@router.get("", response_model=StateResponse)
async def get_state() -> StateResponse:
    """Current cognitive state snapshot."""
    return StateResponse(
        meta_state=pipeline.meta_state,
        workspace_items=len(pipeline.workspace.snapshot.items),
        identity_beliefs=len(pipeline.identity_graph.all_beliefs()),
        episodic_memories=pipeline.episodic.count(),
        interaction_count=pipeline._interaction_count,
    )


@router.get("/history", response_model=list[HistoryPoint])
async def get_history(limit: int = 50) -> list[HistoryPoint]:
    """Drive time-series for Recharts plotting."""
    states = await pipeline.meta_tracker.get_history(limit=limit)
    return [
        HistoryPoint(
            timestamp=s.timestamp,
            drives={
                "coherence":   s.drives.coherence,
                "curiosity":   s.drives.curiosity,
                "stability":   s.drives.stability,
                "competence":  s.drives.competence,
                "compression": s.drives.compression,
            },
            emotional_valence=s.emotional_valence,
            arousal=s.arousal,
            agent_weights=s.agent_weights,
            drive_weights=s.drives.weights,
            total_motivation=s.drives.total_motivation(),
        )
        for s in states
    ]
