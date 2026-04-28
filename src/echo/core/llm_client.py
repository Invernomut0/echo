"""Async LM Studio client (OpenAI-compatible API)."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from echo.core.config import settings

logger = logging.getLogger(__name__)

# Shared async HTTP client (reused across requests)
_http_client = httpx.AsyncClient(timeout=120.0)


def _build_openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=settings.lm_studio_base_url,
        api_key=settings.lm_studio_api_key,
        http_client=_http_client,
    )


class LLMClient:
    """Thin async wrapper around the OpenAI-compatible LM Studio API."""

    def __init__(self) -> None:
        self._client = _build_openai_client()
        self.model = settings.lm_studio_model
        self.embedding_model = settings.lm_studio_embedding_model

    # ------------------------------------------------------------------
    # Chat completions
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        model: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        """Single-turn chat completion. Returns the assistant message content."""
        response = await self._client.chat.completions.create(
            model=model or self.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
            **(extra or {}),
        )
        content = response.choices[0].message.content or ""
        logger.debug("chat() → %d chars", len(content))
        return content

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        model: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Streaming chat completion — yields text deltas."""
        stream = await self._client.chat.completions.create(
            model=model or self.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns a list of float vectors."""
        if not texts:
            return []
        response = await self._client.embeddings.create(
            model=self.embedding_model,
            input=texts,
        )
        return [item.embedding for item in response.data]

    async def embed_one(self, text: str) -> list[float]:
        """Convenience wrapper for a single text."""
        vectors = await self.embed([text])
        return vectors[0]

    # ------------------------------------------------------------------
    # Health / availability
    # ------------------------------------------------------------------

    async def is_available(self) -> bool:
        """Returns True if LM Studio responds to a models list request."""
        try:
            await self._client.models.list()
            return True
        except Exception:  # noqa: BLE001
            return False

    async def aclose(self) -> None:
        await _http_client.aclose()


# Module-level singleton
llm: LLMClient = LLMClient()
