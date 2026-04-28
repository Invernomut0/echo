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

    async def run(self) -> ConsolidationReport:
        """Execute one full consolidation cycle."""
        report = ConsolidationReport(started_at=datetime.now(timezone.utc))

        # 1. Get all episodic memories
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

        # 6. Apply decay
        await self._episodic.apply_decay(3600.0)
        pruned = await self._episodic.prune_weak()
        report.memories_pruned = pruned

        report.finished_at = datetime.now(timezone.utc)
        logger.info(
            "Consolidation complete: promoted=%d pruned=%d patterns=%d",
            report.memories_promoted,
            report.memories_pruned,
            len(report.patterns_found),
        )
        return report
