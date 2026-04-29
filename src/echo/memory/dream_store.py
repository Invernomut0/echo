"""Dream store — persists REM dream entries in SQLite."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, select

from echo.core.db import Base, get_session_factory
from echo.core.types import DreamEntry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ORM model
# ---------------------------------------------------------------------------


class DreamRow(Base):
    __tablename__ = "dream_entries"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    dream = Column(Text, nullable=False)
    source_memory_count = Column(Integer, default=0)
    created_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    cycle_type = Column(String, default="rem")


def _row_to_entry(row: DreamRow) -> DreamEntry:
    return DreamEntry(
        id=row.id,
        dream=row.dream,
        source_memory_count=row.source_memory_count,
        created_at=datetime.fromisoformat(row.created_at),
        cycle_type=row.cycle_type,
    )


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class DreamStore:
    """Simple async store for dream entries backed by SQLite."""

    async def store(self, entry: DreamEntry) -> None:
        """Persist a new dream entry."""
        factory = get_session_factory()
        async with factory() as session:
            row = DreamRow(
                id=entry.id,
                dream=entry.dream,
                source_memory_count=entry.source_memory_count,
                created_at=entry.created_at.isoformat(),
                cycle_type=entry.cycle_type,
            )
            session.add(row)
            await session.commit()
        logger.debug("Dream stored: %s", entry.id)

    async def get_all(self, limit: int = 20) -> list[DreamEntry]:
        """Return the most recent dreams, newest first."""
        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(DreamRow)
                .order_by(DreamRow.created_at.desc())
                .limit(limit)
            )
            rows = result.scalars().all()
        return [_row_to_entry(r) for r in rows]
