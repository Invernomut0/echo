"""One-shot migration: fix decay_lambda and restore strength for existing memories.

The old formula used λ = 1 - salience (aggressive, memories died in hours).
The new formula uses λ = (1 - salience) × 0.005 (gentle, memories last months/years).

Run once after deploying the decay fix:
    .venv/bin/python -m echo.scripts.fix_decay_values
"""

import asyncio
import logging

from sqlalchemy import select

from echo.core.db import startup as db_startup, get_session_factory
from echo.memory.episodic import MemoryRow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    await db_startup()
    factory = get_session_factory()

    async with factory() as session:
        rows = (await session.execute(select(MemoryRow))).scalars().all()
        updated = 0
        for row in rows:
            # Recompute decay_lambda with the new gentle formula
            salience = row.salience or 0.5
            new_lambda = round((1.0 - salience) * 0.005, 6)
            old_lambda = row.decay_lambda

            row.decay_lambda = new_lambda

            # Restore strength for memories that were unfairly decayed
            if row.current_strength < 0.5:
                # Boost back to at least 0.7 — they were killed by the old aggressive decay
                row.current_strength = max(row.current_strength, 0.7)
                row.is_dormant = False

            updated += 1

        await session.commit()

    logger.info(
        "Migration complete: updated %d memories (old λ→new λ, restored strength)", updated
    )


if __name__ == "__main__":
    asyncio.run(main())
