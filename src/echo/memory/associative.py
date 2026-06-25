"""Deep Associative Memory — lateral connections between memories.

Enhances memory retrieval beyond simple vector similarity with:

1. **Random Walk Retrieval**: follow causal links to discover contextually
   related memories that vector search might miss
2. **Cross-pollination**: during deep-sleep, connect unrelated memories via LLM
   to discover unexpected patterns and analogies
3. **Temporal Clustering**: group memories by time period and find recurring
   themes the user hasn't explicitly stated

Integration:
    - Random walk: called from pipeline alongside normal retrieval
    - Cross-pollination: called during deep-sleep consolidation
    - Temporal clustering: called during light consolidation
"""

from __future__ import annotations
from echo.core.config import settings

import json
import logging
import random
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Column, Float, String, Text, select

from echo.core.db import Base, get_session_factory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_MAX_WALK_DEPTH = 3           # max hops in random walk
_WALK_BRANCH_FACTOR = 2       # max links to follow per hop
_CROSS_POLLINATION_PAIRS = 3  # pairs to evaluate per cycle
_TEMPORAL_WINDOW_DAYS = 7     # clustering window


# ---------------------------------------------------------------------------
# SQLAlchemy model — stores discovered associations
# ---------------------------------------------------------------------------

class AssociationRow(Base):
    __tablename__ = "memory_associations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    memory_a_id = Column(String, nullable=False)
    memory_b_id = Column(String, nullable=False)
    association_type = Column(String, default="cross_pollination")  # cross_pollination, temporal, random_walk
    description = Column(Text, default="")
    strength = Column(Float, default=0.5)
    created_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class AssociativeMemory:
    """Lateral memory connections beyond vector similarity."""

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Random Walk Retrieval
    # ------------------------------------------------------------------

    async def random_walk_retrieve(
        self,
        seed_memory_ids: list[str],
        max_results: int = 2,
    ) -> list[Any]:
        """Follow causal links from seed memories to discover related ones.

        Performs a random walk up to _MAX_WALK_DEPTH hops along the
        linked_ids edges. Returns memories found that aren't in the seed set.

        Args:
            seed_memory_ids: IDs of already-retrieved memories to walk from
            max_results: maximum additional memories to return
        """
        from echo.memory.episodic import EpisodicMemoryStore  # noqa: PLC0415

        store = EpisodicMemoryStore()
        visited: set[str] = set(seed_memory_ids)
        discovered: list[Any] = []

        # Start from random seeds
        walk_seeds = random.sample(
            seed_memory_ids,
            min(2, len(seed_memory_ids))
        ) if seed_memory_ids else []

        for seed_id in walk_seeds:
            current_id = seed_id
            for _depth in range(_MAX_WALK_DEPTH):
                # Get the memory and its links
                mem = await store.get_by_id(current_id)
                if not mem or not mem.linked_ids:
                    break

                # Choose a random link to follow
                candidates = [lid for lid in mem.linked_ids if lid not in visited]
                if not candidates:
                    break

                next_id = random.choice(candidates[:_WALK_BRANCH_FACTOR])
                visited.add(next_id)

                # Retrieve the linked memory
                linked_mem = await store.get_by_id(next_id)
                if linked_mem and linked_mem.current_strength > 0.1:
                    discovered.append(linked_mem)

                current_id = next_id

                if len(discovered) >= max_results:
                    break

            if len(discovered) >= max_results:
                break

        logger.debug(
            "Random walk from %d seeds: discovered %d additional memories",
            len(walk_seeds),
            len(discovered),
        )
        return discovered[:max_results]

    # ------------------------------------------------------------------
    # Cross-pollination (deep-sleep)
    # ------------------------------------------------------------------

    async def cross_pollinate(self) -> list[dict[str, Any]]:
        """Find unexpected connections between unrelated memories.

        Selects pairs of memories that are:
        - Not already linked (no causal link)
        - From different time periods
        - Different interaction types/topics

        Uses LLM to see if there's a meaningful connection.
        Returns list of discovered associations.
        """
        from echo.core.llm_client import llm  # noqa: PLC0415
        from echo.memory.episodic import EpisodicMemoryStore  # noqa: PLC0415

        store = EpisodicMemoryStore()
        all_mems = await store.get_all(limit=50, include_dormant=False)

        if len(all_mems) < 10:
            return []

        associations: list[dict[str, Any]] = []

        # Select random pairs that are distant in time
        for _ in range(_CROSS_POLLINATION_PAIRS):
            # Pick two memories at least 5 apart in the list (different time periods)
            idx_a = random.randint(0, len(all_mems) // 3)
            idx_b = random.randint(len(all_mems) * 2 // 3, len(all_mems) - 1)
            mem_a = all_mems[idx_a]
            mem_b = all_mems[idx_b]

            # Skip if already linked
            if mem_b.id in mem_a.linked_ids or mem_a.id in mem_b.linked_ids:
                continue

            prompt = f"""\
You are looking for unexpected intellectual connections between two memories.

Memory A: {mem_a.content[:300]}

Memory B: {mem_b.content[:300]}

Is there a meaningful, non-obvious connection between these two memories?
Not surface-level similarity, but a deeper conceptual link, analogy, or pattern.

Respond with JSON:
{{"connected": true/false, "connection": "...", "strength": 0.7}}

If no meaningful connection exists, set connected=false."""

            try:
                raw = await llm.chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.5,
                    max_tokens=settings.llm_max_tokens_associative_cross,
                )
                start = raw.find("{")
                end = raw.rfind("}") + 1
                data = json.loads(raw[start:end])

                if data.get("connected") and data.get("connection"):
                    assoc = {
                        "memory_a_id": mem_a.id,
                        "memory_b_id": mem_b.id,
                        "description": data["connection"],
                        "strength": float(data.get("strength", 0.5)),
                    }
                    associations.append(assoc)
                    await self._persist_association(assoc)

                    # Add causal link so future walks can traverse it
                    await store.add_causal_link(mem_a.id, mem_b.id)

                    logger.info(
                        "Cross-pollination: '%s' ↔ '%s': %s",
                        mem_a.content[:40],
                        mem_b.content[:40],
                        data["connection"][:80],
                    )

            except Exception as exc:  # noqa: BLE001
                logger.debug("Cross-pollination pair failed: %s", exc)

        if associations:
            # Store a synthesis of found connections as semantic memory
            try:
                from echo.memory.semantic import SemanticMemoryStore  # noqa: PLC0415
                semantic = SemanticMemoryStore()
                connections_text = "\n".join(
                    f"• {a['description']}" for a in associations
                )
                await semantic.store(
                    content=(
                        f"[Cross-pollination insights]\n"
                        f"Found {len(associations)} unexpected connections:\n"
                        f"{connections_text}"
                    ),
                    tags=["cross_pollination", "associative", "deep_sleep"],
                    salience=0.7,
                )
            except Exception:  # noqa: BLE001
                pass

        logger.info("Cross-pollination: %d associations found", len(associations))
        return associations

    # ------------------------------------------------------------------
    # Temporal Clustering
    # ------------------------------------------------------------------

    async def temporal_clustering(self) -> list[dict[str, Any]]:
        """Group recent memories by time period and identify recurring themes.

        Looks at the last N days of memories, clusters them by day, and asks
        the LLM to identify patterns/themes that span multiple days.
        """
        from echo.core.llm_client import llm  # noqa: PLC0415
        from echo.memory.episodic import EpisodicMemoryStore  # noqa: PLC0415

        store = EpisodicMemoryStore()
        all_mems = await store.get_all(limit=100, include_dormant=False)

        if len(all_mems) < 10:
            return []

        # Group by day
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=_TEMPORAL_WINDOW_DAYS)
        daily_groups: dict[str, list[str]] = defaultdict(list)

        for mem in all_mems:
            created = mem.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created > cutoff:
                day_key = created.strftime("%Y-%m-%d")
                daily_groups[day_key].append(mem.content[:150])

        if len(daily_groups) < 2:
            return []

        # Build context for LLM
        days_text = ""
        for day, snippets in sorted(daily_groups.items())[-5:]:
            days_text += f"\n[{day}] ({len(snippets)} memories):\n"
            for s in snippets[:3]:
                days_text += f"  - {s}\n"

        prompt = f"""\
Analyse these memory clusters grouped by day and identify 1-3 recurring themes
or patterns that span multiple days. These should be non-obvious — not just
"the user asked questions" but deeper patterns about interests, concerns, or
evolving topics.

{days_text}

Respond with JSON:
{{"themes": [{{"theme": "...", "days_present": 3, "evidence": "..."}}]}}

If no clear cross-day patterns exist, return {{"themes": []}}"""

        try:
            raw = await llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=settings.llm_max_tokens_associative_cluster,
            )
            start = raw.find("{")
            end = raw.rfind("}") + 1
            data = json.loads(raw[start:end])

            themes = data.get("themes", [])
            if themes:
                # Store themes as semantic memories
                from echo.memory.semantic import SemanticMemoryStore  # noqa: PLC0415
                semantic = SemanticMemoryStore()
                for theme in themes[:3]:
                    if theme.get("theme"):
                        await semantic.store(
                            content=(
                                f"[Temporal pattern] {theme['theme']}: "
                                f"{theme.get('evidence', '')[:200]}"
                            ),
                            tags=["temporal_pattern", "associative"],
                            salience=0.65,
                        )

                logger.info(
                    "Temporal clustering: %d themes found across %d days",
                    len(themes),
                    len(daily_groups),
                )

            return themes

        except Exception as exc:  # noqa: BLE001
            logger.warning("Temporal clustering failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _persist_association(self, assoc: dict[str, Any]) -> None:
        """Store a discovered association in SQLite."""
        factory = get_session_factory()
        async with factory() as session:
            row = AssociationRow(
                id=str(uuid.uuid4()),
                memory_a_id=assoc["memory_a_id"],
                memory_b_id=assoc["memory_b_id"],
                association_type="cross_pollination",
                description=assoc.get("description", ""),
                strength=assoc.get("strength", 0.5),
            )
            session.add(row)
            await session.commit()

    async def get_associations(self, memory_id: str) -> list[dict[str, Any]]:
        """Get all associations for a given memory."""
        factory = get_session_factory()
        async with factory() as session:
            stmt = select(AssociationRow).where(
                (AssociationRow.memory_a_id == memory_id)
                | (AssociationRow.memory_b_id == memory_id)
            )
            rows = (await session.execute(stmt)).scalars().all()
        return [
            {
                "id": r.id,
                "partner_id": r.memory_b_id if r.memory_a_id == memory_id else r.memory_a_id,
                "type": r.association_type,
                "description": r.description,
                "strength": r.strength,
            }
            for r in rows
        ]


# Module-level singleton
associative_memory = AssociativeMemory()
