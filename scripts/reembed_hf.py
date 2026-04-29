#!/usr/bin/env python
"""
Re-embed ALL semantic memories using HuggingFace multilingual model.

Usage:
    cd /Users/lorenzov/dev/ECHO
    .venv/bin/python scripts/reembed_hf.py

This script:
  1. Reads every memory from SQLite
  2. Calls HuggingFace _hf_embed() directly (bypasses LM Studio)
  3. Replaces all ChromaDB vectors with fresh multilingual embeddings
  4. Prints a summary report
"""

import asyncio
import sys
from pathlib import Path

# Make sure we can import echo modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


async def main() -> None:
    from echo.core.config import settings
    from echo.core.llm_client import LLMClient
    from echo.core.db import get_session_factory, get_or_create_collection
    from echo.memory.semantic import SemanticRow

    from sqlalchemy import select

    print(f"HF model     : {settings.hf_embedding_model}")
    print(f"HF token set : {'yes' if settings.hf_token else 'NO — set HF_TOKEN in .env!'}")
    if not settings.hf_token:
        sys.exit(1)

    # ── 1. Load all rows from SQLite ──────────────────────────────────────────
    factory = get_session_factory()
    async with factory() as session:
        rows = (await session.execute(select(SemanticRow))).scalars().all()

    print(f"Memories in SQLite: {len(rows)}")
    if not rows:
        print("Nothing to do.")
        return

    # ── 2. Call HuggingFace in batches ────────────────────────────────────────
    client = LLMClient()
    contents = [r.content for r in rows]

    BATCH = 32          # HF Inference API accepts ~32 texts per call safely
    all_vectors: list[list[float]] = []

    for i in range(0, len(contents), BATCH):
        batch = contents[i : i + BATCH]
        print(f"  Embedding batch {i // BATCH + 1} / {-(-len(contents) // BATCH)}  "
              f"({len(batch)} texts)…", end="", flush=True)
        vecs = await client._hf_embed(batch)       # noqa: SLF001 — intentional direct call
        if len(vecs) != len(batch):
            print(f"  FAILED (got {len(vecs)} vectors for {len(batch)} texts)")
            sys.exit(1)
        all_vectors.extend(vecs)
        print(" ✓")

    dim = len(all_vectors[0]) if all_vectors else "?"
    print(f"Embedding dim: {dim}  (expected 768)")

    # ── 3. Replace ChromaDB collection ───────────────────────────────────────
    collection = get_or_create_collection("semantic_memory")
    current_count = collection.count()
    print(f"ChromaDB vectors before: {current_count}")

    # Delete all existing vectors
    if current_count > 0:
        existing = collection.get(include=[])
        collection.delete(ids=existing["ids"])
        print(f"  Deleted {len(existing['ids'])} old vectors")

    # Re-insert with fresh HF vectors
    import json
    ids = [r.id for r in rows]
    metadatas = [{"salience": r.salience} for r in rows]
    documents = contents

    collection.upsert(
        ids=ids,
        embeddings=all_vectors,
        documents=documents,
        metadatas=metadatas,
    )
    print(f"  Inserted {len(ids)} new vectors")

    # ── 4. Sync embedding_id in SQLite (ensure it matches the row id) ─────────
    updated = 0
    async with factory() as session:
        for row in rows:
            if row.embedding_id != row.id:
                db_row = await session.get(SemanticRow, row.id)
                if db_row:
                    db_row.embedding_id = row.id
                    updated += 1
        await session.commit()

    if updated:
        print(f"  Fixed embedding_id mismatch in SQLite: {updated} rows")

    # ── 5. Verify: spot-check retrieval ──────────────────────────────────────
    print("\n── Spot-check retrieval ─────────────────────────────────────────")
    test_queries = [
        "come mi chiamo?",
        "qual è il mio nome?",
        "nome utente",
        "chi sono io",
        "user name",
    ]
    for q in test_queries:
        q_vec = await client._hf_embed([q])       # noqa: SLF001
        if not q_vec:
            print(f"  [{q!r}] — embedding failed")
            continue
        results = collection.query(
            query_embeddings=q_vec,
            n_results=3,
            include=["documents", "distances"],
        )
        docs = results.get("documents", [[]])[0]
        dists = results.get("distances", [[]])[0]
        print(f"\n  Query: {q!r}")
        for doc, dist in zip(docs, dists):
            sim = round(1 - dist, 3)
            print(f"    [{sim:+.3f}]  {doc[:90]}")

    print("\n✅ Re-embedding complete!")
    print("Restart the ECHO backend for changes to take effect.")


if __name__ == "__main__":
    asyncio.run(main())
