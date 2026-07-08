"""WikiSyncEngine — automatically syncs ECHO's wiki from a GitHub repository.

Fetches all .md files from the configured repo (default: Invernomut0/echo),
detects changes via commit SHA, and ingests new/modified files into the wiki.

Config:
    WIKI_SYNC_REPO=https://github.com/Invernomut0/echo
    WIKI_SYNC_ENABLED=true
    WIKI_SYNC_INTERVAL_H=24
    WIKI_SYNC_MAX_FILES=50
    GITHUB_TOKEN=ghp_...   (optional — raises rate limit from 60 to 5000 req/hour)
"""

from __future__ import annotations

import base64
import logging
import re
import time as _time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"


def _parse_repo(url: str) -> tuple[str, str] | None:
    """Parse 'https://github.com/owner/repo' → ('owner', 'repo')."""
    m = re.search(r"github\.com/([^/]+)/([^/\s?#]+)", url)
    if not m:
        return None
    return m.group(1), m.group(2).rstrip(".git")


class WikiSyncEngine:
    """Fetches .md files from a GitHub repo and ingests them into ECHO's wiki."""

    def __init__(self) -> None:
        self._last_sync: float = 0.0
        self._last_commit_sha: str = ""
        self._synced_files: dict[str, str] = {}   # path → sha (content hash)

    async def sync(self) -> dict[str, Any]:
        """Run one sync cycle. Returns summary dict."""
        from echo.core.config import settings  # noqa: PLC0415
        from echo.core.user_activity import is_active as _ua  # noqa: PLC0415
        from echo.memory.wiki import wiki  # noqa: PLC0415

        if not settings.wiki_sync_enabled:
            return {"skipped": "disabled"}

        # Cooldown
        interval_s = settings.wiki_sync_interval_h * 3600
        elapsed = _time.monotonic() - self._last_sync
        if elapsed < interval_s:
            return {"skipped": f"cooldown ({int(interval_s - elapsed)}s remaining)"}

        # Skip during active session
        if _ua():
            return {"skipped": "user_active"}

        repo_url = settings.wiki_sync_repo
        parsed = _parse_repo(repo_url)
        if not parsed:
            logger.error("WikiSync: cannot parse repo URL: %s", repo_url)
            return {"error": f"invalid repo URL: {repo_url}"}

        owner, repo = parsed
        token = settings.github_token.strip() or None
        headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "ECHO-WikiSync/1.0"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            # Check if repo has new commits since last sync
            try:
                r = await client.get(f"{_GITHUB_API}/repos/{owner}/{repo}/commits/HEAD")
                r.raise_for_status()
                latest_sha = r.json().get("sha", "")
            except Exception as exc:  # noqa: BLE001
                logger.warning("WikiSync: commit check failed: %s", exc)
                return {"error": str(exc)}

            if latest_sha == self._last_commit_sha:
                logger.debug("WikiSync: no new commits since last sync")
                self._last_sync = _time.monotonic()
                return {"skipped": "no_new_commits", "sha": latest_sha}

            logger.info("WikiSync: new commits detected (%s → %s), syncing…", self._last_commit_sha[:8], latest_sha[:8])

            # List all .md files via tree API
            try:
                r = await client.get(
                    f"{_GITHUB_API}/repos/{owner}/{repo}/git/trees/{latest_sha}",
                    params={"recursive": "1"},
                )
                r.raise_for_status()
                tree = r.json().get("tree", [])
            except Exception as exc:  # noqa: BLE001
                logger.warning("WikiSync: tree fetch failed: %s", exc)
                return {"error": str(exc)}

            md_files = [
                item for item in tree
                if item.get("type") == "blob"
                and item.get("path", "").endswith(".md")
                and not item["path"].startswith(".")
            ]

            if not md_files:
                logger.info("WikiSync: no .md files found in repo")
                self._last_sync = _time.monotonic()
                self._last_commit_sha = latest_sha
                return {"synced": 0, "total_md": 0}

            # Limit and prioritize: process changed files first
            max_files = settings.wiki_sync_max_files
            changed = [f for f in md_files if self._synced_files.get(f["path"]) != f.get("sha", "")]
            unchanged = [f for f in md_files if f not in changed]
            to_process = (changed + unchanged)[:max_files]

            logger.info(
                "WikiSync: %d .md files total, %d changed, processing up to %d",
                len(md_files), len(changed), min(len(to_process), max_files),
            )

            synced = 0
            errors = 0
            for item in to_process:
                path = item["path"]
                file_sha = item.get("sha", "")

                # Skip if content unchanged
                if self._synced_files.get(path) == file_sha and file_sha:
                    continue

                # Fetch file content
                try:
                    r = await client.get(
                        f"{_GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
                        params={"ref": latest_sha},
                    )
                    r.raise_for_status()
                    data = r.json()
                    content_b64 = data.get("content", "")
                    content = base64.b64decode(content_b64.replace("\n", "")).decode("utf-8", errors="replace")
                except Exception as exc:  # noqa: BLE001
                    logger.warning("WikiSync: fetch failed for %s: %s", path, exc)
                    errors += 1
                    continue

                if not content.strip():
                    continue

                # Ingest into wiki
                title = path.replace("/", " › ").replace(".md", "")
                try:
                    result = await wiki.ingest(content, title=f"[{repo}] {title}", source_type="github_md")
                    self._synced_files[path] = file_sha
                    synced += 1
                    logger.debug("WikiSync: ingested %s (%s)", path, result.get("pages_written", "?"))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("WikiSync: ingest failed for %s: %s", path, exc)
                    errors += 1

            self._last_sync = _time.monotonic()
            self._last_commit_sha = latest_sha

            summary = {
                "synced": synced,
                "errors": errors,
                "total_md": len(md_files),
                "changed": len(changed),
                "sha": latest_sha[:12],
                "repo": f"{owner}/{repo}",
            }
            logger.info("WikiSync complete: %s", summary)
            return summary


# Singleton
wiki_sync = WikiSyncEngine()
