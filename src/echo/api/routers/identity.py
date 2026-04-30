"""Identity router — /api/identity (graph for D3.js)."""

from __future__ import annotations

import re
import logging

from fastapi import APIRouter

from echo.api.schemas import GraphResponse
from echo.core.pipeline import pipeline
from echo.memory.semantic import SemanticMemoryStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/identity", tags=["identity"])

# ---------------------------------------------------------------------------
# Text helpers (for semantic ↔ belief edge inference)
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset({
    "the", "user", "a", "an", "is", "are", "in", "and", "or", "to", "of",
    "their", "with", "by", "as", "for", "has", "been", "likely", "that",
    "this", "they", "will", "can", "be", "it", "at", "on", "from", "also",
    "very", "well", "more", "most", "both", "when", "where", "which",
    "who", "its", "have", "had", "does", "did", "was", "were",
    # Italian stopwords
    "che", "con", "una", "uno", "gli", "del", "della", "delle", "degli",
    "nel", "nella", "nelle", "negli", "sui", "sulla", "sulle", "sugli",
    "per", "non", "tra", "fra", "come", "cosa", "quando", "dove", "sono",
    "hai", "lui", "lei", "loro", "noi", "voi", "era", "fatto", "ecco",
    "anche", "solo", "poi", "dopo", "prima", "sempre", "mai", "già",
    "echo", "utente",
})


def _tokenize(text: str) -> frozenset[str]:
    # Unicode word chars — handles Italian accented letters (è, à, ò, ì, ù)
    words = re.findall(r"\b[\w']+\b", text.lower(), re.UNICODE)
    return frozenset(w for w in words if len(w) > 3 and w not in _STOPWORDS and not w.isdigit())


def _jaccard(a: frozenset, b: frozenset) -> float:
    u = a | b
    return len(a & b) / len(u) if u else 0.0


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.get("/graph", response_model=GraphResponse)
async def get_graph() -> GraphResponse:
    """Return combined identity + semantic memory graph for 3D visualisation.

    Belief nodes are type='belief' (cyan); semantic memory nodes are
    type='semantic' (violet).  Edges:
    - Persisted belief–belief edges (SUPPORTS, CONTRADICTS, REFINES, DERIVES_FROM)
    - INFORMS  : best-matching belief for each semantic node (text similarity ≥ 0.12)
    - SEMANTIC_RELATED : semantic nodes sharing a source: tag or text sim ≥ 0.22
    """
    # ── 1. Identity belief graph ──────────────────────────────────────────
    belief_data = pipeline.identity_graph.to_dict()
    nodes: list[dict] = []
    for n in belief_data["nodes"]:
        nodes.append({**n, "node_type": "belief"})
    edges: list[dict] = list(belief_data["edges"])

    # ── 2. Semantic memory nodes — deduplicated by content ──────────────
    try:
        store = SemanticMemoryStore()
        all_entries = await store.get_all(limit=400)  # wider pool for dedup

        # Deduplicate: keep highest-scoring copy of each unique content
        seen: dict[str, object] = {}
        for e in all_entries:
            key = e.content.strip().lower()
            score = (e.salience or 0.5) * (e.current_strength or 1.0)
            existing = seen.get(key)
            if existing is None:
                seen[key] = e
            else:
                existing_score = (existing.salience or 0.5) * (existing.current_strength or 1.0)  # type: ignore[union-attr]
                if score > existing_score:
                    seen[key] = e

        sem_entries = sorted(
            seen.values(),
            key=lambda e: (e.salience or 0.5) * (e.current_strength or 1.0),  # type: ignore[union-attr]
            reverse=True,
        )[:60]  # up to 60 unique memories
    except Exception:
        logger.exception("Could not load semantic memories for graph")
        sem_entries = []

    sem_nodes: list[dict] = []
    for e in sem_entries:
        sem_nodes.append({
            "id": f"sem:{e.id}",
            "content": e.content[:150],
            "confidence": round((e.salience or 0.5) * (e.current_strength or 1.0), 3),
            "tags": e.tags or [],
            "node_type": "semantic",
            "source_agent": e.source_agent or "",
        })
    nodes.extend(sem_nodes)

    # Pre-compute token sets
    belief_tokens: dict[str, frozenset] = {
        n["id"]: _tokenize(n["content"])
        for n in belief_data["nodes"]
    }
    sem_tokens: dict[str, frozenset] = {
        sn["id"]: _tokenize(sn["content"])
        for sn in sem_nodes
    }

    # ── 3. INFORMS edges: each semantic node → best matching belief ───────
    for sn in sem_nodes:
        st = sem_tokens[sn["id"]]
        if not st:
            continue
        best_bid: str | None = None
        best_sim = 0.0
        for bid, bt in belief_tokens.items():
            sim = _jaccard(st, bt)
            if sim > best_sim:
                best_sim = sim
                best_bid = bid
        if best_bid and best_sim >= 0.12:
            edges.append({
                "source": sn["id"],
                "target": best_bid,
                "relation": "INFORMS",
                "weight": round(best_sim, 3),
            })

    # ── 4. SEMANTIC_RELATED edges: semantic ↔ semantic ───────────────────
    for i in range(len(sem_nodes)):
        for j in range(i + 1, len(sem_nodes)):
            a, b = sem_nodes[i], sem_nodes[j]
            # Shared source: tag wins immediately
            a_src = {t for t in a["tags"] if t.startswith("source:")}
            b_src = {t for t in b["tags"] if t.startswith("source:")}
            if a_src & b_src:
                edges.append({
                    "source": a["id"],
                    "target": b["id"],
                    "relation": "SEMANTIC_RELATED",
                    "weight": 0.5,
                })
                continue
            # Text similarity fallback
            sim = _jaccard(sem_tokens[a["id"]], sem_tokens[b["id"]])
            if sim >= 0.22:
                edges.append({
                    "source": a["id"],
                    "target": b["id"],
                    "relation": "SEMANTIC_RELATED",
                    "weight": round(sim, 3),
                })

    return GraphResponse(
        nodes=nodes,
        edges=edges,
        coherence_score=pipeline.identity_graph.coherence_score(),
    )

