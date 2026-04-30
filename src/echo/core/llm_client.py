"""Async LLM client — routes to LM Studio, GitHub Copilot, OpenAI, Groq, Anthropic or Ollama."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sys
import time
from collections import OrderedDict
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from echo.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Embedding LRU cache
# ---------------------------------------------------------------------------

class _EmbedCache:
    """Thread-safe LRU cache for embedding vectors with TTL expiry.

    On slow hardware (e.g. a phone acting as LM Studio server) a single
    embed call can take 30-40 s.  Caching avoids repeated calls for the
    same text within a conversation session.

    Parameters
    ----------
    max_size:
        Maximum number of entries.  Oldest are evicted when full.
    ttl_seconds:
        Time-to-live; stale entries are silently dropped on next access.
        Default 300 s (5 min) — vectors don't change for the same text.
    """

    def __init__(self, max_size: int = 256, ttl_seconds: float = 300.0) -> None:
        # {md5_key: (vector, monotonic_timestamp)}
        self._cache: OrderedDict[str, tuple[list[float], float]] = OrderedDict()
        self.max_size = max_size
        self.ttl = ttl_seconds
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()

    def get(self, text: str) -> list[float] | None:
        key = self._key(text)
        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None
        vector, ts = entry
        if time.monotonic() - ts > self.ttl:
            del self._cache[key]
            self._misses += 1
            return None
        # Move to end → recently-used
        self._cache.move_to_end(key)
        self._hits += 1
        return vector

    def put(self, text: str, vector: list[float]) -> None:
        if not vector:
            return
        key = self._key(text)
        self._cache[key] = (vector, time.monotonic())
        self._cache.move_to_end(key)
        # Evict oldest entries when over capacity
        while len(self._cache) > self.max_size:
            self._cache.popitem(last=False)

    @property
    def stats(self) -> dict[str, int]:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "ratio": round(self._hits / total, 3) if total else 0,
            "size": len(self._cache),
        }


# Shared async HTTP client (reused across requests)
_http_client = httpx.AsyncClient(timeout=120.0)

# Headers required by the GitHub Copilot completions API
_COPILOT_HEADERS: dict[str, str] = {
    "Content-Type": "application/json",
    "Editor-Version": "vscode/1.99.3",
    "Editor-Plugin-Version": "copilot-chat/0.22.4",
    "User-Agent": "GitHubCopilotChat/0.22.4",
    "Copilot-Integration-Id": "vscode-chat",
}


def _build_openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=settings.lm_studio_base_url,
        api_key=settings.lm_studio_api_key,
        http_client=_http_client,
    )


def _build_provider_client() -> AsyncOpenAI:
    """Build an OpenAI-compatible async client for the currently selected provider."""
    p = settings.llm_provider
    if p == "openai":
        return AsyncOpenAI(
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key or "sk-none",
            http_client=_http_client,
        )
    if p == "groq":
        return AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=settings.groq_api_key or "gsk-none",
            http_client=_http_client,
        )
    if p == "ollama":
        return AsyncOpenAI(
            base_url=f"{settings.ollama_base_url}/v1",
            api_key="ollama",
            http_client=_http_client,
        )
    # lm_studio or fallback
    return _build_openai_client()


def _provider_model() -> str:
    """Return the model name for the currently selected provider."""
    p = settings.llm_provider
    if p == "openai":
        return settings.openai_model
    if p == "groq":
        return settings.groq_model
    if p == "ollama":
        return settings.ollama_chat_model
    if p == "copilot":
        return settings.copilot_model
    return settings.lm_studio_model


def _clear_copilot_token_cache() -> None:
    """Force the next Copilot call to fetch a fresh token (called after a 401)."""
    m = sys.modules.get("echo.api.routers.setup")
    if m is not None:
        m._copilot_token_cache.clear()


class LLMClient:
    def __init__(self) -> None:
        self._client = _build_openai_client()
        self.model = settings.lm_studio_model
        self.embedding_model = settings.lm_studio_embedding_model
        self._last_tools_used: list[str] = []
        self._embed_cache = _EmbedCache(max_size=256, ttl_seconds=300.0)

    # ── Anthropic helpers ──────────────────────────────────────────────────────

    async def _anthropic_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        model: str | None = None,
    ) -> str:
        """Non-streaming chat via the Anthropic Messages API."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model or settings.anthropic_model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": messages,
                },
            )
        r.raise_for_status()
        data = r.json()
        return data["content"][0]["text"] if data.get("content") else ""

    async def _anthropic_stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        model: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Streaming chat via the Anthropic Messages API (SSE)."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model or settings.anthropic_model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": messages,
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:].strip()
                    if payload in ("[DONE]", ""):
                        continue
                    try:
                        chunk = json.loads(payload)
                        if chunk.get("type") == "content_block_delta":
                            delta = chunk.get("delta", {}).get("text", "")
                            if delta:
                                yield delta
                    except Exception:  # noqa: BLE001
                        pass

    # ── Copilot helpers ────────────────────────────────────────────────────────

    async def _copilot_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        model: str | None = None,
    ) -> str:
        """Non-streaming chat via the GitHub Copilot API."""
        # Late import keeps core modules free of router dependencies at load time.
        from echo.api.routers.setup import _get_copilot_token_cached  # noqa: PLC0415

        token_data = await _get_copilot_token_cached()
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                f"{token_data['endpoint']}/chat/completions",
                headers={
                    **_COPILOT_HEADERS,
                    "Authorization": f"Bearer {token_data['token']}",
                },
                json={
                    "model": model or settings.copilot_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
        if r.status_code == 401:
            _clear_copilot_token_cache()
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"] or ""

    async def _copilot_stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        model: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Streaming chat via the GitHub Copilot API (Server-Sent Events)."""
        from echo.api.routers.setup import _get_copilot_token_cached  # noqa: PLC0415

        token_data = await _get_copilot_token_cached()
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{token_data['endpoint']}/chat/completions",
                headers={
                    **_COPILOT_HEADERS,
                    "Authorization": f"Bearer {token_data['token']}",
                },
                json={
                    "model": model or settings.copilot_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": True,
                },
            ) as response:
                if response.status_code == 401:
                    _clear_copilot_token_cache()
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                        delta = chunk["choices"][0]["delta"].get("content")
                        if delta:
                            yield delta
                    except Exception:  # noqa: BLE001
                        pass

    # ── Chat completions ───────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        model: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        p = settings.llm_provider
        if p == "copilot":
            return await self._copilot_chat(
                messages, temperature=temperature, max_tokens=max_tokens, model=model
            )
        if p == "anthropic":
            return await self._anthropic_chat(
                messages, temperature=temperature, max_tokens=max_tokens, model=model
            )
        # OpenAI-compatible providers (lm_studio, openai, groq, ollama)
        client = _build_provider_client()
        response = await client.chat.completions.create(
            model=model or _provider_model(),
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **(extra or {}),
        )
        return response.choices[0].message.content or ""

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        model: str | None = None,
    ) -> AsyncGenerator[str, None]:
        p = settings.llm_provider
        if p == "copilot":
            async for delta in self._copilot_stream_chat(
                messages, temperature=temperature, max_tokens=max_tokens, model=model
            ):
                yield delta
            return
        if p == "anthropic":
            async for delta in self._anthropic_stream_chat(
                messages, temperature=temperature, max_tokens=max_tokens, model=model
            ):
                yield delta
            return

        # OpenAI-compatible providers (lm_studio, openai, groq, ollama)
        client = _build_provider_client()
        stream = await client.chat.completions.create(
            model=model or _provider_model(),
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    # ── Embeddings (LM Studio primary, HuggingFace fallback) ──────────────────

    # New router URL (updated May 2025 — old api-inference.huggingface.co paths return 404)
    # https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/discussions/116
    _HF_EMBED_URL = (
        "https://router.huggingface.co/hf-inference/models/{model}/pipeline/feature-extraction"
    )

    async def _hf_embed(self, texts: list[str]) -> list[list[float]]:
        """Call HuggingFace Inference API for embeddings.

        Uses the current router endpoint (updated May 2025):
          POST https://router.huggingface.co/hf-inference/models/{model}/pipeline/feature-extraction
          Body: {"inputs": ["text1", "text2", ...]}
          Response: [[float, ...], ...]  — one vector per input

        A fresh httpx.AsyncClient is created per call to avoid event-loop
        conflicts when running under pytest-asyncio.

        Requires HF_TOKEN in .env (free token at huggingface.co/settings/tokens).
        Returns a list of float vectors, or [] if the call fails.
        """
        if not settings.hf_token:
            logger.info(
                "HuggingFace fallback skipped -- set HF_TOKEN in .env "
                "(free token at huggingface.co/settings/tokens)"
            )
            return []

        url = self._HF_EMBED_URL.format(model=settings.hf_embedding_model)
        headers = {
            "Authorization": f"Bearer {settings.hf_token}",
            "Content-Type": "application/json",
        }

        try:
            # Fresh client per call — avoids "Event loop is closed" in pytest-asyncio
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    json={"inputs": texts},
                    headers=headers,
                    timeout=60.0,
                )
                resp.raise_for_status()
                data = resp.json()

            # Response: [[float, ...], [float, ...]] — one vector per input
            if (
                isinstance(data, list)
                and len(data) == len(texts)
                and isinstance(data[0], list)
            ):
                return data  # type: ignore[return-value]

            logger.warning(
                "HuggingFace: unexpected response shape %s — %s",
                type(data).__name__, str(data)[:200],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "HuggingFace embed fallback failed (%s: %s)",
                type(exc).__name__, exc,
            )
        return []

    # paraphrase-multilingual-mpnet-base-v2 has a 512-token context limit.
    # ~4 chars/token → 512 tokens ≈ 2048 chars; cap at 1800 for safety.
    _EMBED_MAX_CHARS: int = 1800

    async def _ollama_embed(self, texts: list[str]) -> list[list[float]]:
        """Call Ollama /api/embed for batch embeddings (v0.3.6+ endpoint).

        POST http://localhost:11434/api/embed
        Body: {"model": "<name>", "input": ["text1", "text2", ...]}
        Response: {"embeddings": [[float, ...], ...]}

        Timeout: 60 s — generous; first call may need to load model into RAM.
        Texts longer than _EMBED_MAX_CHARS are truncated to avoid Ollama's
        "input length exceeds the context length" error.
        """
        truncated = [t[: self._EMBED_MAX_CHARS] for t in texts]
        url = f"{settings.ollama_base_url}/api/embed"
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    url,
                    json={"model": settings.ollama_embedding_model, "input": truncated},
                )
                resp.raise_for_status()
                data = resp.json()
            embeddings = data.get("embeddings", [])
            if embeddings and len(embeddings) == len(texts):
                return embeddings
            logger.warning(
                "Ollama embed: unexpected response shape — %s", str(data)[:200]
            )
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "Ollama embedding unavailable (%s: %s)", type(exc).__name__, exc
            )
        return []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors.

        Priority:
        1. Ollama /api/embed (local daemon, ~20-100 ms, no Python deps)
        2. LM Studio embedding API (local network, requires LM Studio running)
        3. HuggingFace Inference API (cloud fallback, rate-limited)
        4. Empty list — callers handle graceful degradation
        """
        if not texts:
            return []
        # ── 1. Ollama ─────────────────────────────────────────────────────────
        vectors = await self._ollama_embed(texts)
        if vectors:
            return vectors
        # ── 2. LM Studio ──────────────────────────────────────────────────────
        try:
            response = await self._client.embeddings.create(
                model=self.embedding_model, input=texts
            )
            return [item.embedding for item in response.data]
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "LM Studio embedding unavailable (%s) — trying HuggingFace fallback",
                exc,
            )
        # ── 3. HuggingFace cloud ──────────────────────────────────────────────
        vectors = await self._hf_embed(texts)
        if vectors:
            return vectors
        # ── 4. Complete degradation ───────────────────────────────────────────
        logger.warning("All embedding backends unavailable — returning empty vectors")
        return []

    async def embed_one(self, text: str) -> list[float]:
        """Return the embedding vector for *text*, using the in-process cache.

        On a cache hit (same text within the TTL window) this returns in
        microseconds instead of making an LM Studio HTTP round-trip.
        """
        cached = self._embed_cache.get(text)
        if cached is not None:
            logger.debug("embed cache hit — %s", self._embed_cache.stats)
            return cached
        vectors = await self.embed([text])
        result = vectors[0] if vectors else []
        self._embed_cache.put(text, result)
        return result

    # ── Health check ───────────────────────────────────────────────────────────

    async def is_available(self) -> bool:
        p = settings.llm_provider
        if p == "copilot":
            try:
                from echo.api.routers.setup import _get_copilot_token_cached  # noqa: PLC0415
                await _get_copilot_token_cached()
                return True
            except Exception:  # noqa: BLE001
                return False
        if p == "anthropic":
            try:
                # Light probe: list models endpoint
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.get(
                        "https://api.anthropic.com/v1/models",
                        headers={"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01"},
                    )
                return r.status_code == 200
            except Exception:  # noqa: BLE001
                return False
        try:
            client = _build_provider_client()
            await client.models.list()
            return True
        except Exception:  # noqa: BLE001
            return False

    async def aclose(self) -> None:
        await _http_client.aclose()

    # ── Tool-augmented chat (MCP integration) ─────────────────────────────────

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        max_tool_rounds: int = 8,
        model: str | None = None,
    ) -> str:
        """Agentic chat loop with MCP tool-calling.

        Feeds ``messages`` to the LLM together with all tools currently
        available via the MCP manager.  If the model requests a tool call the
        manager executes it and the result is appended to the conversation;
        the loop continues until the model produces a plain-text reply (no
        more tool calls) or ``max_tool_rounds`` is exceeded.

        Falls back silently to plain ``chat()`` when no MCP tools are
        available or when the active provider does not support function
        calling.
        """
        # Late import to avoid circular deps at module load time
        from echo.mcp import mcp_manager  # noqa: PLC0415

        tools = mcp_manager.list_tools_openai()
        if not tools:
            # No tools available — plain chat
            return await self.chat(messages, temperature=temperature, max_tokens=max_tokens, model=model)

        if settings.llm_provider == "copilot":
            # Copilot path: manual tool-call loop via raw HTTP
            return await self._copilot_chat_with_tools(
                messages, tools, mcp_manager,
                temperature=temperature, max_tokens=max_tokens,
                max_rounds=max_tool_rounds, model=model,
            )

        if settings.llm_provider == "anthropic":
            # Anthropic doesn't support OpenAI tool format — fall back to plain chat
            return await self.chat(messages, temperature=temperature, max_tokens=max_tokens, model=model)

        # OpenAI-compatible providers (lm_studio, openai, groq, ollama)
        self._last_tools_used = []
        current_messages = list(messages)
        client = _build_provider_client()
        for _round in range(max_tool_rounds):
            response = await client.chat.completions.create(
                model=model or _provider_model(),
                messages=current_messages,
                tools=tools,
                tool_choice="auto",
                temperature=temperature,
                max_tokens=max_tokens,
            )
            msg = response.choices[0].message

            # No tool calls → we have the final answer
            if not msg.tool_calls:
                return msg.content or ""

            # Append the assistant message (with tool_calls) to history
            current_messages.append(msg.model_dump(exclude_none=True))

            # Execute each requested tool and append results
            for tc in msg.tool_calls:
                fn_name: str = tc.function.name
                if fn_name not in self._last_tools_used:
                    self._last_tools_used.append(fn_name)
                try:
                    fn_args: dict[str, Any] = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    fn_args = {}
                logger.info("[MCP] calling tool %s %s", fn_name, fn_args)
                tool_result = await mcp_manager.call_tool(fn_name, fn_args)
                current_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result,
                })

        # Fallback: final plain call after exhausting rounds
        logger.warning("[MCP] max tool rounds (%d) reached — final plain call", max_tool_rounds)
        return await self.chat(current_messages, temperature=temperature, max_tokens=max_tokens, model=model)

    async def _copilot_chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        mcp_manager: Any,
        *,
        temperature: float,
        max_tokens: int,
        max_rounds: int,
        model: str | None,
    ) -> str:
        """Tool-calling loop through the GitHub Copilot API."""
        from echo.api.routers.setup import _get_copilot_token_cached  # noqa: PLC0415

        self._last_tools_used = []
        current_messages = list(messages)
        for _round in range(max_rounds):
            token_data = await _get_copilot_token_cached()
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.post(
                    f"{token_data['endpoint']}/chat/completions",
                    headers={
                        **_COPILOT_HEADERS,
                        "Authorization": f"Bearer {token_data['token']}",
                    },
                    json={
                        "model": model or settings.copilot_model,
                        "messages": current_messages,
                        "tools": tools,
                        "tool_choice": "auto",
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
            if r.status_code == 401:
                _clear_copilot_token_cache()
            r.raise_for_status()
            data = r.json()
            msg = data["choices"][0]["message"]
            tool_calls = msg.get("tool_calls")

            if not tool_calls:
                return msg.get("content") or ""

            current_messages.append(msg)
            for tc in tool_calls:
                fn_name: str = tc["function"]["name"]
                if fn_name not in self._last_tools_used:
                    self._last_tools_used.append(fn_name)
                try:
                    fn_args: dict[str, Any] = json.loads(tc["function"].get("arguments", "{}"))
                except json.JSONDecodeError:
                    fn_args = {}
                logger.info("[MCP] calling tool %s %s", fn_name, fn_args)
                tool_result = await mcp_manager.call_tool(fn_name, fn_args)
                current_messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result,
                })

        logger.warning("[MCP] Copilot max tool rounds (%d) reached", max_rounds)
        return await self._copilot_chat(current_messages, temperature=temperature, max_tokens=max_tokens, model=model)

    # ── Streaming chat with MCP tools ─────────────────────────────────────────

    async def stream_chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        max_tool_rounds: int = 8,
        model: str | None = None,
    ):
        """Streaming chat with MCP tool support.

        Behaviour:
        - When *no* MCP tools are connected: falls back to ``stream_chat`` (true
          token-by-token streaming, no overhead).
        - When tools *are* connected: runs tool-call round-trips non-streaming
          (necessary to inspect tool_calls in the response), then streams the
          **final** answer token-by-token once all tools have been executed.

        This is an ``AsyncGenerator[str, None]`` so callers can use it with
        ``async for delta in llm.stream_chat_with_tools(...)`` in the same way
        they use ``stream_chat``.
        """
        from echo.mcp import mcp_manager  # noqa: PLC0415

        tools = mcp_manager.list_tools_openai()
        if not tools:
            # No MCP tools available — pure streaming path (no overhead)
            async for delta in self.stream_chat(
                messages, temperature=temperature, max_tokens=max_tokens, model=model
            ):
                yield delta
            return

        # ── Tool-call loop (non-streaming round-trips) ─────────────────────
        # Run until the model stops requesting tools, then stream the final answer.

        if settings.llm_provider == "copilot":
            final_messages = await self._copilot_tool_rounds(
                messages, tools, mcp_manager,
                temperature=temperature, max_tokens=max_tokens,
                max_rounds=max_tool_rounds, model=model,
            )
        elif settings.llm_provider == "anthropic":
            # Anthropic doesn't support OpenAI tool format — stream directly
            async for delta in self.stream_chat(
                messages, temperature=temperature, max_tokens=max_tokens, model=model
            ):
                yield delta
            return
        else:
            final_messages = await self._openai_tool_rounds(
                messages, tools, mcp_manager,
                temperature=temperature, max_tokens=max_tokens,
                max_rounds=max_tool_rounds, model=model,
            )

        # ── Stream the final answer ────────────────────────────────────────
        async for delta in self.stream_chat(
            final_messages, temperature=temperature, max_tokens=max_tokens, model=model
        ):
            yield delta

    async def _openai_tool_rounds(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        mcp_manager: Any,
        *,
        temperature: float,
        max_tokens: int,
        max_rounds: int,
        model: str | None,
    ) -> list[dict[str, Any]]:
        """Run OpenAI-compatible tool-call rounds. Returns messages ready for final streaming."""
        self._last_tools_used = []
        current_messages = list(messages)
        client = _build_provider_client()
        for _round in range(max_rounds):
            response = await client.chat.completions.create(
                model=model or _provider_model(),
                messages=current_messages,
                tools=tools,
                tool_choice="auto",
                temperature=temperature,
                max_tokens=max_tokens,
            )
            msg = response.choices[0].message

            # No tool calls → context is ready for final streaming call
            if not msg.tool_calls:
                return current_messages

            current_messages.append(msg.model_dump(exclude_none=True))
            for tc in msg.tool_calls:
                fn_name: str = tc.function.name
                if fn_name not in self._last_tools_used:
                    self._last_tools_used.append(fn_name)
                try:
                    fn_args: dict[str, Any] = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    fn_args = {}
                logger.info("[MCP] calling tool %s %s", fn_name, fn_args)
                tool_result = await mcp_manager.call_tool(fn_name, fn_args)
                current_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result,
                })

        logger.warning("[MCP] max tool rounds (%d) reached", max_rounds)
        return current_messages

    async def _copilot_tool_rounds(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        mcp_manager: Any,
        *,
        temperature: float,
        max_tokens: int,
        max_rounds: int,
        model: str | None,
    ) -> list[dict[str, Any]]:
        """Run Copilot tool-call rounds. Returns messages ready for final streaming."""
        from echo.api.routers.setup import _get_copilot_token_cached  # noqa: PLC0415

        self._last_tools_used = []
        current_messages = list(messages)
        for _round in range(max_rounds):
            token_data = await _get_copilot_token_cached()
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.post(
                    f"{token_data['endpoint']}/chat/completions",
                    headers={**_COPILOT_HEADERS, "Authorization": f"Bearer {token_data['token']}"},
                    json={
                        "model": model or settings.copilot_model,
                        "messages": current_messages,
                        "tools": tools,
                        "tool_choice": "auto",
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
            if r.status_code == 401:
                _clear_copilot_token_cache()
            r.raise_for_status()
            data = r.json()
            msg = data["choices"][0]["message"]
            tool_calls = msg.get("tool_calls")

            if not tool_calls:
                return current_messages

            current_messages.append(msg)
            for tc in tool_calls:
                fn_name: str = tc["function"]["name"]
                if fn_name not in self._last_tools_used:
                    self._last_tools_used.append(fn_name)
                try:
                    fn_args: dict[str, Any] = json.loads(tc["function"].get("arguments", "{}"))
                except json.JSONDecodeError:
                    fn_args = {}
                logger.info("[MCP] calling tool %s %s", fn_name, fn_args)
                tool_result = await mcp_manager.call_tool(fn_name, fn_args)
                current_messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result,
                })

        logger.warning("[MCP] Copilot max tool rounds (%d) reached", max_rounds)
        return current_messages


# Module-level singleton
llm: LLMClient = LLMClient()
