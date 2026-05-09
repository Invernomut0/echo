"""Tests for embedding stack — HuggingFace fallback and basic sanity checks.

Requires:
    - HF_TOKEN env var (or .env file at project root)
    - Network access to api.huggingface.co

Run with:
    uv run pytest tests/test_embeddings.py -v
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_hf_embed_direct() -> None:
    """HuggingFace endpoint returns a non-empty vector with expected model dimension."""
    from echo.core.config import settings
    from echo.core.llm_client import llm

    vectors = await llm._hf_embed(["The quick brown fox"])
    assert len(vectors) == 1, "Expected exactly one vector"
    dim = len(vectors[0])
    assert dim > 0, "Embedding vector is empty"

    model_name = settings.hf_embedding_model.lower()
    if "mpnet" in model_name:
        expected = 768
        assert dim == expected, f"{settings.hf_embedding_model} should produce {expected}-dim vectors, got {dim}"
    elif "minilm" in model_name:
        expected = 384
        assert dim == expected, f"{settings.hf_embedding_model} should produce {expected}-dim vectors, got {dim}"


@pytest.mark.asyncio
async def test_embed_one_fallback() -> None:
    """embed_one() must return a non-empty vector even when LM Studio is offline."""
    from echo.core.llm_client import llm

    vec = await llm.embed_one("hello world")
    assert len(vec) > 0, "embed_one() returned an empty vector — HF fallback failed"


@pytest.mark.asyncio
async def test_semantic_similarity_sanity() -> None:
    """'dog' should be more similar to 'cat' than to 'airplane'."""
    import numpy as np

    from echo.core.llm_client import llm

    vecs = await llm._hf_embed(["dog", "cat", "airplane"])
    assert len(vecs) == 3

    dog = np.array(vecs[0])
    cat = np.array(vecs[1])
    plane = np.array(vecs[2])

    def cosine(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    dog_cat = cosine(dog, cat)
    dog_plane = cosine(dog, plane)

    assert dog_cat > dog_plane, (
        f"Expected dog↔cat ({dog_cat:.4f}) > dog↔airplane ({dog_plane:.4f})"
    )
