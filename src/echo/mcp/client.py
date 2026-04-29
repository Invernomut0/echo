"""MCPClientManager — persistent connections to MCP servers.

Design
------
* Reads configuration from  ``data/mcp.json``  (see ``mcp.json.example``).
* Each server entry describes a *stdio* or *sse* (HTTP) transport.
* Connections are established at startup and kept alive; if a server dies
  the manager marks it as "disconnected" and re-tries on the next call.
* Tools are namespaced as  ``<server_name>__<tool_name>``  to avoid clashes.
* The manager exposes helpers that return tools in the *OpenAI function-call*
  format so they can be passed directly to ``LLMClient.chat_with_tools()``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default config path (relative to project root, i.e. where the server is run from)
_DEFAULT_CONFIG = Path("data/mcp.json")


# ---------------------------------------------------------------------------
# Config models (plain dataclasses, no Pydantic dep needed here)
# ---------------------------------------------------------------------------

@dataclass
class MCPServerConfig:
    name: str
    transport: str  # "stdio" | "sse"
    # stdio fields
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    # sse fields
    url: str = ""
    # common
    enabled: bool = True
    description: str = ""
    # user-configurable extra path (e.g. for filesystem server)
    user_path: str = ""
    user_path_mode: str = "read"  # "read" | "readwrite"
    # internal marker: auto-generated companion servers, not persisted to disk
    is_derived: bool = field(default=False, repr=False, compare=False)


@dataclass
class MCPToolDef:
    """Thin wrapper around an MCP tool with its server origin."""

    server_name: str
    name: str           # raw tool name from the server
    description: str
    input_schema: dict[str, Any]

    @property
    def qualified_name(self) -> str:
        """Unique name across all connected servers: ``<server>__<tool>``."""
        return f"{self.server_name}__{self.name}"

    def to_openai(self) -> dict[str, Any]:
        """Convert to OpenAI function-call tool dict."""
        return {
            "type": "function",
            "function": {
                "name": self.qualified_name,
                "description": f"[{self.server_name}] {self.description}",
                "parameters": self.input_schema or {"type": "object", "properties": {}},
            },
        }


@dataclass
class ServerStatus:
    name: str
    transport: str
    enabled: bool
    connected: bool
    error: str | None
    tool_count: int
    description: str
    user_path: str = ""
    user_path_mode: str = "read"
    is_derived: bool = False


# ---------------------------------------------------------------------------
# Internal connection wrapper
# ---------------------------------------------------------------------------

class _ServerConnection:
    """Holds one live MCP ClientSession (stdio or SSE)."""

    def __init__(self, cfg: MCPServerConfig) -> None:
        self.cfg = cfg
        self._session: Any = None          # mcp.ClientSession
        self._cm: Any = None               # the combined async context manager
        self._tools: list[MCPToolDef] = []
        self.connected: bool = False
        self.error: str | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the MCP session and cache the tool list."""
        try:
            await self._do_connect()
            self.connected = True
            self.error = None
            logger.info("[MCP] %s connected — %d tool(s)", self.cfg.name, len(self._tools))
        except Exception as exc:  # noqa: BLE001
            self.connected = False
            self.error = str(exc)
            logger.warning("[MCP] %s failed to connect: %s", self.cfg.name, exc)

    async def _do_connect(self) -> None:
        # Late-import so the module loads even if `mcp` is not installed yet
        from mcp import ClientSession  # type: ignore[import-untyped]

        if self.cfg.transport == "stdio":
            from mcp.client.stdio import StdioServerParameters, stdio_client  # type: ignore[import-untyped]

            # Start from the full process environment so the subprocess inherits
            # everything (including env vars loaded from .env by Pydantic settings).
            base_env = os.environ.copy()

            # Ensure common package-manager paths (npx, uvx, etc.) are reachable
            # even when the server is launched without the full interactive-shell PATH.
            _extra = "/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin"
            cur_path = base_env.get("PATH", "")
            if _extra not in cur_path:
                base_env["PATH"] = f"{_extra}:{cur_path}"

            # Only apply non-empty values from cfg.env so that placeholder entries
            # like {"BRAVE_API_KEY": ""} don't override the real value already
            # present in the process environment (loaded from .env).
            merged_env = {**base_env, **{k: v for k, v in self.cfg.env.items() if v}}

            params = StdioServerParameters(
                command=self.cfg.command,
                args=(
                    self.cfg.args + [self.cfg.user_path]
                    if self.cfg.user_path and self.cfg.user_path_mode == "readwrite"
                    else self.cfg.args
                ),
                env=merged_env,
            )
            self._cm = stdio_client(params)
            read_stream, write_stream = await self._cm.__aenter__()
        elif self.cfg.transport == "sse":
            from mcp.client.sse import sse_client  # type: ignore[import-untyped]

            self._cm = sse_client(url=self.cfg.url)
            read_stream, write_stream = await self._cm.__aenter__()
        else:
            raise ValueError(f"Unknown transport: {self.cfg.transport!r}")

        self._session = ClientSession(read_stream, write_stream)
        await self._session.__aenter__()
        await self._session.initialize()

        # Discover tools
        result = await self._session.list_tools()
        self._tools = [
            MCPToolDef(
                server_name=self.cfg.name,
                name=t.name,
                description=t.description or "",
                input_schema=t.inputSchema if isinstance(t.inputSchema, dict) else {},
            )
            for t in result.tools
        ]

    async def disconnect(self) -> None:
        """Close the MCP session cleanly."""
        try:
            if self._session is not None:
                await self._session.__aexit__(None, None, None)
            if self._cm is not None:
                await self._cm.__aexit__(None, None, None)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[MCP] %s disconnect error: %s", self.cfg.name, exc)
        finally:
            self._session = None
            self._cm = None
            self.connected = False

    # ------------------------------------------------------------------
    # Tool invocation
    # ------------------------------------------------------------------

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Call a tool on this server and return the text content."""
        async with self._lock:
            if not self.connected or self._session is None:
                # Try once to reconnect
                await self.disconnect()
                await self.connect()
                if not self.connected:
                    return f"[MCP ERROR] Server '{self.cfg.name}' is not connected: {self.error}"

            try:
                result = await self._session.call_tool(tool_name, arguments)
            except Exception as exc:  # noqa: BLE001
                # Mark as disconnected so next call retries
                self.connected = False
                self.error = str(exc)
                return f"[MCP ERROR] Tool call failed on '{self.cfg.name}': {exc}"

        # Extract text from the result content list
        parts: list[str] = []
        for item in result.content:
            if hasattr(item, "text"):
                parts.append(item.text)
            elif isinstance(item, dict):
                parts.append(item.get("text", json.dumps(item)))
        return "\n".join(parts) if parts else "(empty result)"

    @property
    def tools(self) -> list[MCPToolDef]:
        return self._tools


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class MCPClientManager:
    """Manages a pool of MCP server connections."""

    def __init__(self, config_path: Path = _DEFAULT_CONFIG) -> None:
        self._config_path = config_path
        self._all_configs: dict[str, MCPServerConfig] = {}  # ALL servers (enabled + disabled)
        self._connections: dict[str, _ServerConnection] = {}  # only active connections
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        """Load config and connect to all enabled servers."""
        configs = self._load_config()
        self._all_configs = {cfg.name: cfg for cfg in configs}
        for cfg in configs:
            if not cfg.enabled:
                logger.info("[MCP] %s skipped (disabled)", cfg.name)
                continue
            conn = _ServerConnection(cfg)
            self._connections[cfg.name] = conn
            # Connect in background so a slow server doesn't block ECHO startup
            asyncio.create_task(conn.connect(), name=f"mcp-connect-{cfg.name}")
        self._running = True
        logger.info("[MCP] Manager started with %d server(s)", len(self._connections))

    async def shutdown(self) -> None:
        """Close all server connections."""
        tasks = [conn.disconnect() for conn in self._connections.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._connections.clear()
        self._all_configs.clear()
        self._running = False
        logger.info("[MCP] Manager shut down")

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def _load_config(self) -> list[MCPServerConfig]:
        if not self._config_path.exists():
            logger.info("[MCP] Config not found at %s — no servers loaded", self._config_path)
            return []
        try:
            raw = json.loads(self._config_path.read_text())
        except Exception as exc:  # noqa: BLE001
            logger.error("[MCP] Failed to parse %s: %s", self._config_path, exc)
            return []

        configs: list[MCPServerConfig] = []
        for entry in raw.get("servers", []):
            try:
                user_path = entry.get("user_path", "")
                user_path_mode = entry.get("user_path_mode", "read")
                cfg = MCPServerConfig(
                    name=entry["name"],
                    transport=entry.get("transport", "stdio"),
                    command=entry.get("command", ""),
                    args=entry.get("args", []),
                    env=entry.get("env", {}),
                    url=entry.get("url", ""),
                    enabled=entry.get("enabled", True),
                    description=entry.get("description", ""),
                    user_path=user_path,
                    user_path_mode=user_path_mode,
                )
                configs.append(cfg)
                # Auto-generate a companion server when mode is "read".
                # NOTE: @modelcontextprotocol/server-filesystem (current version) does not
                # support a --read-only CLI flag; all args are treated as directory paths.
                # The companion gives isolated access to user_path (separate from /tmp);
                # true read-only enforcement is aspirational until a supported version is used.
                if user_path and user_path_mode == "read":
                    # Strip path-like args to get just the launcher flags + package name
                    pre_path = [
                        a for a in cfg.args
                        if not a.startswith("/") and not a.startswith("~")
                    ]
                    companion = MCPServerConfig(
                        name=f"{cfg.name}_user",
                        transport=cfg.transport,
                        command=cfg.command,
                        args=pre_path + [user_path],
                        env=dict(cfg.env),
                        enabled=cfg.enabled,
                        description=f"User path access to {user_path}",
                        is_derived=True,
                    )
                    configs.append(companion)
            except KeyError as exc:
                logger.warning("[MCP] Skipping invalid server entry (missing key %s): %s", exc, entry)
        return configs

    def save_config(self) -> None:
        """Persist the current server configs (_all_configs) to mcp.json."""
        servers: list[dict[str, Any]] = []
        for cfg in self._all_configs.values():
            if cfg.is_derived:
                continue  # companion servers are auto-generated, not persisted
            entry: dict[str, Any] = {
                "name": cfg.name,
                "transport": cfg.transport,
                "enabled": cfg.enabled,
                "description": cfg.description,
            }
            if cfg.transport == "stdio":
                entry["command"] = cfg.command
                entry["args"] = cfg.args
                if cfg.env:
                    entry["env"] = cfg.env
                if cfg.user_path:
                    entry["user_path"] = cfg.user_path
                    entry["user_path_mode"] = cfg.user_path_mode
            else:
                entry["url"] = cfg.url
            servers.append(entry)
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(json.dumps({"servers": servers}, indent=2))
        logger.info("[MCP] Config saved to %s", self._config_path)

    def reload_config(self) -> asyncio.Task:
        """Reload config from disk and reconnect servers asynchronously."""
        return asyncio.create_task(self._reload_async(), name="mcp-reload")

    async def _reload_async(self) -> None:
        await self.shutdown()
        await self.startup()

    # ------------------------------------------------------------------
    # Tool discovery
    # ------------------------------------------------------------------

    def list_tools(self) -> list[MCPToolDef]:
        """Return all tools from all *connected* servers."""
        result: list[MCPToolDef] = []
        for conn in self._connections.values():
            if conn.connected:
                result.extend(conn.tools)
        return result

    def list_tools_openai(self) -> list[dict[str, Any]]:
        """Return tools in OpenAI function-call format."""
        return [t.to_openai() for t in self.list_tools()]

    # ------------------------------------------------------------------
    # Tool invocation
    # ------------------------------------------------------------------

    async def call_tool(self, qualified_name: str, arguments: dict[str, Any]) -> str:
        """Call a tool by its qualified name  ``<server>__<tool>``."""
        # Split on the first __ to support tools whose names contain __
        parts = qualified_name.split("__", 1)
        if len(parts) != 2:
            return f"[MCP ERROR] Invalid tool name (expected '<server>__<tool>'): {qualified_name!r}"

        server_name, tool_name = parts
        conn = self._connections.get(server_name)
        if conn is None:
            return f"[MCP ERROR] Unknown server: {server_name!r}"

        return await conn.call_tool(tool_name, arguments)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> list[ServerStatus]:
        """Return status for ALL configured servers (enabled and disabled)."""
        statuses: list[ServerStatus] = []
        for name, cfg in self._all_configs.items():
            conn = self._connections.get(name)
            statuses.append(
                ServerStatus(
                    name=name,
                    transport=cfg.transport,
                    enabled=cfg.enabled,
                    connected=conn.connected if conn else False,
                    error=conn.error if conn else None,
                    tool_count=len(conn.tools) if conn else 0,
                    description=cfg.description,
                    user_path=cfg.user_path,
                    user_path_mode=cfg.user_path_mode,
                    is_derived=cfg.is_derived,
                )
            )
        return statuses

    # ------------------------------------------------------------------
    # Dynamic server management (runtime add/remove)
    # ------------------------------------------------------------------

    async def add_server(self, cfg: MCPServerConfig, persist: bool = True) -> ServerStatus:
        """Add (or replace) a server, connect if enabled, and optionally save to mcp.json."""
        existing = self._connections.pop(cfg.name, None)
        if existing:
            await existing.disconnect()
        self._all_configs[cfg.name] = cfg
        if persist:
            self.save_config()
        conn: _ServerConnection | None = None
        if cfg.enabled:
            conn = _ServerConnection(cfg)
            self._connections[cfg.name] = conn
            await conn.connect()
        return ServerStatus(
            name=cfg.name,
            transport=cfg.transport,
            enabled=cfg.enabled,
            connected=conn.connected if conn else False,
            error=conn.error if conn else None,
            tool_count=len(conn.tools) if conn else 0,
            description=cfg.description,
            user_path=cfg.user_path,
            user_path_mode=cfg.user_path_mode,
            is_derived=cfg.is_derived,
        )

    async def remove_server(self, name: str, persist: bool = True) -> bool:
        """Disconnect and fully remove a server; optionally persist to mcp.json."""
        conn = self._connections.pop(name, None)
        if conn:
            await conn.disconnect()
        removed = self._all_configs.pop(name, None) is not None
        if (removed or conn is not None) and persist:
            self.save_config()
        return removed or conn is not None

    async def set_enabled(self, name: str, enabled: bool) -> ServerStatus | None:
        """Toggle enabled state, persist to mcp.json, and connect/disconnect as needed."""
        cfg = self._all_configs.get(name)
        if cfg is None:
            return None
        cfg.enabled = enabled
        # Propagate to companion server if one exists
        companion_name = f"{name}_user"
        companion_cfg = self._all_configs.get(companion_name)
        if companion_cfg and companion_cfg.is_derived:
            companion_cfg.enabled = enabled
        self.save_config()
        for target_name, target_cfg in [(name, cfg), (companion_name, companion_cfg)]:
            if target_cfg is None:
                continue
            if enabled and target_name not in self._connections:
                conn = _ServerConnection(target_cfg)
                self._connections[target_name] = conn
                await conn.connect()
            elif not enabled and target_name in self._connections:
                conn = self._connections.pop(target_name)
                await conn.disconnect()
        active = self._connections.get(name)
        return ServerStatus(
            name=name,
            transport=cfg.transport,
            enabled=cfg.enabled,
            connected=active.connected if active else False,
            error=active.error if active else None,
            tool_count=len(active.tools) if active else 0,
            description=cfg.description,
            user_path=cfg.user_path,
            user_path_mode=cfg.user_path_mode,
            is_derived=cfg.is_derived,
        )

    async def update_user_path(
        self,
        name: str,
        user_path: str,
        user_path_mode: str = "read",
    ) -> ServerStatus | None:
        """Update the user_path / user_path_mode for a server, regenerate its companion, reconnect."""
        cfg = self._all_configs.get(name)
        if cfg is None or cfg.is_derived:
            return None

        # 1. Remove old companion server if present
        companion_name = f"{name}_user"
        old_companion_conn = self._connections.pop(companion_name, None)
        if old_companion_conn:
            await old_companion_conn.disconnect()
        self._all_configs.pop(companion_name, None)

        # 2. Update parent config
        cfg.user_path = user_path
        cfg.user_path_mode = user_path_mode

        # 3. Reconnect parent (effective args may have changed for readwrite mode)
        old_conn = self._connections.pop(name, None)
        if old_conn:
            await old_conn.disconnect()
        conn: _ServerConnection | None = None
        if cfg.enabled:
            conn = _ServerConnection(cfg)
            self._connections[name] = conn
            await conn.connect()

        # 4. Regenerate companion for read mode
        if user_path and user_path_mode == "read":
            pre_path = [
                a for a in cfg.args
                if not a.startswith("/") and not a.startswith("~")
            ]
            companion = MCPServerConfig(
                name=companion_name,
                transport=cfg.transport,
                command=cfg.command,
                args=pre_path + [user_path],
                env=dict(cfg.env),
                enabled=cfg.enabled,
                description=f"User path access to {user_path}",
                is_derived=True,
            )
            self._all_configs[companion_name] = companion
            if companion.enabled:
                companion_conn = _ServerConnection(companion)
                self._connections[companion_name] = companion_conn
                await companion_conn.connect()

        # 5. Persist (skips derived)
        self.save_config()

        active = self._connections.get(name)
        return ServerStatus(
            name=name,
            transport=cfg.transport,
            enabled=cfg.enabled,
            connected=active.connected if active else False,
            error=active.error if active else None,
            tool_count=len(active.tools) if active else 0,
            description=cfg.description,
            user_path=cfg.user_path,
            user_path_mode=cfg.user_path_mode,
            is_derived=cfg.is_derived,
        )
