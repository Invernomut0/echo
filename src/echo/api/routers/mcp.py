"""MCP management endpoints.

GET  /api/mcp/servers          — list all configured MCP servers and their status
GET  /api/mcp/tools            — list all tools from connected servers
POST /api/mcp/servers          — add a new server at runtime (not persisted to mcp.json)
DELETE /api/mcp/servers/{name} — disconnect and remove a server
POST /api/mcp/reload           — reload mcp.json from disk and reconnect all servers
POST /api/mcp/tools/call       — call a specific tool directly (testing / debug)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from echo.mcp import mcp_manager
from echo.mcp.client import MCPServerConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ServerStatusOut(BaseModel):
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


class ToolOut(BaseModel):
    qualified_name: str
    server_name: str
    name: str
    description: str
    input_schema: dict[str, Any]


class AddServerRequest(BaseModel):
    name: str = Field(..., description="Unique server identifier")
    transport: str = Field("stdio", description="'stdio' or 'sse'")
    # stdio
    command: str = Field("", description="Executable to launch (stdio transport)")
    args: list[str] = Field(default_factory=list, description="CLI arguments (stdio)")
    env: dict[str, str] = Field(default_factory=dict, description="Extra environment variables")
    # sse
    url: str = Field("", description="HTTP URL (sse transport)")
    description: str = ""


class CallToolRequest(BaseModel):
    tool: str = Field(..., description="Qualified tool name: '<server>__<tool>'")
    arguments: dict[str, Any] = Field(default_factory=dict)


class CallToolResponse(BaseModel):
    tool: str
    result: str


class PatchServerRequest(BaseModel):
    enabled: bool | None = None
    user_path: str | None = None
    user_path_mode: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/servers", response_model=list[ServerStatusOut])
async def list_servers() -> list[ServerStatusOut]:
    """Return status of all configured MCP servers."""
    return [
        ServerStatusOut(**vars(s))
        for s in mcp_manager.get_status()
    ]


@router.get("/tools", response_model=list[ToolOut])
async def list_tools() -> list[ToolOut]:
    """Return all tools from all connected MCP servers."""
    return [
        ToolOut(
            qualified_name=t.qualified_name,
            server_name=t.server_name,
            name=t.name,
            description=t.description,
            input_schema=t.input_schema,
        )
        for t in mcp_manager.list_tools()
    ]


@router.post("/servers", response_model=ServerStatusOut, status_code=status.HTTP_201_CREATED)
async def add_server(req: AddServerRequest) -> ServerStatusOut:
    """Add a new MCP server, connect, and persist to mcp.json."""
    cfg = MCPServerConfig(
        name=req.name,
        transport=req.transport,
        command=req.command,
        args=req.args,
        env=req.env,
        url=req.url,
        enabled=True,
        description=req.description,
    )
    result = await mcp_manager.add_server(cfg, persist=True)
    return ServerStatusOut(**vars(result))


@router.patch("/servers/{name}", response_model=ServerStatusOut)
async def toggle_server(name: str, req: PatchServerRequest) -> ServerStatusOut:
    """Enable/disable a server or update its user_path/user_path_mode."""
    if req.user_path is not None:
        # Update user path (also handles reconnect and companion regeneration)
        mode = req.user_path_mode or "read"
        status_result = await mcp_manager.update_user_path(name, req.user_path, mode)
        if status_result is None:
            raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
    elif req.enabled is not None:
        status_result = await mcp_manager.set_enabled(name, req.enabled)
        if status_result is None:
            raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
    else:
        raise HTTPException(status_code=400, detail="Provide 'enabled', 'user_path', or both")
    return ServerStatusOut(**vars(status_result))


@router.delete("/servers/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_server(name: str) -> None:
    """Disconnect and remove an MCP server; persists change to mcp.json."""
    removed = await mcp_manager.remove_server(name, persist=True)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")


@router.post("/reload", response_model=list[ServerStatusOut])
async def reload_servers() -> list[ServerStatusOut]:
    """Reload mcp.json from disk and reconnect all servers."""
    task = mcp_manager.reload_config()
    await task  # wait for reload to finish
    return [ServerStatusOut(**vars(s)) for s in mcp_manager.get_status()]


@router.post("/tools/call", response_model=CallToolResponse)
async def call_tool(req: CallToolRequest) -> CallToolResponse:
    """Directly invoke an MCP tool (useful for testing from the UI or curl)."""
    result = await mcp_manager.call_tool(req.tool, req.arguments)
    return CallToolResponse(tool=req.tool, result=result)
