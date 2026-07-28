"""Tests for request-payload optimisation.

These cover the three defects that made a single chat turn ship a ~19.7k-token
prompt to the local backend (observed in LM Studio logs: prompt processing
stalled at 41% after two minutes and the HTTP read timed out):

1. every connected MCP tool schema was attached to every request;
2. failed assistant turns were replayed as ``[previous response failed]``;
3. a user retrying the same question produced duplicate consecutive turns.
"""

from __future__ import annotations

import json

from echo.agents.orchestrator import _trim_history
from echo.core.config import settings
from echo.mcp.client import MCPClientManager


def _tool(name: str, description: str, props: dict | None = None) -> dict:
    """Build an OpenAI-format tool schema of realistic size."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": props or {"input": {"type": "string", "description": "input"}},
                "required": ["input"],
            },
        },
    }


def _realistic_toolset() -> list[dict]:
    """Reproduce the shape of the payload captured from the running instance.

    112 tools across 8 servers, with ``opencode-mcp`` contributing 80 of them.
    """
    tools: list[dict] = []
    for i in range(7):
        tools.append(_tool(f"echo-workspace__ws_{i}", f"Workspace operation number {i}"))
    tools.append(_tool("bash__bash_exec", "Execute a bash command"))
    for i in range(2):
        tools.append(_tool(f"datetime__dt_{i}", f"Date and time helper {i}"))
    for i in range(80):
        tools.append(_tool(
            f"opencode-mcp__oc_{i}",
            f"OpenCode session, provider, OAuth and TUI management operation {i}",
        ))
    tools.append(_tool("fetch__fetch", "Fetch a URL and return its contents as markdown"))
    for i in range(14):
        tools.append(_tool(f"filesystem__fs_{i}", f"Filesystem operation {i}"))
    tools.append(_tool("brave_search__brave_web_search", "Search the web with Brave"))
    tools.append(_tool("brave_search__brave_local_search", "Search local businesses with Brave"))
    for name in ("list_tasks", "create_task", "update_task", "delete_task", "trigger_task"):
        tools.append(_tool(f"echo__cron_{name}", f"Cron scheduling: {name}"))
    return tools


class _StubManager(MCPClientManager):
    """MCPClientManager whose tool inventory is fixed, no live servers needed."""

    def __init__(self, tools: list[dict]) -> None:  # noqa: D107
        self._tools = tools

    def list_tools_openai(self) -> list[dict]:  # type: ignore[override]
        return list(self._tools)


class TestToolSelection:
    """``select_tools_openai`` must shrink the payload without losing capability."""

    def test_realistic_payload_is_oversized(self) -> None:
        """Sanity check: the captured setup really is ~112 tools / ~20k tokens."""
        tools = _realistic_toolset()
        assert len(tools) == 112
        # ~4 chars per token is the usual rule of thumb for JSON schemas.
        approx_tokens = len(json.dumps(tools)) / 4
        assert approx_tokens > 5000, approx_tokens

    def test_selection_respects_the_cap(self) -> None:
        mgr = _StubManager(_realistic_toolset())
        selected = mgr.select_tools_openai("what time is it?", max_tools=24)
        assert len(selected) <= 24

    def test_selection_cuts_payload_size_substantially(self) -> None:
        mgr = _StubManager(_realistic_toolset())
        before = len(json.dumps(mgr.list_tools_openai()))
        after = len(json.dumps(mgr.select_tools_openai("list my beliefs", max_tools=24)))
        assert after < before * 0.3, f"only shrunk from {before} to {after}"

    def test_echo_internal_tools_are_always_kept(self) -> None:
        """ECHO's own tools are its only handle on its cognitive scheduler."""
        mgr = _StubManager(_realistic_toolset())
        selected = mgr.select_tools_openai("tell me a joke", max_tools=24)
        names = {t["function"]["name"] for t in selected}
        for name in ("echo__cron_list_tasks", "echo__cron_create_task",
                     "echo__cron_update_task", "echo__cron_delete_task",
                     "echo__cron_trigger_task"):
            assert name in names

    def test_broadly_useful_servers_are_always_kept(self) -> None:
        mgr = _StubManager(_realistic_toolset())
        selected = mgr.select_tools_openai("tell me a joke", max_tools=24)
        names = {t["function"]["name"] for t in selected}
        assert "brave_search__brave_web_search" in names
        assert "fetch__fetch" in names

    def test_relevant_tools_win_the_remaining_slots(self) -> None:
        """A filesystem question should surface filesystem tools over TUI ones."""
        tools = [
            _tool("echo__cron_list_tasks", "List scheduled cognitive tasks"),
            _tool("filesystem__read_text_file", "Read the contents of a text file from disk"),
            _tool("opencode-mcp__tui_show_toast", "Show a toast notification in the TUI"),
            _tool("opencode-mcp__provider_oauth_authorize", "Begin an OAuth authorize flow"),
        ]
        mgr = _StubManager(tools)
        selected = mgr.select_tools_openai("read the contents of a text file", max_tools=2)
        names = {t["function"]["name"] for t in selected}
        assert "filesystem__read_text_file" in names
        assert "opencode-mcp__tui_show_toast" not in names

    def test_small_toolsets_are_returned_untouched(self) -> None:
        tools = [_tool("filesystem__read_file", "Read a file")]
        mgr = _StubManager(tools)
        assert mgr.select_tools_openai("anything", max_tools=24) == tools

    def test_zero_disables_the_cap(self) -> None:
        mgr = _StubManager(_realistic_toolset())
        assert len(mgr.select_tools_openai("anything", max_tools=0)) == 112

    def test_default_setting_is_a_sane_cap(self) -> None:
        assert 0 < settings.llm_max_tools <= 40


