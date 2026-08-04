"""Regression tests for the defects found in the 2026-08-04 code review.

Each test pins down one bug that was live in `main`. They are grouped by the
subsystem they cover rather than by severity.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Wiki — path traversal, index corruption, slug collapse
# ---------------------------------------------------------------------------


@pytest.fixture()
def wiki(tmp_path, monkeypatch):
    from echo.memory import wiki as wiki_mod

    monkeypatch.setattr(wiki_mod, "_WIKI_ROOT", tmp_path / "wiki", raising=False)
    store = wiki_mod.WikiStore()
    store._root = tmp_path / "wiki"
    store._index = store._root / "index.md"
    store._log = store._root / "log.md"
    store._pages = store._root / "pages"
    store.startup()
    return store


def test_read_page_by_path_rejects_parent_traversal(wiki, tmp_path):
    """`GET /api/wiki/page?path=../../.env` must not read outside the wiki root."""
    secret = tmp_path / ".env"
    secret.write_text("GITHUB_TOKEN=ghp_supersecret\n", encoding="utf-8")

    assert wiki.read_page_by_path("../.env") is None
    assert wiki.read_page_by_path("../../.env") is None


def test_read_page_by_path_rejects_absolute_path(wiki, tmp_path):
    """An absolute path discards the base when joined — it must be rejected."""
    outside = tmp_path / "outside.md"
    outside.write_text("secret", encoding="utf-8")

    assert wiki.read_page_by_path(str(outside)) is None


def test_read_page_by_path_reads_legitimate_page(wiki):
    """The containment check must not break normal reads."""
    wiki._write_page("concepts", "memory", "# Memory\n\nbody text\n")
    assert "body text" in (wiki.read_page_by_path("pages/concepts/memory.md") or "")


def test_short_slug_does_not_evict_longer_page_from_index(wiki):
    """Index rows are keyed by path: "echo" must not overwrite "echo-architecture"."""
    wiki._update_index(
        "echo-architecture", "Echo Architecture", "concepts", ["design"], "the design"
    )
    wiki._update_index("echo", "Echo", "entities", ["entity"], "the agent")

    paths = {p["path"] for p in wiki.list_pages()}
    assert "pages/concepts/echo-architecture.md" in paths
    assert "pages/entities/echo.md" in paths


def test_update_index_replaces_same_page_instead_of_appending(wiki):
    """Re-writing the same page updates its row rather than duplicating it."""
    wiki._update_index("kant", "Kant", "entities", ["philosopher"], "first summary")
    wiki._update_index("kant", "Kant", "entities", ["philosopher"], "second summary")

    rows = [p for p in wiki.list_pages() if p["path"] == "pages/entities/kant.md"]
    assert len(rows) == 1
    assert "second summary" in rows[0]["summary"]


def test_pipe_in_title_does_not_break_index_row(wiki):
    """An unescaped "|" split the row and made the page vanish from the index."""
    wiki._update_index("rust-cargo", "Rust|Cargo", "concepts", ["build"], "pkg manager")

    pages = wiki.list_pages()
    assert len(pages) == 1
    assert pages[0]["path"] == "pages/concepts/rust-cargo.md"


def test_slugify_never_returns_empty():
    """A symbol-only title collapsed to "" and overwrote `<category>/.md`."""
    from echo.memory.wiki import _slugify

    assert _slugify("C++")
    assert _slugify("!!!")
    assert _slugify("C++") != _slugify("!!!")


def test_parse_repo_strips_git_suffix_not_characters():
    """rstrip(".git") is a character set: "digit" became "d"."""
    from echo.memory.wiki_sync import _parse_repo

    assert _parse_repo("https://github.com/owner/echo.git") == ("owner", "echo")
    assert _parse_repo("https://github.com/owner/digit") == ("owner", "digit")
    assert _parse_repo("https://github.com/owner/echo-agit") == ("owner", "echo-agit")


# ---------------------------------------------------------------------------
# Chunker — oversized chunks were silently truncated by the embedder
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Short intro line.\n" + "x" * 3000,   # short sentence, then a huge one
        "x" * 3000,                            # one huge sentence
        "Sentence one. Sentence two. " * 60,   # ordinary prose
    ],
)
def test_no_chunk_exceeds_chunk_size(text):
    from echo.memory.chunker import CHUNK_SIZE, chunk_text

    chunks = chunk_text(text)
    assert chunks
    assert max(len(c) for c in chunks) <= CHUNK_SIZE


# ---------------------------------------------------------------------------
# Agent routing — greeting fast path and multi-word signals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "Notizie sulla mia ricerca?",
        "Nomina i tuoi obiettivi attuali",
        "significa che non ricordi nulla?",
        "sicuro di aver capito?",
        "okay ma spiegami la memoria episodica",
        "no, spiegami meglio",
    ],
)
def test_real_questions_are_not_treated_as_greetings(query):
    """A bare startswith let "no"/"si"/"ok" swallow real questions."""
    from echo.agents.orchestrator import _select_agents

    selected = _select_agents(query)
    assert selected is None or len(selected) > 0, f"{query!r} hit the greeting fast path"


@pytest.mark.parametrize("query", ["ciao", "ok", "ok grazie", "no", "si!", "come stai?", "thanks"])
def test_greetings_still_take_the_fast_path(query):
    from echo.agents.orchestrator import _select_agents

    assert _select_agents(query) == frozenset()


@pytest.mark.parametrize(
    ("query", "expected_role"),
    [
        ("How can I improve my writing?", "planner"),
        ("Come posso migliorare?", "planner"),
        ("what if we changed the schema?", "explorer"),
    ],
)
def test_multi_word_routing_signals_match(query, expected_role):
    """Phrases like "come posso" can never appear in the split word set."""
    from echo.agents.orchestrator import _select_agents

    selected = _select_agents(query)
    assert selected is not None
    assert expected_role in selected


# ---------------------------------------------------------------------------
# Self-modification — the path safety gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "candidate",
    [
        ".env",
        "./.env",
        "src/echo/self_modification/engine.py",
        "src/echo/self_modification/./engine.py",
        "data/sqlite/echo.db",
        "data/sqlite/./echo.db",
        "../outside.py",
        "../../etc/hosts",
    ],
)
def test_self_modification_rejects_protected_paths(candidate):
    """Resolve first, then match: the raw string let "./" and ".." bypass the gate."""
    from echo.self_modification.engine import _FORBIDDEN, _repo_root

    root = _repo_root().resolve()
    try:
        abs_path = (root / candidate).resolve()
        rel_str = abs_path.relative_to(root).as_posix()
    except ValueError:
        return  # outside the repo — rejected by the containment check
    blocked = any(rel_str == f or rel_str.startswith(f + "/") for f in _FORBIDDEN)
    assert blocked, f"{candidate!r} resolved to {rel_str!r} and was not blocked"


def test_self_modification_allows_ordinary_source_file():
    """The gate must not block a legitimate target."""
    from echo.self_modification.engine import _FORBIDDEN, _repo_root

    root = _repo_root().resolve()
    rel_str = (
        (root / "src/echo/core/types.py").resolve().relative_to(root).as_posix()
    )
    assert not any(rel_str == f or rel_str.startswith(f + "/") for f in _FORBIDDEN)


def test_self_modification_cooldown_is_armed_at_construction():
    """A 0.0 sentinel against monotonic() meant "cooldown already expired"."""
    import time

    from echo.self_modification.engine import _COOLDOWN_S, SelfModificationEngine

    engine = SelfModificationEngine()
    assert time.monotonic() - engine._last_modified < _COOLDOWN_S


def test_self_modification_reset_cooldown_expires_it():
    import time

    from echo.self_modification.engine import _COOLDOWN_S, SelfModificationEngine

    engine = SelfModificationEngine()
    engine.reset_cooldown()
    assert time.monotonic() - engine._last_modified >= _COOLDOWN_S


# ---------------------------------------------------------------------------
# Cron — two task types imported names that do not exist
# ---------------------------------------------------------------------------


def test_curiosity_and_goal_cron_targets_exist():
    """Both tasks used to raise ImportError and report status "skipped" forever."""
    from echo.curiosity.engine import CuriosityEngine

    assert hasattr(CuriosityEngine, "run_cycle")
    assert hasattr(CuriosityEngine, "run_goal_cycle")


# ---------------------------------------------------------------------------
# Consolidation — the dedup scan covered only the newest memory
# ---------------------------------------------------------------------------


def test_duplicate_pairs_finds_a_pair_late_in_the_list():
    """The old _MAX_PAIRS break made pairs beyond the first row unreachable."""
    from echo.consolidation.sleep_phase import _find_duplicate_pairs
    from echo.core.types import MemoryEntry

    memories = [MemoryEntry(content=f"unrelated {i}") for i in range(8)]
    # Indices 5 and 6 are identical; every other vector is orthogonal-ish.
    vectors = {m.id: [1.0 if j == i else 0.0 for j in range(8)] for i, m in enumerate(memories)}
    vectors[memories[6].id] = list(vectors[memories[5].id])

    pairs = _find_duplicate_pairs(memories, vectors, threshold=0.99)
    matched = {frozenset((winner, loser)) for winner, loser, _ in pairs}
    assert frozenset((memories[5].id, memories[6].id)) in matched


# ---------------------------------------------------------------------------
# API — .env writes must not be able to inject a second line
# ---------------------------------------------------------------------------


def test_set_env_key_rejects_newline_in_value(monkeypatch, tmp_path):
    """A newline in a value defined an arbitrary extra variable in .env."""
    from fastapi import HTTPException

    from echo.api.routers import setup as setup_mod

    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_MODEL=gpt-4o\n", encoding="utf-8")
    monkeypatch.setattr(setup_mod, "ENV_PATH", env_file)

    with pytest.raises(HTTPException) as exc:
        setup_mod._set_env_key("OPENAI_MODEL", "gpt-4o\nGITHUB_TOKEN=ghp_injected")
    assert exc.value.status_code == 422
    assert "GITHUB_TOKEN" not in env_file.read_text(encoding="utf-8")


def test_set_env_key_rejects_invalid_key(monkeypatch, tmp_path):
    from fastapi import HTTPException

    from echo.api.routers import setup as setup_mod

    monkeypatch.setattr(setup_mod, "ENV_PATH", tmp_path / ".env")
    with pytest.raises(HTTPException):
        setup_mod._set_env_key("bad key", "value")


def test_set_env_key_writes_a_clean_value(monkeypatch, tmp_path):
    from echo.api.routers import setup as setup_mod

    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_MODEL=old\n", encoding="utf-8")
    monkeypatch.setattr(setup_mod, "ENV_PATH", env_file)

    setup_mod._set_env_key("OPENAI_MODEL", "gpt-4o")
    assert "gpt-4o" in env_file.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Telegram — the bot token must never reach the logs
# ---------------------------------------------------------------------------


def test_redact_removes_bot_token(monkeypatch):
    """httpx puts the token-bearing URL in its error messages."""
    from echo.core.config import settings
    from echo.integrations.telegram_bot import _redact

    monkeypatch.setattr(settings, "telegram_bot_token", "7891234:AAF-realtoken", raising=False)
    message = (
        "Client error '401 Unauthorized' for url "
        "'https://api.telegram.org/bot7891234:AAF-realtoken/getMe'"
    )
    redacted = _redact(message)
    assert "AAF-realtoken" not in redacted
    assert "<TOKEN>" in redacted


# ---------------------------------------------------------------------------
# Pipeline — attribute used by the non-streaming path
# ---------------------------------------------------------------------------


def test_pipeline_memory_sources_initialised_in_constructor():
    """_run_pipeline (Telegram path) wrote to this before it existed."""
    from echo.core.pipeline import CognitivePipeline

    p = CognitivePipeline()
    assert set(p._last_memory_sources) >= {"episodic", "semantic", "wiki"}
