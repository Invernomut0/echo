"""Tests for structured-config validation in self-modification.

Self-modification validated ``.py`` files with ``ast.parse`` and wrote every
other file unchecked. A malformed edit to ``data/mcp.json`` therefore committed
cleanly and then made every MCP server fail to load — ECHO lost file access and
web search while still asserting it had them. These tests use the real config
files in the repository.
"""

from __future__ import annotations

import json

import pytest

from echo.self_modification.git_ops import repo_root, validate_structured


class TestRealRepoConfigs:
    """The configs ECHO actually ships must be valid."""

    @pytest.mark.asyncio
    async def test_mcp_config_is_valid(self) -> None:
        path = repo_root() / "data" / "mcp.json"
        ok, err = await validate_structured(str(path))
        assert ok, f"data/mcp.json is malformed: {err}"

    @pytest.mark.asyncio
    async def test_mcp_config_still_declares_the_workspace_server(self) -> None:
        """A repair must not have dropped ECHO's own file-access server."""
        data = json.loads((repo_root() / "data" / "mcp.json").read_text(encoding="utf-8"))
        names = [s["name"] for s in data["servers"]]
        assert "echo-workspace" in names


class TestValidation:
    @pytest.mark.asyncio
    async def test_rejects_the_corruption_that_shipped(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """The exact malformed shape found in data/mcp.json."""
        bad = tmp_path / "mcp.json"
        bad.write_text('{"servers": [{"env": {,\n  "feedback_enabled": false\n}}]}')
        ok, err = await validate_structured(str(bad))
        assert not ok
        assert "JSONDecodeError" in err

    @pytest.mark.asyncio
    async def test_accepts_valid_json(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        good = tmp_path / "settings.json"
        good.write_text('{"feedback_enabled": false}')
        ok, err = await validate_structured(str(good))
        assert ok and err == ""

    @pytest.mark.asyncio
    async def test_rejects_invalid_yaml(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        bad = tmp_path / "config.yaml"
        bad.write_text("a: 1\n  b: 2\n c: 3\n")
        ok, _ = await validate_structured(str(bad))
        assert not ok

    @pytest.mark.asyncio
    async def test_ignores_non_config_files(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Markdown and shell scripts have no parser here and must pass."""
        doc = tmp_path / "README.md"
        doc.write_text("# not json {,,,")
        ok, err = await validate_structured(str(doc))
        assert ok and err == ""
