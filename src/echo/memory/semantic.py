"""Semantic memory — facts and general knowledge nodes (ChromaDB + SQLite)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import math
import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import Column, Float, Integer, String, Text, select

from echo.core.db import Base, get_or_create_collection, get_session_factory
from echo.core.llm_client import llm
from echo.core.types import MemoryEntry, MemoryType
from echo.memory.chunker import chunk_ids, chunk_text, memory_id_from_chunk_id

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "semantic_memory"

# ---------------------------------------------------------------------------
# Conflict-detection patterns
# Each entry: (category_name, compiled_regex).
# The regex must capture the claimed value in group 1.
# Patterns are intentionally English-only: memories are stored in canonical
# English form ("The user's name is …"). The multilingual embedding model
# handles cross-lingual retrieval, so no hardcoded foreign-language keywords
# are needed here.
# ---------------------------------------------------------------------------
_CONFLICT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "user_name",
        re.compile(
            r"the\s+user'?s?\s+name\s+is\s+([A-Za-zÀ-ÖØ-öø-ÿ'.\-]{2,40})",
            re.IGNORECASE,
        ),
    ),
]


class SemanticRow(Base):
    __tablename__ = "semantic_memories"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    content = Column(Text, nullable=False)
    salience = Column(Float, default=0.5)
    current_strength = Column(Float, default=1.0)
    decay_lambda = Column(Float, default=0.3)
    embedding_id = Column(String, nullable=True)
    tags = Column(Text, default="[]")
    created_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    access_count = Column(Integer, default=0)
    source_agent = Column(String, default="system")


class SemanticMemoryStore:
    """Store general factual knowledge."""

    # Class-level flag: run backfill once per server process
    _backfill_done: bool = False

    def __init__(self) -> None:
        self._collection = get_or_create_collection(_COLLECTION_NAME)

    async def store(
        self, content: str, tags: list[str] | None = None, salience: float = 0.7
    ) -> MemoryEntry:
        # ── Dedup: skip exact-content duplicates ─────────────────────────
        norm_content = content.strip()
        factory = get_session_factory()
        async with factory() as session:
            existing_row = (
                await session.execute(
                    select(SemanticRow).where(SemanticRow.content == norm_content)
                )
            ).scalar_one_or_none()
            if existing_row is not None:
                # If the new salience is higher, update it
                if salience > existing_row.salience:
                    existing_row.salience = salience
                    existing_row.decay_lambda = round(1.0 - salience, 4)
                    await session.commit()
                logger.debug(
                    "Semantic store dedup: content already exists (%s), skipping",
                    existing_row.id[:8],
                )
                return MemoryEntry(
                    id=existing_row.id,
                    content=existing_row.content,
                    memory_type=MemoryType.SEMANTIC,
                    salience=max(salience, existing_row.salience),
                    decay_lambda=existing_row.decay_lambda,
                    tags=json.loads(existing_row.tags or "[]"),
                    embedding_id=existing_row.embedding_id,
                )

        entry_id = str(uuid.uuid4())

        # Chunk long texts so each segment gets its own embedding vector.
        # Short texts (≤ CHUNK_MIN_LEN chars) return a single-element list.
        chunks = chunk_text(norm_content)
        vectors = await llm.embed(chunks)  # batch: one call regardless of chunk count

        decay_lambda = round(1.0 - salience, 4)
        # Only set embedding_id when vectors are actually stored in ChromaDB.
        # If embedding fails, embedding_id stays None so backfill can detect it.
        embedding_id: str | None = None
        if vectors and len(vectors) == len(chunks):
            ids_c = chunk_ids(entry_id, len(chunks))
            try:
                self._collection.upsert(
                    ids=ids_c,
                    embeddings=vectors,
                    documents=chunks,
                    metadatas=[
                        {"memory_id": entry_id, "chunk_index": i, "salience": salience}
                        for i in range(len(chunks))
                    ],
                )
                embedding_id = ids_c[0]
            except Exception as exc:  # noqa: BLE001
                logger.warning("ChromaDB upsert skipped for semantic %s: %s", entry_id[:8], exc)
        else:
            logger.warning(
                "Embedding failed for semantic memory %s — stored in SQLite only; "
                "will be backfilled on next retrieve.",
                entry_id[:8],
            )

        factory = get_session_factory()
        async with factory() as session:
            row = SemanticRow(
                id=entry_id,
                content=norm_content,
                salience=salience,
                decay_lambda=decay_lambda,
                embedding_id=embedding_id,  # None when embedding failed
                tags=json.dumps(tags or []),
            )
            session.add(row)
            await session.commit()

        return MemoryEntry(
            id=entry_id,
            content=norm_content,
            memory_type=MemoryType.SEMANTIC,
            salience=salience,
            decay_lambda=decay_lambda,
            tags=tags or [],
            embedding_id=embedding_id,
        )

    async def backfill_embeddings(self) -> int:
        """Re-embed SQLite memories whose vectors are missing from ChromaDB.

        Catches two cases:
        1. embedding_id is set in SQLite but that ID is absent from ChromaDB
           (old bug: store() always wrote embedding_id even on embed failure).
        2. embedding_id is NULL (new behaviour after this fix).

        Returns count of memories that were successfully backfilled.
        """
        chroma_ids: set[str] = set()
        if self._collection.count() > 0:
            result = self._collection.get(include=[])
            chroma_ids = set(result["ids"])

        factory = get_session_factory()
        async with factory() as session:
            rows = (await session.execute(select(SemanticRow))).scalars().all()

        orphans = [
            r for r in rows
            if (r.embedding_id and r.embedding_id not in chroma_ids)
            or (not r.embedding_id)
        ]

        if not orphans:
            logger.debug(
                "backfill_embeddings: all %d memories have vectors, nothing to do",
                len(rows),
            )
            return 0

        logger.info(
            "backfill_embeddings: found %d orphan memories to re-embed (SQLite=%d, ChromaDB=%d)",
            len(orphans), len(rows), len(chroma_ids),
        )
        backfilled = 0
        for row in orphans:
            chunks = chunk_text(row.content)
            vectors = await llm.embed(chunks)
            if not vectors or len(vectors) != len(chunks):
                logger.warning(
                    "backfill: re-embed still failed for %s, skipping", row.id[:8]
                )
                continue

            ids_c = chunk_ids(row.id, len(chunks))
            try:
                self._collection.upsert(
                    ids=ids_c,
                    embeddings=vectors,
                    documents=chunks,
                    metadatas=[
                        {"memory_id": row.id, "chunk_index": i, "salience": row.salience}
                        for i in range(len(chunks))
                    ],
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("backfill: ChromaDB upsert failed for %s: %s", row.id[:8], exc)
                continue

            for cid in ids_c:
                chroma_ids.add(cid)

            # Repair embedding_id in SQLite if it was None
            if not row.embedding_id:
                async with factory() as session:
                    r = await session.get(SemanticRow, row.id)
                    if r:
                        r.embedding_id = ids_c[0]
                        await session.commit()

            backfilled += 1
            logger.info(
                "Backfilled embedding for %s: %s",
                row.id[:8],
                row.content[:60],
            )

        logger.info(
            "backfill_embeddings: backfilled %d / %d orphan memories",
            backfilled, len(orphans),
        )
        return backfilled

    async def retrieve_similar(self, query: str, n_results: int = 5, query_vector: list[float] | None = None) -> list[MemoryEntry]:
        # Self-healing: backfill missing ChromaDB vectors on first call per process
        if not SemanticMemoryStore._backfill_done:
            SemanticMemoryStore._backfill_done = True
            try:
                await self.backfill_embeddings()
            except Exception as exc:
                logger.warning("backfill_embeddings failed during retrieve: %s", exc)

        loop = asyncio.get_event_loop()
        entries: list[MemoryEntry] = []

        # Primary path: vector search in ChromaDB.
        # The multilingual embedding model (paraphrase-multilingual-mpnet-base-v2)
        # maps queries in any language close to their English equivalents, so a
        # single vector search is enough — no language-specific expansion needed.
        col_count = await loop.run_in_executor(None, self._collection.count)
        if col_count > 0:
            vector = query_vector if query_vector else await llm.embed_one(query)

            if vector:
                results = await loop.run_in_executor(
                    None,
                    lambda: self._collection.query(
                        query_embeddings=[vector],
                        n_results=min(n_results * 3, col_count),
                        include=["documents", "metadatas", "distances"],
                    ),
                )
                # Filter by cosine distance — discard memories too dissimilar to the query.
                # ChromaDB cosine space: distance = 1 - cosine_similarity (0 = identical, 2 = opposite).
                # 0.5 → similarity ≥ 0.5, a reasonable relevance floor.
                _MAX_COSINE_DIST = 0.5
                ids_c = results.get("ids", [[]])[0]
                docs = results.get("documents", [[]])[0]
                metas = results.get("metadatas", [[]])[0]
                dists = results.get("distances", [[]])[0]

                # Deduplicate chunk results → keep the best-matching chunk per memory.
                # "best" = lowest cosine distance.  For legacy single-vector entries the
                # memory_id is stored in metadata; for very old entries we fall back to
                # extracting it from the chunk ID itself.
                best_chunk: dict[str, tuple[str, dict, float]] = {}  # mem_id → (doc, meta, dist)
                for chunk_id, doc, meta, dist in zip(ids_c, docs, metas, dists):
                    if dist > _MAX_COSINE_DIST:
                        continue
                    mem_id = meta.get("memory_id") or memory_id_from_chunk_id(chunk_id)
                    if mem_id not in best_chunk or dist < best_chunk[mem_id][2]:
                        best_chunk[mem_id] = (doc, meta, dist)

                for doc, meta, _dist in best_chunk.values():
                    entries.append(
                        MemoryEntry(
                            content=doc,
                            memory_type=MemoryType.SEMANTIC,
                            salience=meta.get("salience", 0.5),
                        )
                    )

        # Safety fallback: SQLite rows still missing a vector (embedding keeps failing)
        # Include high-salience ones so identity facts are never silently lost.
        if len(entries) < n_results:
            factory = get_session_factory()
            async with factory() as session:
                stmt = (
                    select(SemanticRow)
                    .where(SemanticRow.embedding_id.is_(None))
                    .where(SemanticRow.salience >= 0.7)
                    .order_by(SemanticRow.salience.desc())
                    .limit(n_results - len(entries))
                )
                still_orphaned = (await session.execute(stmt)).scalars().all()
            existing = {e.content for e in entries}
            for row in still_orphaned:
                if row.content not in existing:
                    entries.append(
                        MemoryEntry(
                            id=row.id,
                            content=row.content,
                            memory_type=MemoryType.SEMANTIC,
                            salience=row.salience,
                            current_strength=row.current_strength,
                            decay_lambda=row.decay_lambda,
                            tags=json.loads(row.tags or "[]"),
                        )
                    )

        return entries[:n_results]

    def count(self) -> int:
        return self._collection.count()

    async def get_all(self, limit: int = 200) -> list[MemoryEntry]:
        """Return all semantic memories from SQLite."""
        from sqlalchemy import func
        factory = get_session_factory()
        async with factory() as session:
            stmt = select(SemanticRow).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
        return [
            MemoryEntry(
                id=r.id,
                content=r.content,
                memory_type=MemoryType.SEMANTIC,
                salience=r.salience,
                current_strength=r.current_strength,
                decay_lambda=r.decay_lambda,
                embedding_id=r.embedding_id,
                tags=json.loads(r.tags or "[]"),
                created_at=datetime.fromisoformat(r.created_at),
                access_count=r.access_count,
                source_agent=r.source_agent,
                has_vector=bool(r.embedding_id),  # embedding_id is set only when stored
            )
            for r in rows
        ]

    async def get_all_chunks(
        self,
        limit: int = 200,
        embedding_preview_len: int = 12,
    ) -> list[dict]:
        """Return all semantic memories together with their ChromaDB chunks.

        Each returned dict matches the ``MemoryWithChunks`` Pydantic schema.
        Fetches all ChromaDB vectors in one shot (no N+1) and groups by memory_id.
        """
        # 1 — Load SQLite rows
        factory = get_session_factory()
        async with factory() as session:
            stmt = select(SemanticRow).order_by(SemanticRow.created_at.desc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()

        if not rows:
            return []

        # 2 — Load all ChromaDB chunks in one call (with embeddings)
        chroma_by_mem: dict[str, list[dict]] = defaultdict(list)
        if self._collection.count() > 0:
            raw = self._collection.get(include=["documents", "metadatas", "embeddings"])
            ids_c: list[str] = raw.get("ids") or []
            docs: list[str | None] = raw.get("documents") or []
            metas: list[dict] = raw.get("metadatas") or []
            _emb_raw = raw.get("embeddings")
            embeds: list = _emb_raw if _emb_raw is not None else []

            for cid, doc, meta, emb in zip(ids_c, docs, metas, embeds):
                mem_id: str = meta.get("memory_id") or memory_id_from_chunk_id(cid)
                chunk_idx: int = int(meta.get("chunk_index", 0))
                emb_list: list[float] = list(emb) if emb is not None else []
                chroma_by_mem[mem_id].append(
                    {
                        "chunk_id": cid,
                        "chunk_index": chunk_idx,
                        "text": doc or "",
                        "char_count": len(doc or ""),
                        "embedding_dim": len(emb_list),
                        "embedding_preview": emb_list[:embedding_preview_len],
                    }
                )

        # 3 — Build result list (preserve SQLite ordering)
        result: list[dict] = []
        for row in rows:
            chunks = sorted(
                chroma_by_mem.get(row.id, []),
                key=lambda c: c["chunk_index"],
            )
            result.append(
                {
                    "memory_id": row.id,
                    "content": row.content,
                    "salience": row.salience,
                    "created_at": datetime.fromisoformat(row.created_at),
                    "tags": json.loads(row.tags or "[]"),
                    "chunk_count": len(chunks),
                    "chunks": chunks,
                }
            )
        return result

    async def apply_decay(self, elapsed_seconds: float) -> int:
        """Apply exponential decay I(t) = I₀·e^(−λ·Δt) to all semantic memories.

        Returns count of memories below 0.01 strength (prunable).
        """
        elapsed_hours = elapsed_seconds / 3600.0
        factory = get_session_factory()
        prunable = 0
        async with factory() as session:
            rows = (await session.execute(select(SemanticRow))).scalars().all()
            for row in rows:
                new_strength = row.current_strength * math.exp(
                    -row.decay_lambda * elapsed_hours
                )
                row.current_strength = max(0.0, round(new_strength, 6))
                if row.current_strength < 0.01:
                    prunable += 1
            await session.commit()
        logger.debug("Semantic decay applied to %d memories (%d prunable)", len(rows), prunable)
        return prunable

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    async def delete(self, memory_id: str) -> bool:
        """Delete a semantic memory from both SQLite and ChromaDB.

        Returns True if the row existed and was deleted, False otherwise.
        """
        factory = get_session_factory()
        async with factory() as session:
            row = await session.get(SemanticRow, memory_id)
            if row is None:
                return False
            chroma_id = row.embedding_id
            content_snippet = row.content[:60]
            await session.delete(row)
            await session.commit()

        if chroma_id:
            try:
                self._collection.delete(ids=[chroma_id])
            except Exception as exc:  # noqa: BLE001
                logger.warning("ChromaDB delete failed for %s: %s", chroma_id[:8], exc)

        logger.info("Deleted semantic memory %s: %s…", memory_id[:8], content_snippet)
        return True

    # ------------------------------------------------------------------
    # Spurious / conflicting memory cleanup
    # ------------------------------------------------------------------

    async def _get_all_rows(self) -> list[SemanticRow]:
        """Return all SemanticRow objects from SQLite (detached, safe to inspect)."""
        factory = get_session_factory()
        async with factory() as session:
            rows = (await session.execute(select(SemanticRow))).scalars().all()
        return list(rows)

    # ── Phase-2 helpers: vector-based similarity + contradiction detection ──

    async def _find_similar_pairs(
        self,
        threshold: float = 0.30,
    ) -> list[tuple[SemanticRow, SemanticRow]]:
        """Return pairs of semantically similar memories (cosine-distance < threshold).

        Uses ChromaDB's own stored vectors — no re-embedding is needed.
        With ``hnsw:space = "cosine"`` the distance is ``1 - cosine_similarity``,
        so threshold 0.30 ≈ similarity ≥ 0.70.
        """
        all_rows = await self._get_all_rows()
        rows_with_vec = [r for r in all_rows if r.embedding_id]
        if len(rows_with_vec) < 2:
            return []

        # Batch-fetch all embeddings from ChromaDB in a single call
        chroma_ids = [r.embedding_id for r in rows_with_vec]
        try:
            batch = self._collection.get(ids=chroma_ids, include=["embeddings"])
        except Exception as exc:
            logger.warning("_find_similar_pairs: ChromaDB batch-get failed: %s", exc)
            return []

        id_to_vec: dict[str, list[float]] = {
            cid: emb
            for cid, emb in zip(batch["ids"], batch["embeddings"], strict=False)
            if emb is not None
        }
        id_to_row: dict[str, SemanticRow] = {
            r.embedding_id: r
            for r in rows_with_vec
            if r.embedding_id
        }

        checked_pairs: set[frozenset] = set()
        similar_pairs: list[tuple[SemanticRow, SemanticRow]] = []
        n_neighbors = min(6, len(rows_with_vec))

        for row in rows_with_vec:
            vec = id_to_vec.get(row.embedding_id)
            if vec is None:
                continue
            try:
                neighbors = self._collection.query(
                    query_embeddings=[vec],
                    n_results=n_neighbors,
                    include=["distances"],
                )
            except Exception as exc:
                logger.debug(
                    "_find_similar_pairs: query failed for %s: %s", row.id[:8], exc
                )
                continue

            for nid, dist in zip(neighbors["ids"][0], neighbors["distances"][0], strict=False):
                if nid == row.embedding_id:
                    continue
                if dist > threshold:
                    continue
                pair: frozenset = frozenset([row.embedding_id, nid])
                if pair in checked_pairs:
                    continue
                checked_pairs.add(pair)
                if nid in id_to_row:
                    similar_pairs.append((row, id_to_row[nid]))

        logger.debug("_find_similar_pairs: found %d similar pair(s)", len(similar_pairs))
        return similar_pairs

    async def _are_contradictory(self, fact_a: str, fact_b: str) -> tuple[bool, str]:
        """Ask the LLM whether two facts directly contradict each other.

        Returns ``(is_contradiction, explanation_text)``.
        """
        prompt = (
            "You are a fact-checking assistant. Read these two statements and decide "
            "whether they *directly contradict* each other "
            "(i.e. both cannot simultaneously be true).\n\n"
            f"Statement A: {fact_a}\n"
            f"Statement B: {fact_b}\n\n"
            "Reply with exactly ONE of:\n"
            "• YES: <brief reason>  — if they contradict\n"
            "• NO: <brief reason>   — if they are compatible or just different perspectives\n\n"
            "Do not output anything else."
        )
        try:
            answer = (
                await llm.chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=120,
                )
            ).strip()
            return answer.upper().startswith("YES"), answer
        except Exception as exc:
            logger.warning("_are_contradictory: LLM call failed: %s", exc)
            return False, ""

    async def _resolve_via_web(self, fact_a: str, fact_b: str) -> dict:
        """Try to determine which of two contradictory facts is correct via web search.

        Returns::

            {
                "winner": "fact text" | None,
                "loser":  "fact text" | None,
                "confidence": 0.0–1.0,
                "sources": [{"title": ..., "url": ..., "source": ...}, ...],
            }
        """
        # 1. Generate a precise search query
        search_query: str = fact_a[:80]  # safe fallback
        with contextlib.suppress(Exception):
            search_query = (
                await llm.chat(
                    [
                        {
                            "role": "user",
                            "content": (
                                "I need to verify which fact is correct:\n"
                                f"A) {fact_a}\n"
                                f"B) {fact_b}\n"
                                "Write a short web search query "
                                "(max 10 words) to find the correct "
                                "answer. Output ONLY the query."
                            ),
                        }
                    ],
                    temperature=0.0,
                    max_tokens=30,
                )
            ).strip().strip('"').strip("'")

        # 2. Run Wikipedia + DuckDuckGo (no API keys needed)
        from echo.curiosity.web_search import (  # noqa: PLC0415
            duckduckgo_search,
            wikipedia_search,
        )

        web_results = []
        try:
            web_results.extend(await wikipedia_search(search_query, max_results=2))
        except Exception as exc:
            logger.debug("Wikipedia search failed during conflict resolution: %s", exc)
        try:
            web_results.extend(await duckduckgo_search(search_query, max_results=2))
        except Exception as exc:
            logger.debug("DuckDuckGo search failed during conflict resolution: %s", exc)

        sources = [
            {"title": r.title[:80], "url": r.url, "source": r.source}
            for r in web_results[:4]
        ]
        if not web_results:
            return {"winner": None, "loser": None, "confidence": 0.0, "sources": []}

        # 3. Ask the LLM to evaluate search results
        context = "\n".join(
            f"[{r.source.upper()}] {r.title}: {r.snippet[:300]}"
            for r in web_results[:4]
        )
        eval_prompt = (
            f"Based on these web search results:\n\n{context}\n\n"
            "Which fact do the results support?\n"
            f"A) {fact_a}\n"
            f"B) {fact_b}\n\n"
            "Reply with EXACTLY ONE of:\n"
            "• 'A <confidence>%'  — results clearly support fact A\n"
            "• 'B <confidence>%'  — results clearly support fact B\n"
            "• 'UNCLEAR'          — results don't help determine which is correct\n\n"
            "Only output one of these three options."
        )
        try:
            answer = (
                await llm.chat(
                    [{"role": "user", "content": eval_prompt}],
                    temperature=0.0,
                    max_tokens=20,
                )
            ).strip().upper()
            if answer.startswith("A"):
                m = re.search(r"(\d+)", answer)
                confidence = int(m.group(1)) / 100.0 if m else 0.7
                return {
                    "winner": fact_a,
                    "loser": fact_b,
                    "confidence": confidence,
                    "sources": sources,
                }
            if answer.startswith("B"):
                m = re.search(r"(\d+)", answer)
                confidence = int(m.group(1)) / 100.0 if m else 0.7
                return {
                    "winner": fact_b,
                    "loser": fact_a,
                    "confidence": confidence,
                    "sources": sources,
                }
        except Exception as exc:
            logger.warning("_resolve_via_web: LLM evaluation failed: %s", exc)

        return {"winner": None, "loser": None, "confidence": 0.0, "sources": sources}

    async def detect_and_clean_conflicts(
        self,
        *,
        dry_run: bool = False,
        similarity_threshold: float = 0.30,
        auto_resolve_confidence: float = 0.80,
    ) -> dict[str, list[dict]]:
        """Detect and resolve conflicting / duplicate semantic memories.

        **Phase 1 — Regex patterns (fast, structured facts)**
          For each ``_CONFLICT_PATTERNS`` entry, collect matching rows, deduplicate
          exact duplicates, then resolve cross-value conflicts by salience ratio.

        **Phase 2 — Vector-based semantic clustering (general facts)**
          Find all pairs of memories whose ChromaDB cosine-distance is below
          *similarity_threshold* (≥ 0.70 similarity by default).  For each pair:

          1. Ask the LLM whether the two facts contradict each other.
          2. If contradictory, attempt resolution via web search
             (Wikipedia + DuckDuckGo, no API keys required).
          3. If the web search yields a confident answer
             (≥ *auto_resolve_confidence*), auto-delete the incorrect memory.
          4. Otherwise, add both candidates to ``needs_review`` so the user can
             decide via ``POST /api/memory/resolve``.

        Args:
            dry_run: When True, plan deletes but do not execute them.
            similarity_threshold: ChromaDB cosine-distance below which two
                memories are *similar enough to check* (default 0.30 ≈
                cosine-similarity ≥ 0.70).
            auto_resolve_confidence: Minimum web-search confidence (0–1) to
                auto-delete the losing memory (default 0.80 = 80 %).

        Returns::

            {
                "auto_fixed": [
                    {"memory_id": "...", "content": "...", "reason": "..."},
                    …
                ],
                "needs_review": [
                    {
                        "category": "...",
                        "contradiction_explanation": "...",
                        "web_sources": [...],
                        "candidates": [
                            {"id": "...", "content": "...",
                             "salience": 0.9, "access_count": 3},
                            …
                        ],
                    },
                    …
                ],
            }
        """
        all_rows = await self._get_all_rows()
        auto_fixed: list[dict] = []
        needs_review: list[dict] = []

        # ── Phase 1: Regex-based structured conflicts ─────────────────────────
        for category, pattern in _CONFLICT_PATTERNS:
            matching = [r for r in all_rows if pattern.search(r.content)]
            if len(matching) <= 1:
                continue

            # Exact-content deduplication
            content_groups: dict[str, list[SemanticRow]] = defaultdict(list)
            for row in matching:
                key = row.content.strip().lower()
                content_groups[key].append(row)

            champions: list[SemanticRow] = []
            for group in content_groups.values():
                if len(group) == 1:
                    champions.append(group[0])
                    continue
                group_sorted = sorted(
                    group,
                    key=lambda r: (r.salience, r.access_count, r.created_at),
                    reverse=True,
                )
                champions.append(group_sorted[0])
                for loser in group_sorted[1:]:
                    if not dry_run:
                        await self.delete(loser.id)
                    auto_fixed.append({
                        "memory_id": loser.id,
                        "content": loser.content,
                        "reason": (
                            f"Exact duplicate of {group_sorted[0].id[:8]} "
                            f"(category={category})"
                        ),
                    })

            if len(champions) <= 1:
                continue

            def _extract_value(r: SemanticRow, _pat: re.Pattern = pattern) -> str:
                m = _pat.search(r.content)
                return m.group(1).strip().lower() if m else r.content[:40].lower()

            value_groups: dict[str, list[SemanticRow]] = defaultdict(list)
            for c in champions:
                value_groups[_extract_value(c)].append(c)

            if len(value_groups) <= 1:
                continue

            value_champions = [
                (val, max(rows, key=lambda r: (r.salience, r.access_count)))
                for val, rows in value_groups.items()
            ]
            value_champions.sort(key=lambda t: t[1].salience, reverse=True)
            best_val, best_row = value_champions[0]
            rest = value_champions[1:]

            can_auto_resolve = all(
                best_row.salience >= 1.5 * other_row.salience
                for _, other_row in rest
            )
            if can_auto_resolve:
                for _, loser in rest:
                    if not dry_run:
                        await self.delete(loser.id)
                    auto_fixed.append({
                        "memory_id": loser.id,
                        "content": loser.content,
                        "reason": (
                            f"Conflicting {category}: value '{_extract_value(loser)}' "
                            f"overridden by '{best_val}' "
                            f"(salience {best_row.salience:.2f} ≥ 1.5× "
                            f"{loser.salience:.2f})"
                        ),
                    })
            else:
                needs_review.append({
                    "category": category,
                    "contradiction_explanation": f"Conflicting values for {category}",
                    "web_sources": [],
                    "candidates": [
                        {
                            "id": row.id,
                            "content": row.content,
                            "salience": row.salience,
                            "access_count": row.access_count,
                        }
                        for _, row in value_champions
                    ],
                })

        # ── Phase 2: Vector-based semantic contradiction detection ─────────────
        if self._collection.count() >= 2:
            try:
                similar_pairs = await self._find_similar_pairs(
                    threshold=similarity_threshold
                )
            except Exception as exc:
                logger.warning(
                    "detect_and_clean_conflicts: _find_similar_pairs failed: %s", exc
                )
                similar_pairs = []

            # Guard: don't hammer the LLM on large memories stores
            _MAX_PAIRS = 20
            if len(similar_pairs) > _MAX_PAIRS:
                logger.info(
                    "detect_and_clean_conflicts: capping %d pairs at %d for LLM budget",
                    len(similar_pairs),
                    _MAX_PAIRS,
                )
                similar_pairs = similar_pairs[:_MAX_PAIRS]

            # Track which memory IDs have already been handled (Phase 1 + prior pairs)
            already_handled: set[str] = {item["memory_id"] for item in auto_fixed}
            for nr in needs_review:
                for cand in nr.get("candidates", []):
                    already_handled.add(cand["id"])

            for row_a, row_b in similar_pairs:
                if row_a.id in already_handled or row_b.id in already_handled:
                    continue

                # Skip exact-content duplicates (already handled or not a conflict)
                if row_a.content.strip().lower() == row_b.content.strip().lower():
                    continue

                # Step 1: LLM contradiction check
                try:
                    is_contradiction, explanation = await self._are_contradictory(
                        row_a.content, row_b.content
                    )
                except Exception as exc:
                    logger.debug(
                        "Contradiction check error (%s, %s): %s",
                        row_a.id[:8],
                        row_b.id[:8],
                        exc,
                    )
                    continue

                if not is_contradiction:
                    continue

                logger.info(
                    "Contradiction detected: '%s…' vs '%s…' — %s",
                    row_a.content[:40],
                    row_b.content[:40],
                    explanation[:80],
                )

                # Step 2: Web resolution attempt
                try:
                    resolution = await self._resolve_via_web(row_a.content, row_b.content)
                except Exception as exc:
                    logger.warning("Web resolution error: %s", exc)
                    resolution = {
                        "winner": None,
                        "loser": None,
                        "confidence": 0.0,
                        "sources": [],
                    }

                winner_content = resolution.get("winner")
                confidence = float(resolution.get("confidence", 0.0))

                if winner_content and confidence >= auto_resolve_confidence:
                    # Identify winner/loser rows
                    loser_row = row_b if winner_content == row_a.content else row_a
                    winner_row = row_a if loser_row is row_b else row_b

                    if not dry_run:
                        await self.delete(loser_row.id)

                    already_handled.add(loser_row.id)
                    already_handled.add(winner_row.id)
                    auto_fixed.append({
                        "memory_id": loser_row.id,
                        "content": loser_row.content,
                        "reason": (
                            f"Semantic contradiction with '{winner_row.content[:50]}…' — "
                            f"web sources support the other "
                            f"(confidence={confidence:.0%}): "
                            + ", ".join(
                                s.get("title", "")[:40]
                                for s in resolution.get("sources", [])[:2]
                            )
                        ),
                    })
                    logger.info(
                        "Auto-resolved: deleted '%s…' (confidence=%.0f%%)",
                        loser_row.content[:50],
                        confidence * 100,
                    )
                else:
                    # Inconclusive — request user decision
                    already_handled.add(row_a.id)
                    already_handled.add(row_b.id)
                    needs_review.append({
                        "category": "semantic_contradiction",
                        "contradiction_explanation": explanation,
                        "web_sources": resolution.get("sources", []),
                        "candidates": [
                            {
                                "id": row_a.id,
                                "content": row_a.content,
                                "salience": row_a.salience,
                                "access_count": row_a.access_count,
                            },
                            {
                                "id": row_b.id,
                                "content": row_b.content,
                                "salience": row_b.salience,
                                "access_count": row_b.access_count,
                            },
                        ],
                    })

        return {"auto_fixed": auto_fixed, "needs_review": needs_review}

    async def acount(self) -> int:
        """Async count from SQLite."""
        from sqlalchemy import func
        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(select(func.count()).select_from(SemanticRow))
            return result.scalar_one()
