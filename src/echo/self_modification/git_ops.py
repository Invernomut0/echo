"""Git operations for ECHO self-modification.

Thin subprocess wrapper — used only by SelfModificationEngine.
All operations are relative to the ECHO repo root.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import stat
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# ECHO repo root — git_ops.py is at REPO/src/echo/self_modification/git_ops.py
# so 4 .parent calls reach REPO root
REPO_ROOT = Path(__file__).parent.parent.parent.parent.resolve()


async def _run(
    args: list[str],
    cwd: Path = REPO_ROOT,
    extra_env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode(errors="replace"), stderr.decode(errors="replace")


async def git_status() -> str:
    """Return git status output."""
    rc, out, err = await _run(["git", "status", "--short"])
    return out.strip()


async def git_diff(path: str | None = None) -> str:
    """Return diff of unstaged changes (or specific path)."""
    args = ["git", "diff"]
    if path:
        args.append(path)
    rc, out, _ = await _run(args)
    return out


async def git_add(paths: list[str]) -> bool:
    """Stage specific files."""
    rc, _, err = await _run(["git", "add", "--"] + paths)
    if rc != 0:
        logger.error("git add failed: %s", err)
    return rc == 0


async def git_commit(message: str) -> bool:
    """Commit staged changes."""
    rc, out, err = await _run(["git", "commit", "-m", message])
    if rc != 0:
        logger.error("git commit failed: %s", err)
        return False
    logger.info("git commit: %s", out.strip().splitlines()[0] if out else "done")
    return True


async def git_push() -> bool:
    """Push to origin, authenticating with GITHUB_TOKEN when available.

    The token is injected via a short-lived GIT_ASKPASS script so it never
    appears in process arguments or logs.
    """
    from echo.core.config import settings  # lazy import to avoid circular deps

    token = (settings.github_token or "").strip()
    askpass_path: str | None = None
    extra_env: dict[str, str] = {}

    if token:
        # Write a temporary executable script that echoes the token.
        # Git calls GIT_ASKPASS to retrieve passwords non-interactively.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sh", delete=False, prefix="echo_askpass_"
        ) as f:
            # Use single-quotes in the script; token must not contain single-quotes.
            safe_token = token.replace("'", "'\"'\"'")
            f.write(f"#!/bin/sh\necho '{safe_token}'\n")
            askpass_path = f.name
        os.chmod(askpass_path, stat.S_IRWXU)  # owner execute only
        extra_env["GIT_ASKPASS"] = askpass_path
        extra_env["GIT_TERMINAL_PROMPT"] = "0"  # never hang waiting for input

    try:
        rc, out, err = await _run(["git", "push"], extra_env=extra_env or None)
    finally:
        if askpass_path:
            try:
                os.unlink(askpass_path)
            except OSError:
                pass

    if rc != 0:
        logger.error("git push failed: %s", err)
        return False
    logger.info("git push: %s", (out or err).strip())
    return True


async def validate_python(path: str) -> tuple[bool, str]:
    """Validate a Python file parses correctly. Returns (ok, error_message).

    The path is passed through ``argv`` rather than interpolated into the
    source string: ECHO derives these paths from LLM output, so a filename
    containing a quote would otherwise break out and execute arbitrary code.
    """
    rc, out, err = await _run(
        [
            sys.executable,
            "-c",
            "import ast, sys; ast.parse(open(sys.argv[1]).read()); print('OK')",
            path,
        ]
    )
    if rc == 0 and "OK" in out:
        return True, ""
    return False, (err or out).strip()


async def validate_structured(path: str) -> tuple[bool, str]:
    """Validate a JSON or YAML config file parses. Returns (ok, error_message).

    Self-modification only ever checked ``.py`` files, so a malformed config
    edit was committed silently. That is not a cosmetic failure: a broken
    ``data/mcp.json`` makes every MCP server fail to load, and ECHO then
    genuinely loses file access and web search while still believing it has
    them. Non-config extensions pass through untouched.
    """
    suffix = Path(path).suffix.lower()
    try:
        text = Path(path).read_text(encoding="utf-8")
        if suffix == ".json":
            json.loads(text)
        elif suffix in {".yaml", ".yml"}:
            import yaml

            yaml.safe_load(text)
        else:
            return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"
    return True, ""


def repo_root() -> Path:
    return REPO_ROOT
