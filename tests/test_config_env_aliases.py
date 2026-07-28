"""Tests for environment-variable resolution in :mod:`echo.core.config`.

These cover the regression where every ``ECHO_*`` variable in ``.env`` was
silently ignored because ``Settings`` declared no ``env_prefix``, leaving ~34
tuned values dead while the code ran on defaults.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from echo.core.config import Settings, find_unmapped_env_vars


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove inherited variables so tests observe only what they set."""
    for name in (
        "LLM_MAX_TOKENS_AGENT",
        "ECHO_LLM_MAX_TOKENS_AGENT",
        "ECHO_ECHO_LANGUAGE",
        "ECHO_LANGUAGE",
    ):
        monkeypatch.delenv(name, raising=False)


class TestEnvAliases:
    """Both the bare and the ``ECHO_``-prefixed spelling must resolve."""

    def test_prefixed_variable_is_honoured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ECHO_LLM_MAX_TOKENS_AGENT", "777")
        assert Settings(_env_file=None).llm_max_tokens_agent == 777

    def test_bare_variable_is_honoured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_MAX_TOKENS_AGENT", "555")
        assert Settings(_env_file=None).llm_max_tokens_agent == 555

    def test_bare_name_wins_when_both_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_MAX_TOKENS_AGENT", "111")
        monkeypatch.setenv("ECHO_LLM_MAX_TOKENS_AGENT", "222")
        assert Settings(_env_file=None).llm_max_tokens_agent == 111

    def test_field_already_starting_with_echo_still_resolves(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``echo_language`` must keep working under its own bare name."""
        monkeypatch.setenv("ECHO_LANGUAGE", "en")
        assert Settings(_env_file=None).echo_language == "en"

    def test_default_applies_when_nothing_is_set(self) -> None:
        assert Settings(_env_file=None).llm_max_tokens_agent == 1024


class TestFindUnmappedEnvVars:
    """The startup diagnostic must flag dead configuration, and only that."""

    def test_flags_unknown_variable(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("ECHO_TOTALLY_MADE_UP=1\n", encoding="utf-8")
        assert find_unmapped_env_vars(env) == ["ECHO_TOTALLY_MADE_UP"]

    def test_accepts_both_spellings_of_a_real_field(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text(
            "ECHO_LLM_MAX_TOKENS_AGENT=1024\nLLM_MAX_TOKENS_SYNTHESIS=3072\n",
            encoding="utf-8",
        )
        assert find_unmapped_env_vars(env) == []

    def test_ignores_comments_and_blank_lines(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("# ECHO_NOT_REAL=1\n\n   \n", encoding="utf-8")
        assert find_unmapped_env_vars(env) == []

    def test_allows_variables_consumed_by_other_subsystems(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("BRAVE_API_KEY=abc123\n", encoding="utf-8")
        assert find_unmapped_env_vars(env) == []

    def test_missing_file_is_not_an_error(self, tmp_path: Path) -> None:
        assert find_unmapped_env_vars(tmp_path / "nope.env") == []
