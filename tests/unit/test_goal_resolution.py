"""Unit tests for centralized goal-resolution consolidation."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from echo.memory.goals import GoalStore, _build_goal_resolution_payload, _persist_goal_resolution



def test_build_goal_resolution_payload_contains_required_fields():
    goal = {
        "id": "goal-123",
        "title": "Fix Telegram typing in channels",
        "description": "Improve channel UX by showing typing and clear completion feedback.",
        "priority": 0.8,
        "status": "achieved",
        "achieved_at": "2026-01-01T00:00:00+00:00",
        "tags": ["telegram", "ux"],
        "actions": [
            {
                "description": "Investigate channel-specific API behaviour",
                "result": "Typing action is not visible in channels unless a placeholder message exists.",
                "status": "done",
            },
            {
                "description": "Implement placeholder-edit flow",
                "result": "Added placeholder send/edit/delete fallback for channels.",
                "status": "done",
            },
        ],
    }

    payload = _build_goal_resolution_payload(goal)

    assert payload["goal_title"] == "Fix Telegram typing in channels"
    assert payload["why_chosen"].startswith("Improve channel UX")
    assert "placeholder" in payload["solution_summary"].lower()

    semantic = payload["semantic_content"]
    assert "Goal: Fix Telegram typing in channels" in semantic
    assert "Perché scelto:" in semantic
    assert "Informazioni ricavate:" in semantic
    assert "Soluzione adottata:" in semantic
    assert "Riassunto soluzione:" in semantic


@pytest.mark.asyncio
async def test_update_status_triggers_consolidation_once_on_achieved_transition(db, monkeypatch):
    from echo.memory import goals as goals_module

    store = GoalStore()
    goal = await store.create(
        title="Consolidate achieved goals",
        description="Persist final goal learning in semantic memory.",
        priority=0.7,
    )

    persist_mock = AsyncMock()
    monkeypatch.setattr(goals_module, "_persist_goal_resolution", persist_mock)

    # No transition (active -> active): must not trigger
    await store.update_status(goal["id"], "active")
    assert persist_mock.await_count == 0

    # Real transition (active -> achieved): trigger once
    updated = await store.update_status(goal["id"], "achieved")
    assert updated is not None
    assert updated["status"] == "achieved"
    persist_mock.assert_awaited_once()
    persisted_goal = persist_mock.await_args.args[0]
    assert persisted_goal["id"] == goal["id"]

    # Idempotent call (achieved -> achieved): must not trigger again
    await store.update_status(goal["id"], "achieved")
    assert persist_mock.await_count == 1


@pytest.mark.asyncio
async def test_persist_goal_resolution_stores_semantic_and_sends_telegram(monkeypatch):
    stored_calls: list[dict] = []

    class DummySemanticStore:
        async def store(self, *, content: str, tags: list[str] | None = None, salience: float = 0.7):
            stored_calls.append({"content": content, "tags": tags or [], "salience": salience})
            return None

    notify_mock = AsyncMock(return_value=2)

    monkeypatch.setattr("echo.memory.semantic.SemanticMemoryStore", DummySemanticStore)
    monkeypatch.setattr("echo.integrations.send_goal_resolution_notification", notify_mock)

    goal = {
        "id": "goal-xyz-987",
        "title": "Deliver consolidated goal memory",
        "description": "Store why + findings + solution and notify Telegram.",
        "priority": 0.9,
        "status": "achieved",
        "tags": ["goals", "memory"],
        "actions": [
            {
                "description": "Design centralized hook",
                "result": "Hook placed in GoalStore.update_status for achieved transitions.",
                "status": "done",
            },
            {
                "description": "Implement telegram notifier",
                "result": "Broadcasts goal/why/solution summary to allowed chats.",
                "status": "done",
            },
        ],
    }

    await _persist_goal_resolution(goal)

    assert len(stored_calls) == 1
    stored = stored_calls[0]
    assert "[Goal Resolution Report]" in stored["content"]
    assert "goal_achieved" in stored["tags"]
    assert "goal_resolution" in stored["tags"]
    assert stored["salience"] >= 0.7

    notify_mock.assert_awaited_once()
    kwargs = notify_mock.await_args.kwargs
    assert kwargs["goal_title"] == "Deliver consolidated goal memory"
    assert "why" not in kwargs  # keyword names are explicit and stable
    assert "why_chosen" in kwargs
    assert "solution_summary" in kwargs
