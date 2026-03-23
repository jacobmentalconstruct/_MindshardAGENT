"""
FILE: mcp_server.py
ROLE: MCP stdio server for _ollama-prompt-lab.
WHAT IT DOES: Exposes prompt-lab tools through MCP using the same underlying `run(arguments)` function used by CLI execution.
HOW TO USE:
  - Start: python _ollama-prompt-lab/mcp_server.py
  - Connect as a stdio MCP server from an MCP-capable client.
TOOLS:
  - ollama_prompt_lab
  - validate_model_slot
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from tools.ollama_prompt_lab import FILE_METADATA as OLLAMA_PROMPT_LAB_METADATA, run as run_ollama_prompt_lab
from tools.validate_model_slot import FILE_METADATA as VALIDATE_SLOT_METADATA, run as run_validate_model_slot


SERVER_INFO = {
    "name": "ollama-prompt-lab-mcp",
    "version": "1.0.0",
}

TOOL_REGISTRY = {
    OLLAMA_PROMPT_LAB_METADATA["mcp_name"]: (OLLAMA_PROMPT_LAB_METADATA, run_ollama_prompt_lab),
    VALIDATE_SLOT_METADATA["mcp_name"]: (VALIDATE_SLOT_METADATA, run_validate_model_slot),
}


def _success(result: dict) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
        "structuredContent": result,
        "isError": result.get("status") == "error",
    }


def _tool_list() -> list[dict]:
    return [
        {
            "name": metadata["mcp_name"],
            "description": metadata["summary"],
            "inputSchema": metadata["input_schema"],
        }
        for metadata, _ in TOOL_REGISTRY.values()
    ]


def _call_tool(name: str, arguments: dict) -> dict:
    entry = TOOL_REGISTRY.get(name)
    if not entry:
        return _success({"status": "error", "tool": name, "input": arguments, "result": {"message": f"Unknown tool: {name}"}})
    _, runner = entry
    try:
        return _success(runner(arguments))
    except Exception as exc:
        return _success({
            "status": "error",
            "tool": name,
            "input": arguments,
            "result": {
                "message": str(exc),
                "traceback": traceback.format_exc(),
            },
        })


def _read_message() -> dict | None:
    """Read one NDJSON message from stdin (newline-delimited JSON)."""
    line = sys.stdin.buffer.readline()
    if not line:
        return None
    line = line.strip()
    if not line:
        return None
    return json.loads(line.decode("utf-8"))


def _write_message(payload: dict) -> None:
    """Write one NDJSON message to stdout."""
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(body + b"\n")
    sys.stdout.buffer.flush()


def _handle_request(message: dict) -> dict | None:
    method = message.get("method")
    message_id = message.get("id")
    params = message.get("params", {})

    if method == "notifications/initialized":
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": message_id, "result": {}}
    if method == "initialize":
        client_version = params.get("protocolVersion", "2024-11-05")
        return {
            "jsonrpc": "2.0",
            "id": message_id,
            "result": {
                "protocolVersion": client_version,
                "serverInfo": SERVER_INFO,
                "capabilities": {"tools": {}},
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": message_id, "result": {"tools": _tool_list()}}
    if method == "tools/call":
        return {"jsonrpc": "2.0", "id": message_id, "result": _call_tool(params["name"], params.get("arguments", {}))}
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> int:
    while True:
        message = _read_message()
        if message is None:
            return 0
        response = _handle_request(message)
        if response is not None:
            _write_message(response)


if __name__ == "__main__":
    raise SystemExit(main())
