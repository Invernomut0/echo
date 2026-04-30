"""Async database layer — SQLAlchemy (SQLite) + ChromaDB."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from echo.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SQLAlchemy ORM base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Engine + session factory (created lazily)
# ---------------------------------------------------------------------------

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        db_path: Path = settings.sqlite_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite+aiosqlite:///{db_path}"
        _engine = create_async_engine(url, echo=False, future=True)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=_get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_factory


async def get_session() -> AsyncSession:  # noqa: D401
    """FastAPI dependency — yields an async DB session."""
    factory = get_session_factory()
    async with factory() as session:
        yield session  # type: ignore[misc]


async def init_db() -> None:
    """Create all tables. Safe to call multiple times (CREATE IF NOT EXISTS)."""
    # Import all ORM Row classes so Base.metadata is fully populated before create_all.
    # New models must be added here to ensure their tables are created.
    import echo.memory.episodic  # noqa: F401
    import echo.memory.semantic  # noqa: F401
    import echo.memory.autobiographical  # noqa: F401
    import echo.memory.dream_store  # noqa: F401
    import echo.self_model.identity_graph  # noqa: F401
    import echo.self_model.meta_state  # noqa: F401
    import echo.memory.goals  # noqa: F401

    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Enable WAL mode for better concurrency
    async with engine.connect() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA synchronous=NORMAL"))
    # ── Schema migrations (SQLite doesn't support IF NOT EXISTS on ADD COLUMN) ──
    async with engine.begin() as conn:
        for stmt in (
            "ALTER TABLE episodic_memories ADD COLUMN is_dormant INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE episodic_memories ADD COLUMN has_vector INTEGER NOT NULL DEFAULT 0",
        ):
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass  # Column already exists — safe to ignore
    logger.info("SQLite initialized at %s", settings.sqlite_path)


# ---------------------------------------------------------------------------
# ChromaDB client (persistent, embedded)
# ---------------------------------------------------------------------------

_chroma_client: chromadb.ClientAPI | None = None


def get_chroma_client() -> chromadb.ClientAPI:
    global _chroma_client
    if _chroma_client is None:
        chroma_path: Path = settings.chroma_path
        chroma_path.mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        logger.info("ChromaDB initialized at %s", chroma_path)
    return _chroma_client


def get_or_create_collection(
    name: str,
    metadata: dict[str, Any] | None = None,
) -> chromadb.Collection:
    """Return (or create) a named ChromaDB collection."""
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=name,
        metadata=metadata or {"hnsw:space": "cosine"},
    )


# ---------------------------------------------------------------------------
# Top-level init called at startup
# ---------------------------------------------------------------------------

async def startup() -> None:
    await init_db()
    get_chroma_client()
    logger.info("Database layer ready")
