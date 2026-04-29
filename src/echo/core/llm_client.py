"""Async LLM client — routes to LM Studio or GitHub Copilot depending on settings."""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from echo.core.config import settings

logger = logging.getLogger(__name__)

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
        if settings.llm_provider == "copilot":
            return await self._copilot_chat(
                messages, temperature=temperature, max_tokens=max_tokens, model=model
            )
        response = await self._client.chat.completions.create(
            model=model or self.model,
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
        if settings.llm_provider == "copilot":
            async for delta in self._copilot_stream_chat(
                messages, temperature=temperature, max_tokens=max_tokens, model=model
            ):
                yield delta
            return

        stream = await self._client.chat.completions.create(
            model=model or self.model,
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

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors.

        Priority:
        1. LM Studio (local, fast, no rate-limit)
        2. HuggingFace free Inference API (cloud fallback, rate-limited)
        3. Empty list — callers handle graceful degradation
        """
        if not texts:
            return []
        # ── 1. Try LM Studio ──────────────────────────────────────────────────
        try:
            response = await self._client.embeddings.create(
                model=self.embedding_model, input=texts
            )
            return [item.embedding for item in response.data]
        except Exception as exc:  # noqa: BLE001
            logger.info("LM Studio embedding unavailable (%s) — trying HuggingFace fallback", exc)
        # ── 2. Try HuggingFace free API ───────────────────────────────────────
        vectors = await self._hf_embed(texts)
        if vectors:
            return vectors
        # ── 3. Complete degradation ───────────────────────────────────────────
        logger.warning("All embedding backends unavailable — returning empty vectors")
        return []

    async def embed_one(self, text: str) -> list[float]:
        vectors = await self.embed([text])
        return vectors[0] if vectors else []

    # ── Health check ───────────────────────────────────────────────────────────

    async def is_available(self) -> bool:
        if settings.llm_provider == "copilot":
            try:
                from echo.api.routers.setup import _get_copilot_token_cached  # noqa: PLC0415
                await _get_copilot_token_cached()
                return True
            except Exception:  # noqa: BLE001
                return False
        try:
            await self._client.models.list()
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

        # OpenAI-compatible path (LM Studio)
        self._last_tools_used = []
        current_messages = list(messages)
        for _round in range(max_tool_rounds):
            response = await self._client.chat.completions.create(
                model=model or self.model,
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
        - When tools *are* connected: runs the full agentic tool-call loop via
          ``chat_with_tools()`` and yields the complete final answer as a single
          chunk.  Streaming is sacrificed to support the tool-call round-trip,
          which is an acceptable tradeoff — the user is waiting for real data.

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

        # Tools available — run the agentic loop and yield the complete answer.
        # The non-streaming call is necessary because we need to inspect the
        # assistant message for ``tool_calls`` before continuing.
        result = await self.chat_with_tools(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            max_tool_rounds=max_tool_rounds,
            model=model,
        )
        yield result


# Module-level singleton
llm: LLMClient = LLMClient()
