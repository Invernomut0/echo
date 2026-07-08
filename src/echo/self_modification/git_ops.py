"""Git operations for ECHO self-modification.

Thin subprocess wrapper — used only by SelfModificationEngine.
All operations are relative to the ECHO repo root.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# ECHO repo root — two levels up from this file
REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent.resolve()


async def _run(args: list[str], cwd: Path = REPO_ROOT) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
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
    """Push to origin."""
    rc, out, err = await _run(["git", "push"])
    if rc != 0:
        logger.error("git push failed: %s", err)
        return False
    logger.info("git push: %s", (out or err).strip())
    return True


async def validate_python(path: str) -> tuple[bool, str]:
    """Validate a Python file parses correctly. Returns (ok, error_message)."""
    rc, out, err = await _run(["python3", "-c", f"import ast; ast.parse(open('{path}').read()); print('OK')"])
    if rc == 0 and "OK" in out:
        return True, ""
    return False, (err or out).strip()


def repo_root() -> Path:
    return REPO_ROOT
