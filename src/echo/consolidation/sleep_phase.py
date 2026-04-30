"""Consolidation sleep phase — synaptic pruning and memory consolidation.

Consolidation pipeline
----------------------
1. Load all active episodic memories.
2. **Synaptic deduplication** — find near-duplicate episodic memories via
   vector cosine similarity; keep the winner (highest salience × access_count),
   mark losers dormant (light) or delete them (deep/REM).
3. Promote high-salience episodic → semantic memories.
4. **Semantic dedup** — find near-duplicate semantic memories; keep the richer
   version (highest salience), delete redundant copies.
5. Back-fill missing embeddings.
6. Very-high salience memories → autobiographical note (self-reflection).
7. Pattern extraction from recent memories.
8. Apply time-based decay.
9. Mark dormant / prune weak memories.

Biological analogy
------------------
Steps 2 and 4 mirror **synaptic pruning** in the developing brain: redundant
connections (duplicate memories) are selectively eliminated so that the
surviving synapses (unique memories) are strengthened.  A memory that is
*similar but not identical* to an existing one is not purely redundant — it
may carry subtle contextual nuance — so we use a conservative similarity
threshold (0.92) for automatic pruning.  Pairs that are similar but not over
the threshold are left intact ("potentially valuable tomorrow, like gene reuse
in evolution").
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from echo.core.llm_client import llm
from echo.core.types import ConsolidationReport, MemoryEntry, MemoryType
from echo.memory.autobiographical import AutobiographicalMemoryStore
from echo.memory.episodic import EpisodicMemoryStore
from echo.memory.semantic import SemanticMemoryStore

logger = logging.getLogger(__name__)

# ── Similarity thresholds ──────────────────────────────────────────────────────
# Cosine similarity (0–1, 1 = identical).
# Pairs above HARD_DEDUP_SIM are true duplicates → always prune the weaker.
# Pairs between SOFT_DEDUP_SIM and HARD_DEDUP_SIM are near-duplicates →
#   pruned only in deep/REM cycles.
HARD_DEDUP_SIM: float = 0.97
SOFT_DEDUP_SIM: float = 0.92

# Max pairs to evaluate per cycle (cost guard)
_MAX_PAIRS: int = 300


# ── Prompts ───────────────────────────────────────────────────────────────────

_PATTERN_PROMPT = """\
You are a memory consolidation system. Analyse the following recent memories
and extract 2-5 recurring themes or important patterns.

Memories:
{memories}

Respond ONLY with a JSON array of strings (themes/patterns), e.g.:
["theme1", "theme2"]"""

_AUTOBIO_PROMPT = """\
Based on this high-salience memory, write a brief (1 sentence) autobiographical note
that ECHO should retain about itself:

Memory: {content}

Autobiographical note:"""


# ── Dedup helpers ─────────────────────────────────────────────────────────────

def _cosine(a: list[float], b: list[float]) -> float:
    """Numpy-free cosine similarity between two equal-length vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _memory_score(mem: MemoryEntry) -> float:
    """Winner selection score: salience × sqrt(access_count + 1)."""
    ac = getattr(mem, "access_count", 0) or 0
    return mem.salience * ((ac + 1) ** 0.5)


async def _embed_memories(memories: list[MemoryEntry]) -> dict[str, list[float]]:
    """Return {memory_id: vector} for all memories. Batches 32 at a time."""
    vectors: dict[str, list[float]] = {}
    batch_size = 32
    for i in range(0, len(memories), batch_size):
        batch = memories[i : i + batch_size]
        texts = [m.content[:512] for m in batch]
        try:
            vecs = await llm.embed(texts)
            if vecs and len(vecs) == len(batch):
                for mem, vec in zip(batch, vecs):
                    if vec:
                        vectors[mem.id] = vec
        except Exception as exc:  # noqa: BLE001
            logger.warning("[Dedup] embed batch failed: %s", exc)
    return vectors


