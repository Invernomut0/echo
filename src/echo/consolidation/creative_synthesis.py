"""Creative synthesis during dream phase (v0.2.13).

Identifies pairs of *distant* episodic memories (low cosine similarity) that
share high salience, then asks the LLM to derive a non-obvious connecting
insight — a cognitive "bridge".

The insights are stored as new semantic memories with tags ["synthetic","dream"]
so they become part of ECHO's permanent knowledge base.

If ChromaDB embeddings are unavailable the phase falls back to random pairing
and skips the similarity filter.
"""

from __future__ import annotations

import asyncio
import logging
import math

from echo.core.llm_client import llm
from echo.core.types import MemoryEntry
from echo.memory.episodic import EpisodicMemoryStore
from echo.memory.semantic import SemanticMemoryStore

logger = logging.getLogger(__name__)

# ── Hyper-parameters ──────────────────────────────────────────────────────────
MAX_PAIRS: int = 4          # max number of bridge pairs to synthesise
BRIDGE_COS_MAX: float = 0.45  # pairs with cosine sim < this are "distant"
MIN_SALIENCE: float = 0.50   # both memories must exceed this threshold
SYNTHESIS_SALIENCE: float = 0.65  # salience assigned to stored insights
_LLM_TEMP: float = 0.75
_LLM_MAX_TOKENS: int = 130
# ─────────────────────────────────────────────────────────────────────────────

_BRIDGE_PROMPT = """\
Memory A: {a}
Memory B: {b}

These two experiences appear unrelated. Derive ONE concrete, non-obvious insight \
that connects them at a deeper level.
Start with "I notice that" — two sentences maximum.\
"""


def _cosine(u: list[float], v: list[float]) -> float:
    """Fast cosine similarity between two equal-length float vectors."""
    dot = sum(a * b for a, b in zip(u, v))
    mag_u = math.sqrt(sum(a * a for a in u))
    mag_v = math.sqrt(sum(b * b for b in v))
    if mag_u == 0 or mag_v == 0:
        return 0.0
    return dot / (mag_u * mag_v)


class CreativeSynthesis:
    """Generates synthetic insights by bridging distant episodic memories."""

    def __init__(self) -> None:
        self._episodic = EpisodicMemoryStore()
        self._semantic = SemanticMemoryStore()

    async def run(self, seed_memories: list[MemoryEntry]) -> list[str]:
        """Synthesise insights from distant memory pairs.

        Parameters
        ----------
        seed_memories:
            Dream seed memories (typically the top-15 salient ones).

        Returns
        -------
        list[str]
            Generated insight texts (also persisted as semantic memories).
        """
        if len(seed_memories) < 2:
            return []

        pairs = await self._find_bridge_pairs(seed_memories)
        if not pairs:
            logger.debug("CreativeSynthesis: no bridge pairs found in %d seeds", len(seed_memories))
            return []

        # Run all LLM calls in parallel
        tasks = [self._synthesise_pair(a, b) for a, b in pairs]
        results: list[str | None] = await asyncio.gather(*tasks, return_exceptions=False)

        insights: list[str] = []
        for insight in results:
            if insight:
                insights.append(insight)
                try:
                    await self._semantic.store(
                        content=insight,
                        tags=["synthetic", "dream"],
                        salience=SYNTHESIS_SALIENCE,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("CreativeSynthesis: failed to store insight: %s", exc)

        logger.info("CreativeSynthesis: %d/%d insights generated", len(insights), len(pairs))
        return insights

    # ----------------------------------------------------------------- private

    async def _find_bridge_pairs(
        self, memories: list[MemoryEntry]
    ) -> list[tuple[MemoryEntry, MemoryEntry]]:
        """Return up to MAX_PAIRS distant, high-salience memory pairs."""
        # Filter for high-salience memories that have embeddings
        candidates = [
            m for m in memories
            if m.salience >= MIN_SALIENCE and m.embedding_id
        ]

        if len(candidates) < 2:
            # Fallback: use all seeds regardless of salience or embeddings
            candidates = memories
            if len(candidates) < 2:
                return []
            # Random pairing (no cosine filter)
            pairs: list[tuple[MemoryEntry, MemoryEntry]] = []
            import random
            shuffled = random.sample(candidates, min(len(candidates), MAX_PAIRS * 2))
            for i in range(0, len(shuffled) - 1, 2):
                pairs.append((shuffled[i], shuffled[i + 1]))
                if len(pairs) >= MAX_PAIRS:
                    break
            return pairs

        # Retrieve embeddings from ChromaDB
        ids = [m.embedding_id for m in candidates if m.embedding_id]
        embeddings_map: dict[str, list[float]] = {}
        try:
            chroma_result = self._episodic._collection.get(
                ids=ids, include=["embeddings"]
            )
            if chroma_result and chroma_result.get("ids"):
                for cid, emb in zip(chroma_result["ids"], chroma_result["embeddings"]):
                    embeddings_map[cid] = emb
        except Exception as exc:  # noqa: BLE001
            logger.warning("CreativeSynthesis: cannot read embeddings: %s", exc)

        if not embeddings_map:
            # No embeddings — fallback to sorted random pairs
            import random
            salienced = sorted(candidates, key=lambda m: m.salience, reverse=True)
            pairs = []
            for i in range(0, len(salienced) - 1, 2):
                pairs.append((salienced[i], salienced[i + 1]))
                if len(pairs) >= MAX_PAIRS:
                    break
            return pairs

        # Find distant pairs
        scored: list[tuple[float, MemoryEntry, MemoryEntry]] = []
        for i in range(len(candidates)):
            for j in range(i + 1, len(candidates)):
                a, b = candidates[i], candidates[j]
                emb_a = embeddings_map.get(a.embedding_id or "")
                emb_b = embeddings_map.get(b.embedding_id or "")
                if emb_a is None or emb_b is None:
                    continue
                sim = _cosine(emb_a, emb_b)
                if sim < BRIDGE_COS_MAX:
                    pair_salience = a.salience + b.salience
                    scored.append((pair_salience, a, b))

        # Sort by combined salience (best bridge candidates first)
        scored.sort(key=lambda x: x[0], reverse=True)
        return [(a, b) for _, a, b in scored[:MAX_PAIRS]]

    async def _synthesise_pair(
        self, a: MemoryEntry, b: MemoryEntry
    ) -> str | None:
        """Ask the LLM to derive one insight connecting memories a and b."""
        prompt = _BRIDGE_PROMPT.format(
            a=a.content[:250],
            b=b.content[:250],
        )
        try:
            raw = await llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=_LLM_TEMP,
                max_tokens=_LLM_MAX_TOKENS,
            )
            insight = (raw or "").strip()
            return insight if insight else None
        except Exception as exc:  # noqa: BLE001
            logger.warning("CreativeSynthesis: LLM call failed: %s", exc)
            return None
