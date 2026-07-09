#!/usr/bin/env python3
"""Bash execution MCP server (stdio transport).

Exposes one tool: bash_exec
  - command: bash command string to run
  - cwd: working directory (default: ECHO repo root)
  - timeout: max seconds (default 30, max 120)
  - env_extra: optional dict of extra env vars to inject

Security constraints:
  - Runs as the current user (no privilege escalation)
  - Hard timeout enforced via asyncio
  - Working directory defaults to the ECHO repo, not /
  - Blocked commands: rm -rf /, shutdown, reboot, mkfs, dd if=/dev/zero

Start with: python3 scripts/mcp_bash_server.py
"""

import asyncio
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

# ECHO repo root (one level up from scripts/)
_REPO_ROOT = str(Path(__file__).parent.parent.resolve())

_MAX_TIMEOUT = 120  # hard cap in seconds
_DEFAULT_TIMEOUT = 30
_MAX_OUTPUT = 50_000  # chars

# Commands / patterns that are unconditionally blocked
_BLOCKED = [
    "rm -rf /",
    "mkfs",
    "dd if=/dev/zero",
    "> /dev/sda",
    "shutdown",
    "reboot",
    ":(){ :|:& };:",  # fork bomb
]


def _is_blocked(command: str) -> str | None:
    lower = command.lower()
    for b in _BLOCKED:
        if b in lower:
            return b
    return None


async def _run_bash(
    command: str,
    cwd: str | None,
    timeout: int,
    env_extra: dict[str, str] | None,
) -> dict[str, Any]:
    blocked = _is_blocked(command)
    if blocked:
        return {
            "stdout": "",
            "stderr": f"Command blocked: matched pattern '{blocked}'",
            "exit_code": -1,
            "blocked": True,
        }

    effective_cwd = cwd or _REPO_ROOT
    if not Path(effective_cwd).exists():
        effective_cwd = _REPO_ROOT

    effective_timeout = max(1, min(timeout, _MAX_TIMEOUT))

    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=effective_cwd,
            env=env,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=effective_timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return {
                "stdout": "",
                "stderr": f"Command timed out after {effective_timeout}s",
                "exit_code": -1,
                "timed_out": True,
            }

        stdout = stdout_b.decode(errors="replace")[:_MAX_OUTPUT]
        stderr = stderr_b.decode(errors="replace")[:_MAX_OUTPUT]
        return {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": proc.returncode,
            "cwd": effective_cwd,
        }

    except Exception as exc:
        return {
            "stdout": "",
            "stderr": f"Error running command: {exc}",
            "exit_code": -1,
        }


# ---------------------------------------------------------------------------
# MCP server using the mcp SDK
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        import mcp.types as types
    except ImportError:
        print("mcp SDK not found. Install with: pip install mcp", file=sys.stderr)
        sys.exit(1)

    server = Server("bash")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="bash_exec",
                description=(
                    "Execute a bash command and return stdout, stderr, and exit code. "
                    "Working directory defaults to the ECHO repo root. "
                    "Commands that could destroy the system are blocked."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Bash command to execute",
                        },
                        "cwd": {
                            "type": "string",
                            "description": "Working directory (default: ECHO repo root)",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": f"Timeout in seconds (default {_DEFAULT_TIMEOUT}, max {_MAX_TIMEOUT})",
                            "default": _DEFAULT_TIMEOUT,
                        },
                        "env_extra": {
                            "type": "object",
                            "description": "Extra environment variables to inject",
                        },
                    },
                    "required": ["command"],
                },
            )
        ]

    @server.call_tool()
    async def call_tool(
        name: str, arguments: dict[str, Any]
    ) -> list[types.TextContent]:
        if name != "bash_exec":
            raise ValueError(f"Unknown tool: {name}")

        command = arguments["command"]
        cwd = arguments.get("cwd")
        timeout = int(arguments.get("timeout", _DEFAULT_TIMEOUT))
        env_extra = arguments.get("env_extra")

        result = await _run_bash(command, cwd, timeout, env_extra)

        output_parts = []
        if result.get("blocked"):
            output_parts.append(f"🚫 BLOCKED: {result['stderr']}")
        elif result.get("timed_out"):
            output_parts.append(f"⏱️ TIMEOUT: {result['stderr']}")
        else:
            if result["stdout"]:
                output_parts.append(f"STDOUT:\n{result['stdout']}")
            if result["stderr"]:
                output_parts.append(f"STDERR:\n{result['stderr']}")
            output_parts.append(f"EXIT CODE: {result['exit_code']}")
            if "cwd" in result:
                output_parts.append(f"CWD: {result['cwd']}")

        return [types.TextContent(type="text", text="\n\n".join(output_parts))]

    asyncio.run(stdio_server(server))


if __name__ == "__main__":
    main()
