"""MCP stdio proxy for the running MindshardAGENT UI bridge."""

from __future__ import annotations

import json
import sys
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve()
PROJECT_ROOT = HERE.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _bridge_base_url() -> str:
    from src.core.config.app_config import AppConfig

    bridge_info = PROJECT_ROOT / ".mindshard_ui_bridge.json"
    if bridge_info.exists():
        try:
            data = json.loads(bridge_info.read_text(encoding="utf-8"))
            url = str(data.get("url", "") or "").strip()
            if url:
                return url.rstrip("/")
        except Exception:
            pass

    config = AppConfig.load(PROJECT_ROOT)
    host = config.ui_bridge_host or "127.0.0.1"
    port = int(config.ui_bridge_port or 8765)
    return f"http://{host}:{port}"


def _http_get(path: str) -> dict[str, Any]:
    url = _bridge_base_url() + path
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = _bridge_base_url() + path
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


TOOLS = [
    {
        "name": "mindshard_ui_get_state",
        "description": "Get the visible running-app UI state from the local UI bridge.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_messages": {"type": "integer", "default": 20},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "mindshard_ui_set_input",
        "description": "Replace the visible compose input text in the running app.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
    },
    {
        "name": "mindshard_ui_attach_project",
        "description": "Attach a project folder to the visible app without using the file dialog.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "display_name": {"type": "string"},
                "project_purpose": {"type": "string"},
                "current_goal": {"type": "string"},
                "project_type": {"type": "string"},
                "constraints": {"type": "string"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "mindshard_ui_new_session",
        "description": "Start a fresh session in the visible app.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "mindshard_ui_submit",
        "description": "Submit input through the visible running app.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "loop_mode": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "mindshard_ui_wait_until_idle",
        "description": "Wait until the visible app is no longer streaming.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "timeout_ms": {"type": "integer", "default": 30000},
                "poll_ms": {"type": "integer", "default": 150},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "mindshard_ui_click_button",
        "description": "Trigger one of the faux control-panel buttons in the visible app.",
        "inputSchema": {
            "type": "object",
            "properties": {"label": {"type": "string"}},
            "required": ["label"],
            "additionalProperties": False,
        },
    },
    {
        "name": "mindshard_ui_run_plan",
        "description": "Start the visible Plan workflow without using the goal dialog.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string"},
                "depth": {"type": "integer", "default": 3},
            },
            "required": ["goal"],
            "additionalProperties": False,
        },
    },
    {
        "name": "mindshard_ui_request_stop",
        "description": "Request stop on the visible running app.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
]


def _dispatch(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "mindshard_ui_get_state":
        max_messages = int(arguments.get("max_messages", 20) or 20)
        return _http_get(f"/state?max_messages={max_messages}")

    if name == "mindshard_ui_set_input":
        return _http_post("/command", {"action": "set_input_text", "args": {"text": arguments["text"]}})

    if name == "mindshard_ui_attach_project":
        return _http_post("/command", {"action": "attach_project", "args": arguments})

    if name == "mindshard_ui_new_session":
        return _http_post("/command", {"action": "new_session", "args": {}})

    if name == "mindshard_ui_submit":
        args = {}
        if "text" in arguments:
            args["text"] = arguments["text"]
        if "loop_mode" in arguments:
            args["loop_mode"] = arguments["loop_mode"]
        return _http_post("/command", {"action": "submit_input", "args": args})

    if name == "mindshard_ui_wait_until_idle":
        return _http_post(
            "/command",
            {
                "action": "wait_until_idle",
                "args": {
                    "timeout_ms": int(arguments.get("timeout_ms", 30000) or 30000),
                    "poll_ms": int(arguments.get("poll_ms", 150) or 150),
                },
            },
        )

    if name == "mindshard_ui_click_button":
        return _http_post(
            "/command",
            {"action": "click_faux_button", "args": {"label": arguments["label"]}},
        )

    if name == "mindshard_ui_run_plan":
        return _http_post(
            "/command",
            {
                "action": "run_plan",
                "args": {
                    "goal": arguments["goal"],
                    "depth": int(arguments.get("depth", 3) or 3),
                },
            },
        )

    if name == "mindshard_ui_request_stop":
        return _http_post("/command", {"action": "request_stop", "args": {}})

    return {"status": "error", "message": f"Unknown tool: {name}"}


def _read_message() -> dict | None:
    line = sys.stdin.buffer.readline()
    if not line:
        return None
    line = line.strip()
    if not line:
        return None
    return json.loads(line.decode("utf-8"))


def _write_message(payload: dict) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(body + b"\n")
    sys.stdout.buffer.flush()


SERVER_INFO = {"name": "mindshard-ui-bridge", "version": "1.0.0"}


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
        return {"jsonrpc": "2.0", "id": message_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        try:
            result = _dispatch(tool_name, arguments)
        except urllib.error.URLError as exc:
            result = {
                "status": "error",
                "message": (
                    f"Could not reach the running UI bridge at {_bridge_base_url()}. "
                    "Start the GUI app first."
                ),
                "detail": str(exc),
            }
        except Exception as exc:
            result = {
                "status": "error",
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
        content_text = json.dumps(result, indent=2)
        return {
            "jsonrpc": "2.0",
            "id": message_id,
            "result": {
                "content": [{"type": "text", "text": content_text}],
                "structuredContent": result,
                "isError": result.get("status") == "error" or result.get("ok") is False,
            },
        }
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> int:
    while True:
        try:
            message = _read_message()
        except Exception:
            break
        if message is None:
            break
        try:
            response = _handle_request(message)
        except Exception as exc:
            response = {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {"code": -32603, "message": str(exc)},
            }
        if response is not None:
            _write_message(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
