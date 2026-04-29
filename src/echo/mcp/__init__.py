"""MCP (Model Context Protocol) client layer for PROJECT ECHO.

ECHO connects to external MCP servers as a *client*, extending its cognitive
capabilities with external tools (file systems, search engines, APIs, …).

Usage
-----
    from echo.mcp import mcp_manager

    # At startup (already called by CognitivePipeline.startup)
    await mcp_manager.startup()

    # List available tools in OpenAI function-call format
    tools = await mcp_manager.list_tools_openai()

    # Call a tool by its fully-qualified name  "<server>__<tool>"
    result = await mcp_manager.call_tool("filesystem__read_file", {"path": "/tmp/x.txt"})

    # At shutdown
    await mcp_manager.shutdown()
"""

from echo.mcp.client import MCPClientManager

mcp_manager = MCPClientManager()

__all__ = ["mcp_manager", "MCPClientManager"]
