#!/usr/bin/env python3
"""Datetime MCP server (stdio transport).

Exposes two tools:
  - get_current_datetime  → ISO datetime + human-readable + timezone info
  - get_current_date      → date only (YYYY-MM-DD)

Start with: python3 scripts/mcp_datetime_server.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _now(tz_name: str | None) -> datetime:
    if tz_name:
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            tz = timezone.utc
    else:
        # Local system timezone
        tz = datetime.now().astimezone().tzinfo  # type: ignore[assignment]
    return datetime.now(tz=tz)


def _datetime_payload(tz_name: str | None) -> dict[str, Any]:
    now = _now(tz_name)
    return {
        "iso": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
        "timezone": str(now.tzinfo),
        "unix_timestamp": int(now.timestamp()),
        "human": now.strftime("%A, %d %B %Y — %H:%M:%S %Z"),
    }


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        import mcp.types as types
    except ImportError:
        print("mcp SDK not found. Install with: pip install mcp", file=sys.stderr)
        sys.exit(1)

    import asyncio
    import json

    server = Server("datetime")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        tz_prop = {
            "type": "string",
            "description": (
                "IANA timezone name (e.g. 'Europe/Rome', 'UTC', 'America/New_York'). "
                "Defaults to system local timezone."
            ),
        }
        return [
            types.Tool(
                name="get_current_datetime",
                description=(
                    "Return the current date and time. "
                    "Includes ISO format, human-readable string, weekday, timezone, and unix timestamp."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {"timezone": tz_prop},
                    "required": [],
                },
            ),
            types.Tool(
                name="get_current_date",
                description="Return the current date as YYYY-MM-DD.",
                inputSchema={
                    "type": "object",
                    "properties": {"timezone": tz_prop},
                    "required": [],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(
        name: str, arguments: dict[str, Any]
    ) -> list[types.TextContent]:
        tz_name: str | None = arguments.get("timezone")

        if name == "get_current_datetime":
            payload = _datetime_payload(tz_name)
            text = json.dumps(payload, ensure_ascii=False)
        elif name == "get_current_date":
            now = _now(tz_name)
            text = now.strftime("%Y-%m-%d")
        else:
            raise ValueError(f"Unknown tool: {name}")

        return [types.TextContent(type="text", text=text)]

    async def run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(run())


if __name__ == "__main__":
    main()
