"""uv run python server.py"""

# Perforce Admin SME — MCP Agent Server
# Exposes ask_perforce_admin(query, session_id) as a callable MCP tool.

import asyncio
import logging
import os
from uuid import uuid4

from mcp.server.fastmcp import FastMCP

import agent
from backend_client import BackendClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

mcp = FastMCP("Perforce Admin Agent")
backend = BackendClient()


@mcp.tool(
    annotations={
        "title": "Ask the Perforce Admin SME",
        "readOnlyHint": True,
    }
)
async def ask_perforce_admin(query: str, session_id: str = None) -> dict:
    """
    Ask the Perforce Administration Subject Matter Expert a question.

    The agent has access to live Perforce server data (read-only) and will
    use it to provide accurate, actionable answers about depot management,
    workspaces, changelists, shelves, jobs, branching, access control, and more.

    Args:
        query: Your question or request in natural language.
        session_id: Optional. Pass the session_id from a previous response to
                    continue a multi-turn conversation. Omit to start a new session.

    Returns:
        dict with keys:
            session_id (str): Use this value in subsequent calls to continue the conversation.
            response (str): The agent's answer.
    """
    sid = session_id or str(uuid4())
    logger.info("ask_perforce_admin session=%s query=%r", sid, query[:80])
    return await agent.run(query, sid, backend)


if __name__ == "__main__":
    mcp.run(transport="stdio")
