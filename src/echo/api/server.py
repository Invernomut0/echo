"""FastAPI application server."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

# Load ALL variables from .env into os.environ early, so subprocesses (e.g. MCP
# servers) can inherit them even if they are not declared as Pydantic fields.
from dotenv import load_dotenv
load_dotenv(override=False)  # override=False: real env vars take precedence

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from echo.api.routers import consolidation, identity, interact, memory, mcp as mcp_router, setup, state
from echo.api.routers import curiosity as curiosity_router
from echo.api.routers import wiki as wiki_router
from echo.api.schemas import HealthResponse
from echo.core.config import settings
from echo.core.llm_client import llm
from echo.core.pipeline import pipeline

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting PROJECT ECHO cognitive pipeline…")
    await pipeline.startup()
    from echo.memory.wiki import wiki
    wiki.startup()
    yield
    logger.info("Shutting down…")
    await pipeline.shutdown()


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title="PROJECT ECHO",
        description="Persistent Self-Modifying Cognitive Architecture",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(interact.router)
    app.include_router(state.router)
    app.include_router(memory.router)
    app.include_router(identity.router)
    app.include_router(consolidation.router)
    app.include_router(setup.router)
    app.include_router(mcp_router.router)
    app.include_router(curiosity_router.router)
    app.include_router(wiki_router.router)

    # Health check
    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health() -> HealthResponse:
        available = await llm.is_available()
        return HealthResponse(
            status="ok" if available else "degraded",
            lm_studio_available=available,
        )

    # WebSocket — live event feed
    from fastapi import WebSocket, WebSocketDisconnect
    import json as _json

    @app.websocket("/ws/events")
    async def ws_events(websocket: WebSocket):
        await websocket.accept()
        from echo.core.event_bus import bus
        from echo.core.types import EventTopic
        try:
            async for event in bus.subscribe():
                await websocket.send_text(
                    _json.dumps({
                        "topic": event.topic.value,
                        "payload": event.payload,
                        "source_agent": event.source_agent,
                        "timestamp": event.timestamp.isoformat(),
                    })
                )
        except WebSocketDisconnect:
            pass

    # Serve frontend static build in production
    frontend_dist = Path(__file__).parent.parent.parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="static")
        logger.info("Serving frontend from %s", frontend_dist)

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(
        "echo.api.server:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
