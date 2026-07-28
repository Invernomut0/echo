"""Security regression tests for the self-modification subsystem.

ECHO rewrites its own source, and the file paths involved originate from LLM
output. Any shell/interpreter interpolation on those paths is therefore an
injection vector reachable by the model itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from echo.self_modification.git_ops import validate_python


@pytest.mark.asyncio
async def test_valid_file_passes(tmp_path: Path) -> None:
    target = tmp_path / "ok.py"
    target.write_text("x = 1\n", encoding="utf-8")

    ok, err = await validate_python(str(target))

    assert ok is True
    assert err == ""


@pytest.mark.asyncio
async def test_syntax_error_is_reported(tmp_path: Path) -> None:
    target = tmp_path / "broken.py"
    target.write_text("def (:\n", encoding="utf-8")

    ok, err = await validate_python(str(target))

    assert ok is False
    assert "SyntaxError" in err


@pytest.mark.asyncio
async def test_quote_in_path_cannot_inject_code(tmp_path: Path) -> None:
    """A path crafted to break out of the source string must not execute.

    Verified against the previous f-string implementation, this payload made
    validation report success *and* ran ``touch``: the empty target file makes
    ``.read()`` falsy, so the ``or`` chain reaches the injected call.
    """
    target = tmp_path / "empty_target.py"
    target.write_text("", encoding="utf-8")
    marker = tmp_path / "pwned"

    payload = (
        f"{target}').read() or __import__('os').system('touch {marker}') or open('{target}"
    )

    ok, err = await validate_python(payload)

    assert not marker.exists(), "injected command executed — path is still interpolated"
    assert ok is False, "injected payload was accepted instead of being treated as a path"
    assert err


@pytest.mark.asyncio
async def test_missing_file_fails_cleanly(tmp_path: Path) -> None:
    ok, err = await validate_python(str(tmp_path / "does_not_exist.py"))

    assert ok is False
    assert err