class TestHistoryHygiene:
    """Failed turns must not be replayed back to the model."""

    def test_failed_assistant_turns_are_dropped(self) -> None:
        history = [
            {"role": "user", "content": "list your beliefs"},
            {"role": "assistant", "content": "[Error: ReadTimeout]"},
        ]
        trimmed = _trim_history(history)
        assert all(m["role"] != "assistant" for m in trimmed)
        assert not any("failed" in m["content"] for m in trimmed)

    def test_placeholder_is_no_longer_emitted(self) -> None:
        """The old implementation kept a '[previous response failed]' marker."""
        history = [{"role": "assistant", "content": "[Error: boom]"}]
        assert _trim_history(history) == []

    def test_repeated_user_question_is_collapsed(self) -> None:
        """The exact retry pattern captured from the running instance."""
        history = [
            {"role": "user", "content": "dammi l'elenco dei belief"},
            {"role": "assistant", "content": "[Error: timeout]"},
            {"role": "user", "content": "dammi l'elenco dei belief"},
            {"role": "assistant", "content": "[Error: timeout]"},
            {"role": "user", "content": "dammi l'elenco dei belief"},
            {"role": "assistant", "content": "[Error: timeout]"},
        ]
        trimmed = _trim_history(history)
        assert trimmed == [{"role": "user", "content": "dammi l'elenco dei belief"}]

    def test_empty_assistant_turns_are_dropped(self) -> None:
        history = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "   "},
        ]
        assert _trim_history(history) == [{"role": "user", "content": "hi"}]

    def test_distinct_user_messages_are_preserved(self) -> None:
        history = [
            {"role": "user", "content": "first question"},
            {"role": "assistant", "content": "first answer"},
            {"role": "user", "content": "second question"},
        ]
        trimmed = _trim_history(history)
        assert [m["content"] for m in trimmed] == [
            "first question", "first answer", "second question",
        ]

    def test_long_content_is_still_truncated(self) -> None:
        history = [{"role": "user", "content": "x" * 900}]
        trimmed = _trim_history(history, max_content_chars=400)
        assert len(trimmed[0]["content"]) == 401  # 400 chars + ellipsis

    def test_turn_cap_is_applied_after_cleaning(self) -> None:
        """Errors must not consume slots in the ``max_turns`` window."""
        history: list[dict[str, str]] = []
        for i in range(5):
            history.append({"role": "user", "content": f"q{i}"})
            history.append({"role": "assistant", "content": "[Error: boom]"})
        trimmed = _trim_history(history, max_turns=4)
        assert [m["content"] for m in trimmed] == ["q1", "q2", "q3", "q4"]


class TestReadTimeout:
    """A local backend stays silent during prompt processing."""

    def test_read_timeout_covers_slow_prompt_processing(self) -> None:
        # 19.7k tokens at the observed ~160 tok/s needs ~123 s of silence.
        assert settings.llm_read_timeout_s >= 180.0
