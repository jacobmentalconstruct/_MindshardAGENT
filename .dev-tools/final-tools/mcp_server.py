"""
FILE: mcp_server.py
ROLE: MCP stdio server for .final-tools.
WHAT IT DOES: Exposes the final toolset through MCP using the same underlying `run(arguments)` functions used by the CLI.
HOW TO USE:
  - Start: python .final-tools/mcp_server.py
  - Connect as a stdio MCP server from an MCP-capable client.
TOOLS:
  - workspace_audit
  - data_shape_inspector
  - structured_patch
  - python_risk_scan
  - tk_ui_map
  - tk_ui_thread_audit
  - tk_ui_event_map
  - tk_ui_layout_audit
  - tk_ui_test_scaffold
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from tools.data_shape_inspector import FILE_METADATA as DATA_METADATA, run as run_data_shape_inspector
from tools.module_decomp_planner import FILE_METADATA as MODULE_DECOMP_METADATA, run as run_module_decomp_planner
from tools.python_risk_scan import FILE_METADATA as PYTHON_SCAN_METADATA, run as run_python_risk_scan
from tools.structured_patcher import FILE_METADATA as PATCH_METADATA, run as run_structured_patch
from tools.tk_ui_event_map import FILE_METADATA as TK_UI_EVENT_MAP_METADATA, run as run_tk_ui_event_map
from tools.tk_ui_layout_audit import FILE_METADATA as TK_UI_LAYOUT_AUDIT_METADATA, run as run_tk_ui_layout_audit
from tools.tk_ui_map import FILE_METADATA as TK_UI_MAP_METADATA, run as run_tk_ui_map
from tools.tk_ui_test_scaffold import FILE_METADATA as TK_UI_TEST_SCAFFOLD_METADATA, run as run_tk_ui_test_scaffold
from tools.tk_ui_thread_audit import FILE_METADATA as TK_UI_THREAD_AUDIT_METADATA, run as run_tk_ui_thread_audit
from tools.workspace_audit import FILE_METADATA as WORKSPACE_METADATA, run as run_workspace_audit


SERVER_INFO = {
    "name": "final-tools-mcp",
    "version": "1.0.0"
}

TOOL_REGISTRY = {
    WORKSPACE_METADATA["mcp_name"]: (WORKSPACE_METADATA, run_workspace_audit),
    DATA_METADATA["mcp_name"]: (DATA_METADATA, run_data_shape_inspector),
    MODULE_DECOMP_METADATA["mcp_name"]: (MODULE_DECOMP_METADATA, run_module_decomp_planner),
    PATCH_METADATA["mcp_name"]: (PATCH_METADATA, run_structured_patch),
    PYTHON_SCAN_METADATA["mcp_name"]: (PYTHON_SCAN_METADATA, run_python_risk_scan),
    TK_UI_MAP_METADATA["mcp_name"]: (TK_UI_MAP_METADATA, run_tk_ui_map),
    TK_UI_THREAD_AUDIT_METADATA["mcp_name"]: (TK_UI_THREAD_AUDIT_METADATA, run_tk_ui_thread_audit),
    TK_UI_EVENT_MAP_METADATA["mcp_name"]: (TK_UI_EVENT_MAP_METADATA, run_tk_ui_event_map),
    TK_UI_LAYOUT_AUDIT_METADATA["mcp_name"]: (TK_UI_LAYOUT_AUDIT_METADATA, run_tk_ui_layout_audit),
    TK_UI_TEST_SCAFFOLD_METADATA["mcp_name"]: (TK_UI_TEST_SCAFFOLD_METADATA, run_tk_ui_test_scaffold),
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
