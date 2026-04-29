"""Consolidation sleep phase — promotes episodic → semantic/autobiographical memories."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from echo.core.llm_client import llm
from echo.core.types import ConsolidationReport, MemoryType
from echo.memory.autobiographical import AutobiographicalMemoryStore
from echo.memory.episodic import EpisodicMemoryStore
from echo.memory.semantic import SemanticMemoryStore

logger = logging.getLogger(__name__)

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


class ConsolidationPhase:
    """Off-line consolidation: decay application, pattern extraction, promotion."""

    def __init__(self) -> None:
        self._episodic = EpisodicMemoryStore()
        self._semantic = SemanticMemoryStore()
        self._autobio = AutobiographicalMemoryStore()

    async def run(self, elapsed_seconds: float = 300.0, *, prune: bool = False) -> ConsolidationReport:
        """Execute one full consolidation cycle.

        Args:
            elapsed_seconds: Real wall-clock seconds since the last decay run.
                Pass 0 to skip decay (e.g. in deep/REM cycles where the
                preceding light cycle already applied decay).
            prune: When True (deep/REM cycle) permanently delete sub-threshold
                memories via :meth:`~EpisodicMemoryStore.prune_weak`.
                When False (light cycle) only mark weak memories as dormant,
                preserving them until the next deep cycle.
        """
        report = ConsolidationReport(started_at=datetime.now(timezone.utc))

        # 1. Get all episodic memories (active only — dormant excluded by default)
        memories = await self._episodic.get_all(limit=500)
        report.memories_processed = len(memories)
        logger.info("Consolidation: processing %d memories", len(memories))

        if not memories:
            report.finished_at = datetime.now(timezone.utc)
            return report

        # 2. Identify high-salience memories for promotion
        high_salience = [m for m in memories if m.salience >= 0.7]

        # 3. Promote to semantic memory
        for mem in high_salience[:20]:
            try:
                await self._semantic.store(
                    content=mem.content,
                    salience=mem.salience,
                    tags=mem.tags,
                )
                report.memories_promoted += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Semantic promotion failed: %s", exc)

        # 3b. Back-fill vectors for memories that had no embedding at store time
        re_embedded = await self._episodic.re_embed_missing()
        if re_embedded:
            logger.info("Re-embedded %d memories that were missing vectors", re_embedded)

        # 4. Very high salience → autobiographical note
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

        # 5. Extract patterns from all memories
        try:
            import json

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

        # 6. Apply decay (only when elapsed_seconds > 0 to avoid double-counting)
        if elapsed_seconds > 0:
            await self._episodic.apply_decay(elapsed_seconds)
            await self._semantic.apply_decay(elapsed_seconds)

        # 7. Restructure or prune weak memories
        if prune:
            # Deep/REM cycle: permanently delete sub-threshold memories
            pruned = await self._episodic.prune_weak()
            report.memories_pruned = pruned
        else:
            # Light cycle: mark weak memories as dormant; no deletion
            dormant = await self._episodic.mark_dormant()
            report.memories_pruned = dormant  # reported as "restructured" count

        report.finished_at = datetime.now(timezone.utc)
        logger.info(
            "Consolidation complete: promoted=%d %s=%d re_embedded=%d patterns=%d",
            report.memories_promoted,
            "pruned" if prune else "dormant",
            report.memories_pruned,
            re_embedded,
            len(report.patterns_found),
        )
        return report
