"""Identity router — /api/identity (graph for D3.js)."""

from __future__ import annotations

from fastapi import APIRouter

from echo.api.schemas import GraphResponse
from echo.core.pipeline import pipeline

router = APIRouter(prefix="/api/identity", tags=["identity"])


@router.get("/graph", response_model=GraphResponse)
async def get_graph() -> GraphResponse:
    """Return identity belief graph for D3.js force-directed visualisation."""
    data = pipeline.identity_graph.to_dict()
    return GraphResponse(
        nodes=data["nodes"],
        edges=data["edges"],
        coherence_score=pipeline.identity_graph.coherence_score(),
    )
