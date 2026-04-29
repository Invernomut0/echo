"""Identity Graph — NetworkX DiGraph persisted to SQLite.

Nodes = IdentityBelief objects
Edges = BeliefEdge (SUPPORTS / CONTRADICTS / REFINES / DERIVES_FROM)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

import networkx as nx
from sqlalchemy import Column, Float, String, Text, select

from echo.core.db import Base, get_session_factory
from echo.core.types import BeliefEdge, BeliefRelation, IdentityBelief

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SQLite persistence models
# ---------------------------------------------------------------------------

class BeliefRow(Base):
    __tablename__ = "identity_beliefs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    content = Column(Text, nullable=False)
    confidence = Column(Float, default=0.5)
    evidence_ids = Column(Text, default="[]")
    tags = Column(Text, default="[]")
    created_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    updated_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())


class BeliefEdgeRow(Base):
    __tablename__ = "belief_edges"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id = Column(String, nullable=False)
    target_id = Column(String, nullable=False)
    relation = Column(String, nullable=False)
    weight = Column(Float, default=1.0)
    created_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Identity Graph
# ---------------------------------------------------------------------------

class IdentityGraph:
    """In-memory NetworkX graph with SQLite persistence."""

    def __init__(self) -> None:
        self.graph: nx.DiGraph = nx.DiGraph()
        self._loaded = False

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    async def load(self) -> None:
        """Load all beliefs + edges from SQLite into the in-memory graph."""
        factory = get_session_factory()
        async with factory() as session:
            belief_rows = (await session.execute(select(BeliefRow))).scalars().all()
            edge_rows = (await session.execute(select(BeliefEdgeRow))).scalars().all()

        for row in belief_rows:
            belief = IdentityBelief(
                id=row.id,
                content=row.content,
                confidence=row.confidence,
                evidence_ids=json.loads(row.evidence_ids or "[]"),
                tags=json.loads(row.tags or "[]"),
                created_at=datetime.fromisoformat(row.created_at),
                updated_at=datetime.fromisoformat(row.updated_at),
            )
            self.graph.add_node(row.id, belief=belief)

        for row in edge_rows:
            if self.graph.has_node(row.source_id) and self.graph.has_node(row.target_id):
                self.graph.add_edge(
                    row.source_id,
                    row.target_id,
                    relation=row.relation,
                    weight=row.weight,
                    id=row.id,
                )

        self._loaded = True
        logger.info(
            "IdentityGraph loaded: %d beliefs, %d edges",
            self.graph.number_of_nodes(),
            self.graph.number_of_edges(),
        )

    # ------------------------------------------------------------------
    # Beliefs
    # ------------------------------------------------------------------

    async def add_belief(self, belief: IdentityBelief) -> IdentityBelief:
        self.graph.add_node(belief.id, belief=belief)

        factory = get_session_factory()
        async with factory() as session:
            row = BeliefRow(
                id=belief.id,
                content=belief.content,
                confidence=belief.confidence,
                evidence_ids=json.dumps(belief.evidence_ids),
                tags=json.dumps(belief.tags),
                created_at=belief.created_at.isoformat(),
                updated_at=belief.updated_at.isoformat(),
            )
            session.add(row)
            await session.commit()

        logger.debug("Added belief %s: %.60s", belief.id, belief.content)
        return belief

    async def update_belief_confidence(self, belief_id: str, delta: float) -> bool:
        if not self.graph.has_node(belief_id):
            return False
        belief: IdentityBelief = self.graph.nodes[belief_id]["belief"]
        belief.confidence = max(0.0, min(1.0, belief.confidence + delta))
        belief.updated_at = datetime.now(timezone.utc)

        factory = get_session_factory()
        async with factory() as session:
            row = (
                await session.execute(select(BeliefRow).where(BeliefRow.id == belief_id))
            ).scalar_one_or_none()
            if row:
                row.confidence = belief.confidence
                row.updated_at = belief.updated_at.isoformat()
                await session.commit()
        return True

    def get_belief(self, belief_id: str) -> IdentityBelief | None:
        node = self.graph.nodes.get(belief_id)
        return node["belief"] if node else None

    def all_beliefs(self) -> list[IdentityBelief]:
        return [data["belief"] for _, data in self.graph.nodes(data=True) if "belief" in data]

    # ------------------------------------------------------------------
    # Edges
    # ------------------------------------------------------------------

    async def add_edge(self, edge: BeliefEdge) -> BeliefEdge:
        self.graph.add_edge(
            edge.source_id,
            edge.target_id,
            relation=edge.relation.value,
            weight=edge.weight,
        )

        factory = get_session_factory()
        async with factory() as session:
            row = BeliefEdgeRow(
                id=str(uuid.uuid4()),
                source_id=edge.source_id,
                target_id=edge.target_id,
                relation=edge.relation.value,
                weight=edge.weight,
                created_at=edge.created_at.isoformat(),
            )
            session.add(row)
            await session.commit()
        return edge

    def get_neighbors(
        self,
        belief_id: str,
        relation: BeliefRelation | None = None,
    ) -> list[IdentityBelief]:
        if not self.graph.has_node(belief_id):
            return []
        neighbors = []
        for _, neighbor_id, data in self.graph.out_edges(belief_id, data=True):
            if relation is None or data.get("relation") == relation.value:
                b = self.get_belief(neighbor_id)
                if b:
                    neighbors.append(b)
        return neighbors

    # ------------------------------------------------------------------
    # Graph metrics
    # ------------------------------------------------------------------

    async def resolve_contradictions(self) -> list[str]:
        """Attenuate confidence of older beliefs involved in CONTRADICTS edges.

        For each A→B CONTRADICTS pair, reduces confidence of the *older* belief
        by −0.05 (newer evidence takes precedence).  Returns the list of belief
        IDs whose confidence was updated.  When confidence falls below 0.15 the
        belief is logged as near-obsolete (not auto-deleted).
        """
        resolved: list[str] = []
        for source_id, target_id, data in list(self.graph.edges(data=True)):
            if data.get("relation") != BeliefRelation.CONTRADICTS.value:
                continue
            b_source = self.get_belief(source_id)
            b_target = self.get_belief(target_id)
            if not b_source or not b_target:
                continue
            # Attenuate the older belief (less recent evidence)
            older = b_source if b_source.created_at < b_target.created_at else b_target
            updated = await self.update_belief_confidence(older.id, -0.05)
            if updated:
                resolved.append(older.id)
                belief = self.get_belief(older.id)
                if belief and belief.confidence < 0.15:
                    logger.info(
                        "Belief near-obsolete (conf=%.2f): %.80s",
                        belief.confidence, belief.content,
                    )
        if resolved:
            logger.info("Resolved %d contradiction(s) in identity graph", len(resolved))
        return resolved

    def coherence_score(self) -> float:
        """Returns ratio of SUPPORTS to (SUPPORTS + CONTRADICTS) edges."""
        supports = sum(
            1
            for _, _, d in self.graph.edges(data=True)
            if d.get("relation") == BeliefRelation.SUPPORTS.value
        )
        contradicts = sum(
            1
            for _, _, d in self.graph.edges(data=True)
            if d.get("relation") == BeliefRelation.CONTRADICTS.value
        )
        total = supports + contradicts
        if total == 0:
            return 1.0
        return round(supports / total, 4)

    def compute_semantic_edges(self) -> list[dict]:
        """Compute keyword-based semantic edges for visualization (not persisted).

        Uses Jaccard similarity on content tokens to infer relationships between
        beliefs without requiring embeddings.
        """
        import re

        STOPWORDS = frozenset({
            "the", "user", "a", "an", "is", "are", "in", "and", "or", "to", "of",
            "their", "with", "by", "as", "for", "has", "been", "likely", "that",
            "this", "they", "will", "can", "be", "it", "at", "on", "from", "also",
            "very", "well", "more", "most", "both", "when", "where", "which",
            "who", "its", "have", "had", "does", "did", "was", "were",
        })

        beliefs = self.all_beliefs()
        if len(beliefs) < 2:
            return []

        def tokenize(text: str) -> frozenset:
            words = re.findall(r"\b[a-z]+\b", text.lower())
            return frozenset(w for w in words if len(w) > 3 and w not in STOPWORDS)

        def jaccard(a: frozenset, b: frozenset) -> float:
            u = a | b
            return len(a & b) / len(u) if u else 0.0

        NEGATION = ("not ", "never", "doesn't", "don't", "without", "avoid", "dislike")

        token_pairs = [(b, tokenize(b.content)) for b in beliefs]
        edges: list[dict] = []

        for i in range(len(token_pairs)):
            b1, t1 = token_pairs[i]
            for j in range(i + 1, len(token_pairs)):
                b2, t2 = token_pairs[j]
                sim = jaccard(t1, t2)

                if sim < 0.18:
                    continue

                # Contradiction: one belief negates terms the other affirms
                neg1 = any(p in b1.content.lower() for p in NEGATION)
                neg2 = any(p in b2.content.lower() for p in NEGATION)

                if neg1 != neg2 and sim > 0.28:
                    relation = "CONTRADICTS"
                elif sim > 0.42:
                    relation = "REFINES"
                elif sim > 0.28:
                    relation = "SUPPORTS"
                else:
                    relation = "DERIVES_FROM"

                # Direction: higher-confidence belief supports lower-confidence one
                if b1.confidence >= b2.confidence:
                    src, tgt = b1.id, b2.id
                else:
                    src, tgt = b2.id, b1.id

                edges.append({
                    "source": src,
                    "target": tgt,
                    "relation": relation,
                    "weight": round(sim, 3),
                })

        return edges

    def to_dict(self) -> dict:
        """Serialise graph for API/frontend consumption."""
        nodes = [
            {
                "id": nid,
                "content": data["belief"].content,
                "confidence": data["belief"].confidence,
                "tags": data["belief"].tags,
            }
            for nid, data in self.graph.nodes(data=True)
            if "belief" in data
        ]
        edges = [
            {
                "source": s,
                "target": t,
                "relation": d.get("relation"),
                "weight": d.get("weight", 1.0),
            }
            for s, t, d in self.graph.edges(data=True)
        ]
        # If no persisted edges exist, compute semantic edges dynamically
        if not edges:
            edges = self.compute_semantic_edges()
        return {"nodes": nodes, "edges": edges}
