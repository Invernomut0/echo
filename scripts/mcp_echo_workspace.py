#!/usr/bin/env python3
"""ECHO Workspace MCP server — read, write, edit files and run git in the ECHO repo.

Tools:
  echo_read_file(path)               — read any file in the repo
  echo_write_file(path, content)     — create or overwrite a file
  echo_edit_file(path, old, new)     — find-and-replace in a file (first occurrence)
  echo_append_file(path, content)    — append text to end of file
  echo_list_files(directory?, glob?) — list files matching a glob pattern
  echo_git(command)                  — run a git command (add/commit/push/status/diff/log)
  echo_validate_python(path)         — check if a .py file parses correctly

All paths are relative to the ECHO repo root (/root/echo or wherever the repo lives).
Absolute paths outside the repo are rejected.
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).parent.parent.resolve()
# Safety: these paths cannot be modified
_WRITE_FORBIDDEN = {
    ".env",
    "data/sqlite",
    "data/chroma",
    "src/echo/self_modification/engine.py",
    "uv.lock",
    "frontend/node_modules",
}


def _safe_path(rel: str) -> Path | str:
    """Resolve rel path to absolute inside repo. Returns error string on failure."""
    p = (_REPO_ROOT / rel.lstrip("/")).resolve()
    if not str(p).startswith(str(_REPO_ROOT)):
        return f"Error: path '{rel}' is outside the ECHO repo"
    return p


def _check_write_allowed(rel: str) -> str | None:
    """Return error string if write is forbidden, else None."""
    for forbidden in _WRITE_FORBIDDEN:
        if rel == forbidden or rel.startswith(forbidden + "/") or rel.startswith(forbidden):
            return f"Error: '{rel}' is protected and cannot be modified"
    return None


def _write_with_validation(p: Path, rel: str, new_content: str, original: str | None) -> str:
    """Write new_content to p. If it's a .py file that becomes invalid, roll back.

    Args:
        original: previous content for rollback (None if the file is new — then the
                  file is deleted on validation failure).
    Returns a human-readable status string.
    """
    import ast

    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(new_content, encoding="utf-8")

    # Safety net: any .py edit must remain syntactically valid, or we revert.
    if p.suffix == ".py":
        try:
            ast.parse(new_content)
        except SyntaxError as e:
            # Roll back so the running system is never left with broken code
            if original is not None:
                p.write_text(original, encoding="utf-8")
                return (
                    f"REJECTED: edit to {rel} would break Python syntax "
                    f"(line {e.lineno}: {e.msg}). Rolled back to previous version. "
                    f"Fix the syntax and retry."
                )
            else:
                p.unlink(missing_ok=True)
                return (
                    f"REJECTED: new file {rel} has invalid Python syntax "
                    f"(line {e.lineno}: {e.msg}). File not created. Fix and retry."
                )
    return f"OK: wrote {len(new_content)} chars to {rel}"


def main() -> None:
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        import mcp.types as types
    except ImportError:
        print("mcp SDK not found", file=sys.stderr)
        sys.exit(1)

    server = Server("echo_workspace")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="echo_read_file",
                description="Read a file from the ECHO repository.",
                inputSchema={
                    "type": "object",
                    "properties": {"path": {"type": "string", "description": "File path relative to repo root"}},
                    "required": ["path"],
                },
            ),
            types.Tool(
                name="echo_write_file",
                description="Create or overwrite a file in the ECHO repository.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            ),
            types.Tool(
                name="echo_edit_file",
                description="Find and replace the first occurrence of old_snippet with new_snippet in a file.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "old_snippet": {"type": "string", "description": "Exact text to find"},
                        "new_snippet": {"type": "string", "description": "Replacement text"},
                    },
                    "required": ["path", "old_snippet", "new_snippet"],
                },
            ),
            types.Tool(
                name="echo_append_file",
                description="Append text to the end of a file.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            ),
            types.Tool(
                name="echo_list_files",
                description="List files in the repo matching an optional glob pattern.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "directory": {"type": "string", "default": ".", "description": "Directory to search"},
                        "glob": {"type": "string", "default": "**/*", "description": "Glob pattern"},
                    },
                },
            ),
            types.Tool(
                name="echo_git",
                description="Run a git command in the ECHO repo. Examples: 'status', 'add src/echo/file.py', 'commit -m \"msg\"', 'push', 'diff HEAD~1', 'log --oneline -5'.",
                inputSchema={
                    "type": "object",
                    "properties": {"command": {"type": "string", "description": "Git subcommand + args (without 'git' prefix)"}},
                    "required": ["command"],
                },
            ),
            types.Tool(
                name="echo_validate_python",
                description="Check whether a Python file parses without syntax errors.",
                inputSchema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        def text(s: str) -> list[types.TextContent]:
            return [types.TextContent(type="text", text=s)]

        if name == "echo_read_file":
            p = _safe_path(arguments["path"])
            if isinstance(p, str):
                return text(p)
            if not p.exists():
                return text(f"Error: file not found: {arguments['path']}")
            try:
                return text(p.read_text(encoding="utf-8", errors="replace"))
            except Exception as e:
                return text(f"Error reading: {e}")

        elif name == "echo_write_file":
            rel = arguments["path"]
            err = _check_write_allowed(rel)
            if err:
                return text(err)
            p = _safe_path(rel)
            if isinstance(p, str):
                return text(p)
            prev = p.read_text(encoding="utf-8") if p.exists() else None
            return text(_write_with_validation(p, rel, arguments["content"], prev))

        elif name == "echo_edit_file":
            rel = arguments["path"]
            err = _check_write_allowed(rel)
            if err:
                return text(err)
            p = _safe_path(rel)
            if isinstance(p, str):
                return text(p)
            if not p.exists():
                return text(f"Error: file not found: {rel}")
            original = p.read_text(encoding="utf-8")
            old = arguments["old_snippet"]
            new = arguments["new_snippet"]
            if old not in original:
                return text(f"Error: old_snippet not found in {rel}")
            modified = original.replace(old, new, 1)
            result = _write_with_validation(p, rel, modified, original)
            if result.startswith("OK"):
                return text(f"OK: edited {rel} ({len(old)} → {len(new)} chars at first occurrence)")
            return text(result)

        elif name == "echo_append_file":
            rel = arguments["path"]
            err = _check_write_allowed(rel)
            if err:
                return text(err)
            p = _safe_path(rel)
            if isinstance(p, str):
                return text(p)
            original = p.read_text(encoding="utf-8") if p.exists() else ""
            appended = original + arguments["content"]
            result = _write_with_validation(p, rel, appended, original if p.exists() else None)
            if result.startswith("OK"):
                return text(f"OK: appended {len(arguments['content'])} chars to {rel}")
            return text(result)

        elif name == "echo_list_files":
            directory = arguments.get("directory", ".")
            glob = arguments.get("glob", "**/*")
            base = _safe_path(directory)
            if isinstance(base, str):
                return text(base)
            if not base.is_dir():
                return text(f"Error: not a directory: {directory}")
            skip = {"node_modules", "__pycache__", ".venv", "data/sqlite", "data/chroma"}
            results = []
            for p in sorted(base.glob(glob)):
                if not p.is_file():
                    continue
                rel = str(p.relative_to(_REPO_ROOT))
                if any(s in rel for s in skip):
                    continue
                results.append(rel)
            return text("\n".join(results[:200]) or "(no files found)")

        elif name == "echo_git":
            import shlex
            cmd = arguments["command"].strip()
            # Safety: block destructive forced operations
            blocked = ["push --force", "push -f", "reset --hard", "clean -f", "branch -D"]
            for b in blocked:
                if b in cmd:
                    return text(f"Error: blocked git command: '{b}'")

            def _run_git(subcmd: str) -> subprocess.CompletedProcess:
                return subprocess.run(
                    ["git"] + shlex.split(subcmd),
                    cwd=str(_REPO_ROOT),
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

            try:
                # Before push: pull --rebase to avoid rejected non-fast-forward
                if cmd.startswith("push"):
                    pull = _run_git("pull --rebase")
                    if pull.returncode != 0:
                        return text(
                            f"Error: pull --rebase failed before push:\n{(pull.stdout + pull.stderr).strip()}"
                        )
                result = _run_git(cmd)
                out = result.stdout + result.stderr
                return text(out.strip() or f"(exit code {result.returncode})")
            except subprocess.TimeoutExpired:
                return text("Error: git command timed out")
            except Exception as e:
                return text(f"Error: {e}")

        elif name == "echo_validate_python":
            p = _safe_path(arguments["path"])
            if isinstance(p, str):
                return text(p)
            if not p.exists():
                return text(f"Error: file not found: {arguments['path']}")
            import ast
            try:
                ast.parse(p.read_text(encoding="utf-8"))
                return text(f"OK: {arguments['path']} is valid Python")
            except SyntaxError as e:
                return text(f"SyntaxError in {arguments['path']}: {e}")

        else:
            return text(f"Error: unknown tool '{name}'")

    async def _serve() -> None:
        async with stdio_server() as (r, w):
            await server.run(r, w, server.create_initialization_options())

    asyncio.run(_serve())


if __name__ == "__main__":
    main()
