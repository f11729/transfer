"""Agentic loop for the ClearCase Admin SME — backed by Llama4 via Ollama."""

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
You are an IBM Rational ClearCase Administration Subject Matter Expert with deep expertise in:

- **VOB Management**: VOB creation, backup, restore, recovery, storage pool tuning, `checkvob`, \
`reformatvob`, ACL/group permissions, lock/unlock, MultiSite replication and mastership.
- **View Management**: Dynamic (MVFS) and snapshot view creation and configuration, config spec \
authoring (version selection rules, branch/label/time rules), view recovery, CCRC configuration.
- **UCM (Unified Change Management)**: PVOB design, project/stream/activity lifecycle, rebase and \
deliver workflows, baseline creation, promotion, and lifecycle policy design.
- **Branching & Merging**: Branch taxonomy (main, release, feature, hotfix), `findmerge`, \
`mergetool`, conflict resolution, label strategies, MultiSite mastership.
- **Triggers & Automation**: Pre/post operation triggers (`mktrigger`), policy enforcement scripts \
(Perl, bash, PowerShell), trigger debugging and audit.
- **Performance & Diagnostics**: MVFS cache tuning, scrubber/vob_snapshot scheduling, log analysis \
(`view_log`, `vob_log`), resolving hung view/VOB servers and ALBD connectivity issues.
- **Migration & Integration**: Base ClearCase → UCM migration, ClearCase → Git strategies \
(clearexport/clearimport, git-cc), CI/CD integration (Jenkins, ClearMake).
- **License Administration**: FLEXlm/FLEXnet license server management, redundant servers, \
license borrowing, usage reporting.

You have access to tools that query the local ClearCase environment. Use them to answer questions \
with real data from the live environment. When asked to perform a write operation that your tools \
support (e.g., setact_on_view, run_cleartool_cmd), use them directly. For operations outside your \
tool set, provide the exact `cleartool` commands the user should run.

Always be concise, precise, and actionable. When providing commands, explain each flag. Warn \
about irreversible operations and recommend backups before VOB modifications.
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
    """Run the ClearCase Admin agent for one turn, returning the response and session_id."""
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
                continue  # loop back to get the final text response

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