def _find_duplicate_pairs(
    memories: list[MemoryEntry],
    vectors: dict[str, list[float]],
    threshold: float,
) -> list[tuple[str, str, float]]:
    """Return (winner_id, loser_id, similarity) for pairs above threshold.

    Winner = higher _memory_score(). Capped at _MAX_PAIRS evaluated.
    """
    ids = [m.id for m in memories if m.id in vectors]
    score = {m.id: _memory_score(m) for m in memories}
    pairs: list[tuple[str, str, float]] = []
    evaluated = 0
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            if evaluated >= _MAX_PAIRS:
                break
            evaluated += 1
            sim = _cosine(vectors[ids[i]], vectors[ids[j]])
            if sim >= threshold:
                a, b = ids[i], ids[j]
                winner, loser = (a, b) if score[a] >= score[b] else (b, a)
                pairs.append((winner, loser, sim))
        if evaluated >= _MAX_PAIRS:
            break
    return pairs


# ── Main consolidation phase ──────────────────────────────────────────────────

class ConsolidationPhase:
    """Off-line consolidation: synaptic pruning, promotion, pattern extraction."""

    def __init__(self) -> None:
        self._episodic = EpisodicMemoryStore()
        self._semantic = SemanticMemoryStore()
        self._autobio = AutobiographicalMemoryStore()

    async def _dedup_episodic(
        self, memories: list[MemoryEntry], *, hard_prune: bool
    ) -> tuple[int, int]:
        """Synaptic pruning for episodic memories.

        Light cycle: silence only exact duplicates (sim ≥ HARD_DEDUP_SIM).
        Deep/REM: also remove strong near-duplicates (sim ≥ SOFT_DEDUP_SIM).

        Returns (pairs_found, memories_pruned).
        """
        if len(memories) < 2:
            return 0, 0

        vectors = await _embed_memories(memories)
        threshold = SOFT_DEDUP_SIM if hard_prune else HARD_DEDUP_SIM
        pairs = _find_duplicate_pairs(memories, vectors, threshold)
        if not pairs:
            return 0, 0

        loser_ids = list({loser for _, loser, _ in pairs})
        logger.info(
            "[Synaptic pruning·episodic] %d duplicate pair(s) (sim≥%.2f) — "
            "%s %d memor%s",
            len(pairs), threshold,
            "deleting" if hard_prune else "silencing",
            len(loser_ids),
            "ies" if len(loser_ids) != 1 else "y",
        )

        if hard_prune:
            pruned = await self._episodic.delete_by_ids(loser_ids)
        else:
            pruned = await self._episodic.mark_dormant_by_ids(loser_ids)

        return len(pairs), pruned

    async def _dedup_semantic(self, *, hard_prune: bool) -> tuple[int, int]:
        """Synaptic pruning for semantic memories.

        Always uses HARD threshold — semantic memories are already abstract;
        near-exact duplicates carry no contextual value.

        Returns (pairs_found, memories_deleted).
        """
        all_rows = await self._semantic._get_all_rows()
        if len(all_rows) < 2:
            return 0, 0

        proxies = [
            MemoryEntry(
                id=r.id,
                content=r.content,
                memory_type=MemoryType.SEMANTIC,
                salience=r.salience,
                decay_lambda=r.decay_lambda,
                tags=json.loads(r.tags or "[]"),
                embedding_id=r.embedding_id,
                access_count=r.access_count,
            )
            for r in all_rows
        ]

        vectors = await _embed_memories(proxies)
        threshold = SOFT_DEDUP_SIM if hard_prune else HARD_DEDUP_SIM
        pairs = _find_duplicate_pairs(proxies, vectors, threshold)
        if not pairs:
            return 0, 0

        loser_ids = list({loser for _, loser, _ in pairs})
        logger.info(
            "[Synaptic pruning·semantic] %d conceptual duplicate(s) (sim≥%.2f) — "
            "deleting %d",
            len(pairs), threshold, len(loser_ids),
        )

        deleted = 0
        for lid in loser_ids:
            if await self._semantic.delete(lid):
                deleted += 1

        return len(pairs), deleted

    async def run(self, elapsed_seconds: float = 300.0, *, prune: bool = False) -> ConsolidationReport:
        """Execute one full consolidation cycle.

        Args:
            elapsed_seconds: Real wall-clock seconds since the last decay run.
                Pass 0 to skip decay (e.g. in deep/REM cycles where the
                preceding light cycle already applied decay).
            prune: When True (deep/REM cycle) permanently delete sub-threshold
                and duplicate memories. When False (light cycle) only silence
                exact duplicates and mark weak memories as dormant.
        """
        report = ConsolidationReport(started_at=datetime.now(timezone.utc))

        # 1. Load all active episodic memories
        memories = await self._episodic.get_all(limit=500)
        report.memories_processed = len(memories)
        logger.info("Consolidation: processing %d episodic memories", len(memories))

        if not memories:
            report.finished_at = datetime.now(timezone.utc)
            return report

        # 2. Synaptic pruning — episodic deduplication
        ep_pairs, ep_pruned = await self._dedup_episodic(memories, hard_prune=prune)

        # Refresh list after dedup (dormant ones excluded by default)
        if ep_pruned:
            memories = await self._episodic.get_all(limit=500)

        # 3. Promote high-salience episodic → semantic
        high_salience = [m for m in memories if m.salience >= 0.7]
        promoted = 0
        for mem in high_salience[:20]:
            try:
                await self._semantic.store(
                    content=mem.content,
                    salience=mem.salience,
                    tags=mem.tags,
                )
                promoted += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Semantic promotion failed: %s", exc)
        report.memories_promoted = promoted

        # 4. Semantic deduplication (after promotion so new entries are included)
        sem_pairs, sem_pruned = await self._dedup_semantic(hard_prune=prune)

        # 5. Back-fill vectors for memories missing embeddings
        re_embedded = await self._episodic.re_embed_missing()
        if re_embedded:
            logger.info("Re-embedded %d memories that were missing vectors", re_embedded)
        report.re_embedded = re_embedded

        # 6. Very high salience → autobiographical note
        very_high = [m for m in high_salience if m.salience >= 0.85 and m.self_relevance >= 0.7]
        for mem in very_high[:5]:
            try:
                raw = await llm.chat(
                    [{"role": "user", "content": _AUTOBIO_PROMPT.format(content=mem.content[:300])}],
                    temperature=0.4,
                    max_tokens=80,
                )
                if raw.strip():
                    await self._autobio.store(raw.strip(), salience=0.9)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Autobio promotion failed: %s", exc)

        # 7. Pattern extraction
        try:
            sample = "\n".join(f"- {m.content[:150]}" for m in memories[:30])
            raw_patterns = await llm.chat(
                [{"role": "user", "content": _PATTERN_PROMPT.format(memories=sample)}],
                temperature=0.3,
                max_tokens=256,
            )
            start = raw_patterns.find("[")
            end = raw_patterns.rfind("]") + 1
            if start != -1 and end > 0:
                patterns = json.loads(raw_patterns[start:end])
                report.patterns_found = [str(p) for p in patterns]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Pattern extraction failed: %s", exc)

        # 8. Apply decay
        if elapsed_seconds > 0:
            await self._episodic.apply_decay(elapsed_seconds)
            await self._semantic.apply_decay(elapsed_seconds)

        # 9. Restructure or prune weak memories
        if prune:
            report.memories_pruned = await self._episodic.prune_weak()
        else:
            report.memories_pruned = await self._episodic.mark_dormant()

        report.episodic_deduped = ep_pruned
        report.semantic_deduped = sem_pruned
        total_deduped = ep_pruned + sem_pruned
        report.finished_at = datetime.now(timezone.utc)
        logger.info(
            "Consolidation complete: promoted=%d %s=%d re_embedded=%d "
            "deduped=%d(ep=%d sem=%d) patterns=%d",
            report.memories_promoted,
            "pruned" if prune else "dormant",
            report.memories_pruned,
            re_embedded,
            total_deduped, ep_pruned, sem_pruned,
            len(report.patterns_found),
        )
        return report
