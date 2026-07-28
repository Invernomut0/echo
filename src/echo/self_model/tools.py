"""Self-model introspection tools — LLM-callable access to the identity graph.

The synthesis prompt carries only a bounded selection of beliefs (see
``orchestrator._fmt_beliefs``), which is the right trade-off for a normal turn
but leaves ECHO unable to answer a direct request such as "list all the beliefs
you hold": the remaining beliefs are simply not in its context, so any answer it
gives is a guess. These tools let it read its own identity graph on demand.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from echo.mcp.client import MCPClientManager
    from echo.self_model.identity_graph import IdentityGraph

logger = logging.getLogger(__name__)

# Beliefs returned by a single call. The graph is capped at 300; returning all
# of them would undo the payload savings the tool cap exists to protect.
_DEFAULT_LIMIT = 50
_MAX_LIMIT = 300

_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "echo__list_beliefs",
            "description": (
                "List the identity beliefs ECHO currently holds, ordered by "
                "confidence. Use this whenever the user asks what you believe, "
                "what you know about yourself, or for a list of your beliefs — "
                "the prompt only ever shows a subset, so answer from this tool "
                "rather than from memory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": (
                            f"Maximum beliefs to return (default {_DEFAULT_LIMIT}, "
                            f"max {_MAX_LIMIT})."
                        ),
                    },
                    "min_confidence": {
                        "type": "number",
                        "description": "Only return beliefs at or above this confidence (0.0-1.0).",
                    },
                    "query": {
                        "type": "string",
                        "description": (
                            "Optional substring filter applied to belief text, "
                            "case-insensitive."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
]


def _make_handlers(graph: IdentityGraph) -> dict[str, Any]:
    """Build tool handlers bound to a live identity graph."""

    async def _list_beliefs(args: dict[str, Any]) -> str:
        try:
            limit = min(int(args.get("limit") or _DEFAULT_LIMIT), _MAX_LIMIT)
            min_confidence = float(args.get("min_confidence") or 0.0)
            query = str(args.get("query") or "").strip().lower()

            beliefs = [b for b in graph.all_beliefs() if b.confidence >= min_confidence]
            if query:
                beliefs = [b for b in beliefs if query in b.content.lower()]
            beliefs.sort(key=lambda b: b.confidence, reverse=True)

            return json.dumps({
                "ok": True,
                "total_in_graph": len(graph.all_beliefs()),
                "returned": len(beliefs[:limit]),
                "beliefs": [
                    {"content": b.content, "confidence": round(b.confidence, 3)}
                    for b in beliefs[:limit]
                ],
            }, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("list_beliefs failed: %s", exc)
            return json.dumps({"ok": False, "error": str(exc)})

    return {"echo__list_beliefs": _list_beliefs}


def register_self_model_tools(mcp_manager: MCPClientManager, graph: IdentityGraph) -> None:
    """Register self-model introspection tools into the MCP manager."""
    handlers = _make_handlers(graph)
    for tool_def in _TOOLS:
        name = tool_def["function"]["name"]
        mcp_manager.register_internal_tool(
            qualified_name=name,
            openai_def=tool_def,
            handler=handlers[name],
        )
    logger.info("[SelfModel] Registered %d introspection tool(s)", len(_TOOLS))
