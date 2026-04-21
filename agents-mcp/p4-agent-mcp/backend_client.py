"""Async MCP stdio client — proxies tool calls to the underlying p4-mcp-server."""

import asyncio
import os
import logging
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

P4_SERVER_BIN = "/local/mnt/workspace/mcp/p4-mcp-server/p4-mcp-server"
P4PORT = os.environ.get("P4PORT", "ssl:10.43.108.69:1666")
P4USER = os.environ.get("P4USER", "aseah")


class BackendClient:
    """Long-lived MCP client that connects to p4-mcp-server over stdio."""

    def __init__(self):
        self._session: ClientSession | None = None
        self._context = None
        self._lock = asyncio.Lock()
        self._tools_cache: list | None = None

    async def _ensure_connected(self) -> ClientSession:
        async with self._lock:
            if self._session is not None:
                return self._session

            server_params = StdioServerParameters(
                command=P4_SERVER_BIN,
                args=["--readonly", "--allow-usage"],
                env={"P4PORT": P4PORT, "P4USER": P4USER},
            )
            self._context = stdio_client(server_params)
            read, write = await self._context.__aenter__()
            session = ClientSession(read, write)
            await session.__aenter__()
            await session.initialize()
            self._session = session
            logger.info("Connected to p4-mcp-server")
            return self._session

    async def list_tools(self) -> list[dict]:
        """Return tools as Anthropic-compatible tool dicts (cached)."""
        if self._tools_cache is not None:
            return self._tools_cache

        session = await self._ensure_connected()
        result = await session.list_tools()
        tools = []
        for t in result.tools:
            tools.append({
                "name": t.name,
                "description": t.description or "",
                "input_schema": t.inputSchema if t.inputSchema else {"type": "object", "properties": {}},
            })
        self._tools_cache = tools
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Call a tool on the underlying MCP server and return the result as a string."""
        session = await self._ensure_connected()
        try:
            result = await session.call_tool(name, arguments)
            parts = []
            for content in result.content:
                if hasattr(content, "text"):
                    parts.append(content.text)
                else:
                    parts.append(str(content))
            return "\n".join(parts) if parts else "(no output)"
        except Exception as exc:
            logger.error("Tool call %s failed: %s", name, exc)
            return f"Error calling {name}: {exc}"

    async def close(self):
        if self._session:
            await self._session.__aexit__(None, None, None)
        if self._context:
            await self._context.__aexit__(None, None, None)
        self._session = None
        self._context = None
        self._tools_cache = None
