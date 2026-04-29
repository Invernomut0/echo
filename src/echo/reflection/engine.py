"""Reflection engine — post-interaction introspective analysis."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from echo.core.llm_client import llm
from echo.core.types import (
    BeliefRelation,
    IdentityBelief,
    MetaState,
    ReflectionResult,
)
from echo.self_model.identity_graph import IdentityGraph

logger = logging.getLogger(__name__)

_REFLECTION_PROMPT = """\
You are ECHO's introspective reflection engine.

Analyse the following interaction and provide reflection in JSON format.

Current beliefs (sample):
{beliefs}

Current drives:
  coherence={coherence:.2f}  curiosity={curiosity:.2f}  stability={stability:.2f}
  competence={competence:.2f}  compression={compression:.2f}
{workspace_context}
Interaction:
User: {user_input}
ECHO: {response}

Respond ONLY with this JSON structure (no markdown):
{{
  "insights": ["insight1", "insight2"],
  "new_beliefs": [
    {{"content": "...", "confidence": 0.7}}
  ],
  "belief_updates": {{
    "belief_id_or_content_fragment": 0.1
  }},
  "drive_adjustments": {{
    "coherence": 0.0,
    "curiosity": 0.05,
    "stability": -0.02,
    "competence": 0.03,
    "compression": 0.0
  }}
}}"""


class ReflectionEngine:
    """Asynchronous post-interaction reflection."""

    def __init__(self, identity_graph: IdentityGraph) -> None:
        self._graph = identity_graph

    async def reflect(
        self,
        interaction_id: str,
        user_input: str,
        response: str,
        meta_state: MetaState,
        workspace_summary: str = "",
    ) -> ReflectionResult:
        """Run reflection and update the identity graph. Returns structured result.

        workspace_summary: newline-separated list of active workspace items at the
        time of the interaction (i.e., what was "consciously" active in ECHO's GWT).
        """
        # Summarise current beliefs for context
        beliefs = self._graph.all_beliefs()
        belief_summaries = "\n".join(
            f"  - [{b.id[:8]}] {b.content[:100]} (conf={b.confidence:.2f})"
            for b in beliefs[:10]
        )
        if not belief_summaries:
            belief_summaries = "  (none yet)"

        d = meta_state.drives
        # IM-8: Include active workspace items so reflection knows what was "conscious"
        workspace_context = ""
        if workspace_summary:
            workspace_context = f"\nActive workspace items:\n{workspace_summary}\n"

        prompt = _REFLECTION_PROMPT.format(
            beliefs=belief_summaries,
            coherence=d.coherence,
            curiosity=d.curiosity,
            stability=d.stability,
            competence=d.competence,
            compression=d.compression,
            workspace_context=workspace_context,
            user_input=user_input[:400],
            response=response[:400],
        )

        raw = await llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=512,
        )

        result = ReflectionResult(interaction_id=interaction_id)

        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            data = json.loads(raw[start:end])

            result.insights = data.get("insights", [])
            result.drive_adjustments = {
                k: float(v) for k, v in data.get("drive_adjustments", {}).items()
            }

            # Process new beliefs
            for nb in data.get("new_beliefs", []):
                if isinstance(nb, dict) and nb.get("content"):
                    belief = IdentityBelief(
                        content=nb["content"],
                        confidence=float(nb.get("confidence", 0.5)),
                    )
                    await self._graph.add_belief(belief)
                    result.new_beliefs.append(belief)

            # Process confidence updates
            for fragment, delta in data.get("belief_updates", {}).items():
                for existing in beliefs:
                    if fragment.lower() in existing.content.lower():
                        updated = await self._graph.update_belief_confidence(
                            existing.id, float(delta)
                        )
                        if updated:
                            result.updated_belief_ids.append(existing.id)

        except Exception as exc:  # noqa: BLE001
            logger.warning("Reflection parsing failed: %s | raw: %.200s", exc, raw)

        logger.info(
            "Reflection complete: %d insights, %d new beliefs, %d updated",
            len(result.insights),
            len(result.new_beliefs),
            len(result.updated_belief_ids),
        )
        return result
