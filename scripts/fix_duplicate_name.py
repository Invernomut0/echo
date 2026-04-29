#!/usr/bin/env python
"""Remove duplicate identity memories and optionally update the stored name."""
import asyncio, sys
sys.path.insert(0, "/Users/lorenzov/dev/ECHO/src")

async def main():
    from echo.core.db import get_session_factory, get_or_create_collection
    from echo.memory.semantic import SemanticRow
    from sqlalchemy import select

    factory = get_session_factory()

    # Find duplicates
    async with factory() as session:
        rows = (await session.execute(
            select(SemanticRow).where(SemanticRow.content == "The user's name is Lo.")
        )).scalars().all()

    print(f"Duplicate entries for 'The user's name is Lo.': {len(rows)}")
    for r in rows:
        print(f"  id={r.id[:8]}  embedding_id={r.embedding_id[:8] if r.embedding_id else 'None'}")

    if len(rows) > 1:
        to_delete = rows[1:]
        collection = get_or_create_collection("semantic_memory")

        # SQLite delete
        async with factory() as session:
            for r in to_delete:
                obj = await session.get(SemanticRow, r.id)
                if obj:
                    await session.delete(obj)
            await session.commit()

        # ChromaDB delete
        ids_to_remove = [r.id for r in to_delete]
        collection.delete(ids=ids_to_remove)
        print(f"Deleted {len(to_delete)} duplicates from SQLite + ChromaDB")

    # Verify all identity memories
    async with factory() as session:
        remaining = (await session.execute(
            select(SemanticRow).where(SemanticRow.content.ilike("%name is%"))
        )).scalars().all()

    print(f"\nIdentity memories remaining: {len(remaining)}")
    for r in remaining:
        print(f"  {r.content!r}  tags={r.tags}")

asyncio.run(main())
