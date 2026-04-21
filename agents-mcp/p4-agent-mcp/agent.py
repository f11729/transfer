"""Agentic loop for the Perforce Admin SME — backed by Llama4 via Ollama."""

import json
import logging
from typing import Any
from uuid import uuid4

import openai

import sessions
from backend_client import BackendClient

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = "http://10.43.108.69:11434/v1"
MODEL = "llama4"
MAX_TOKENS = 4096

SYSTEM_PROMPT = """\
You are a Perforce (Helix Core) Administration Subject Matter Expert with deep expertise in:

- **Server & Depot Management**: p4d configuration, depot types (local, stream, remote, spec, unload), \
server spec tuning, replica and edge server topology.
- **Workspaces & Streams**: client spec design, stream depot topology (mainline, development, release, \
task streams), stream inheritance and flow.
- **Changelists & Shelving**: pending/submitted changelist workflows, shelve/unshelve patterns, \
changelist descriptions and job associations.
- **Branching & Integration**: `p4 integrate`, branch specs, merge strategies, resolve workflows, \
cherry-pick vs. full integration.
- **Access Control**: `p4 protect` table, groups, users, depot-path permissions, IP-based restrictions.
- **Jobs & Workflows**: job spec customization, job/fix linkage, automated job state transitions.
- **Reviews (Swarm)**: review creation, voting, transitions, commenting, participant management.
- **Performance & Tuning**: db.* table health, `p4 verify`, journaling, checkpoint strategies, \
monitor and lock analysis.
- **Diagnostics**: log analysis, `p4 info`, `p4 diskspace`, common error messages and remediation.

You have access to a set of tools that query a live Perforce server (read-only). Use these tools \
proactively to answer questions with real data. When asked to perform a write operation, explain \
the exact `p4` commands the user should run manually, since write access is not available through \
your tools.

Always be concise, precise, and actionable. When providing commands, include relevant flags and \
explain each option. Warn about irreversible operations.
"""


def _to_openai_tools(backend_tools: list[dict]) -> list[dict]:
    """Convert MCP tool dicts (Anthropic format) to OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in backend_tools
    ]


def _parse_text_tool_call(content: str) -> dict | None:
    """Detect when Llama4 emits a tool call as JSON text instead of tool_calls.

    Handles cases where the model appends special tokens after the JSON.
    Returns a normalised dict with 'name' and 'arguments' (JSON string), or None.
    """
    if not content:
        return None
    # Find first '{' and matching closing '}'
    start = content.find("{")
    if start == -1:
        return None
    depth = 0
    end = -1
    for i, ch in enumerate(content[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        return None
    try:
        obj = json.loads(content[start:end + 1])
    except json.JSONDecodeError:
        return None
    name = obj.get("name")
    if not isinstance(name, str):
        return None
    args = obj.get("parameters") or obj.get("arguments") or obj.get("input") or {}
    return {"name": name, "arguments": json.dumps(args)}


async def run(query: str, session_id: str, backend: BackendClient) -> dict[str, Any]:
    """Run the Perforce Admin agent for one turn, returning the response and session_id."""
    client = openai.AsyncOpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")

    history = sessions.get_or_create(session_id)
    history = list(history)  # shallow copy

    # Prepend system message for new sessions
    if not history:
        history.append({"role": "system", "content": SYSTEM_PROMPT})

    history.append({"role": "user", "content": query})
    tools = _to_openai_tools(await backend.list_tools())

    while True:
        response = await client.chat.completions.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            tools=tools,
            messages=history,
        )

        choice = response.choices[0]
        msg = choice.message
        finish_reason = choice.finish_reason

        # Serialise assistant message for history storage
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.content}
        if msg.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
        history.append(assistant_msg)

        if finish_reason == "stop":
            # Llama4 sometimes emits a tool call as JSON text instead of tool_calls.
            text_call = _parse_text_tool_call(msg.content or "")
            if text_call:
                logger.info("Detected text tool call: %s", text_call["name"])
                tc_id = f"call_{uuid4().hex[:12]}"
                # Rewrite history: replace last assistant message with proper tool_calls form
                history[-1] = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": tc_id,
                        "type": "function",
                        "function": {"name": text_call["name"], "arguments": text_call["arguments"]},
                    }],
                }
                try:
                    args = json.loads(text_call["arguments"])
                except (json.JSONDecodeError, TypeError):
                    args = {}
                result_text = await backend.call_tool(text_call["name"], args)
                history.append({"role": "tool", "tool_call_id": tc_id, "content": result_text})
                continue  # loop back to get Claude's final text response

            sessions.update(session_id, history)
            return {"session_id": session_id, "response": msg.content or ""}

        if finish_reason != "tool_calls":
            sessions.update(session_id, history)
            return {"session_id": session_id, "response": f"Unexpected finish reason: {finish_reason}"}

        # Execute each tool call and append results
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                args = {}
            logger.info("Calling tool %s with %s", tc.function.name, args)
            result_text = await backend.call_tool(tc.function.name, args)
            history.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_text,
            })
