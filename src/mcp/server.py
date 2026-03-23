"""
FILE: src/mcp/server.py
ROLE: MCP stdio server that exposes the MindshardAGENT engine for agent-to-agent use.

WHAT IT DOES:
  Bootstraps a headless Engine (no Tkinter, no GUI) from the same app_config.json
  used by the GUI app, then exposes its capabilities over MCP stdio protocol.

  This allows Claude (or any MCP-capable agent) to:
    - Submit prompts to MindshardAGENT and get responses
    - Run CLI commands inside the sandbox
    - Inspect and manage chat history
    - Preview the built system prompt
    - Query current configuration

HOW TO START:
  python mcp_agent_server.py                 # from project root
  python -m src.mcp.server                   # from project root

MCP TOOLS EXPOSED:
  mindshard_submit       — submit a user prompt, get full response
  mindshard_run_cli      — run a CLI command in the sandbox
  mindshard_get_history  — get current chat history
  mindshard_clear_history — clear chat history
  mindshard_preview_prompt — get the built system prompt text
  mindshard_get_status   — get engine status + config summary
  mindshard_list_tools   — list tools available in the sandbox
  mindshard_request_stop — stop the currently running agent loop

NOTES:
  - submit_prompt is synchronous from MCP's perspective (blocks until agent completes).
  - The engine runs in the same process as the MCP server — one engine per server.
  - Session state (chat history) persists across calls within one server session.
  - The server does NOT start the Tkinter GUI — it is purely headless.
"""

from __future__ import annotations

import json
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

# ── Path setup ────────────────────────────────────────────────
# Server may be launched from project root or from src/mcp/
_HERE = Path(__file__).resolve()
PROJECT_ROOT = _HERE.parent.parent.parent  # src/mcp/server.py → project root
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Engine bootstrap ──────────────────────────────────────────

def _boot_engine():
    """Build and start a headless Engine from the project's app_config.json."""
    from src.core.config.app_config import AppConfig
    from src.core.runtime.activity_stream import ActivityStream
    from src.core.runtime.event_bus import EventBus
    from src.core.engine import Engine

    config = AppConfig.load(PROJECT_ROOT)

    # Headless activity stream — subscribe a logger that writes to stderr
    # (keeping stdout clean for MCP wire protocol)
    activity = ActivityStream()
    activity.subscribe(lambda entry: print(
        f"[{entry.level}][{entry.source}] {entry.message}", file=sys.stderr, flush=True
    ))
    bus = EventBus()

    engine = Engine(config, activity, bus)

    # Set up default sandbox
    sandbox_root = config.sandbox_root or str(PROJECT_ROOT / "_sandbox")
    config.sandbox_root = sandbox_root
    engine.set_sandbox(sandbox_root)
    engine.start()

    return engine, config


# ── Sync wrapper for async submit_prompt ─────────────────────

def _submit_sync(
    engine,
    text: str,
    timeout: float = 180.0,
) -> dict[str, Any]:
    """Run engine.submit_prompt and block until complete or timeout."""
    result_holder: dict[str, Any] = {}
    done = threading.Event()
    tokens: list[str] = []

    def on_token(tok: str) -> None:
        tokens.append(tok)

    def on_complete(result: dict) -> None:
        result_holder["result"] = result
        done.set()

    def on_error(err: str) -> None:
        result_holder["error"] = err
        done.set()

    engine.submit_prompt(text, on_token=on_token, on_complete=on_complete, on_error=on_error)
    timed_out = not done.wait(timeout=timeout)

    if timed_out:
        engine.request_stop()
        return {
            "status": "timeout",
            "partial_response": "".join(tokens),
            "message": f"No response received within {timeout}s — loop stopped.",
        }
    if "error" in result_holder:
        return {"status": "error", "message": result_holder["error"]}

    res = result_holder["result"]
    return {
        "status": "ok",
        "content": res.get("content", "".join(tokens)),
        "metadata": res.get("metadata", {}),
        "streaming_tokens_collected": len(tokens),
    }


# ── Tool definitions ──────────────────────────────────────────

TOOLS = [
    {
        "name": "mindshard_submit",
        "description": (
            "Submit a user prompt to MindshardAGENT and receive the full response. "
            "The agent may invoke tools (CLI, file write, Python) autonomously before responding. "
            "Blocks until the agent loop completes (up to timeout seconds)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The user message to send to the agent.",
                },
                "timeout": {
                    "type": "number",
                    "description": "Max seconds to wait for a response. Default 180.",
                    "default": 180,
                },
            },
            "required": ["message"],
            "additionalProperties": False,
        },
    },
    {
        "name": "mindshard_run_cli",
        "description": (
            "Execute a CLI command directly in the MindshardAGENT sandbox (bypasses the agent loop). "
            "Returns stdout, stderr, and exit_code."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run."},
                "cwd": {"type": "string", "description": "Working directory (relative to sandbox root)."},
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    },
    {
        "name": "mindshard_get_history",
        "description": "Return the current chat history (list of role/content turns).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max number of recent turns to return. 0 = all.",
                    "default": 0,
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "mindshard_clear_history",
        "description": "Clear the current chat history, starting a fresh conversation context.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "mindshard_preview_prompt",
        "description": (
            "Build and return the current system prompt that would be sent to the model. "
            "Useful for inspecting what context the agent is working with."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_text": {
                    "type": "string",
                    "description": "Optional sample user text to include in prompt preview.",
                    "default": "",
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "mindshard_get_status",
        "description": (
            "Get current engine status: running state, sandbox root, selected model, "
            "config summary, and tool count."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "mindshard_list_tools",
        "description": "List the tools (functions) currently registered in the sandbox tool catalog.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "mindshard_request_stop",
        "description": "Request that the currently running agent loop stop at the next safe checkpoint.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
]


# ── Tool dispatch ─────────────────────────────────────────────

def _dispatch(engine, config, name: str, arguments: dict) -> dict:
    """Route an MCP tool call to the engine and return a result dict."""

    if name == "mindshard_submit":
        msg = arguments.get("message", "")
        if not msg:
            return {"status": "error", "message": "message is required"}
        timeout = float(arguments.get("timeout", 180))
        return _submit_sync(engine, msg, timeout=timeout)

    if name == "mindshard_run_cli":
        command = arguments.get("command", "")
        if not command:
            return {"status": "error", "message": "command is required"}
        cwd = arguments.get("cwd") or None
        result = engine.run_cli(command, cwd=cwd)
        return {"status": "ok", **result}

    if name == "mindshard_get_history":
        history = engine.get_history()
        limit = int(arguments.get("limit", 0))
        if limit > 0:
            history = history[-limit:]
        return {"status": "ok", "turn_count": len(history), "history": history}

    if name == "mindshard_clear_history":
        engine.clear_history()
        return {"status": "ok", "message": "Chat history cleared."}

    if name == "mindshard_preview_prompt":
        user_text = arguments.get("user_text", "")
        try:
            build = engine.preview_system_prompt(user_text=user_text)
            if build is None:
                return {"status": "error", "message": "Could not build prompt — check sandbox and model config."}
            return {
                "status": "ok",
                "system_prompt": build.prompt,
                "source_fingerprint": build.source_fingerprint,
                "prompt_fingerprint": build.prompt_fingerprint,
                "char_count": len(build.prompt),
            }
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    if name == "mindshard_get_status":
        from src.core.agent.model_roles import PRIMARY_CHAT_ROLE, resolve_model_for_role
        model = resolve_model_for_role(config, PRIMARY_CHAT_ROLE) or "(none)"
        tool_count = len(engine.tool_catalog.list_tools()) if engine.tool_catalog else 0
        return {
            "status": "ok",
            "engine_running": engine.is_running,
            "sandbox_root": config.sandbox_root or "(not set)",
            "active_model": model,
            "ollama_url": config.ollama_base_url,
            "docker_enabled": config.docker_enabled,
            "max_tool_rounds": config.max_tool_rounds,
            "tool_count": tool_count,
            "history_turns": len(engine.get_history()),
        }

    if name == "mindshard_list_tools":
        if not engine.tool_catalog:
            return {"status": "ok", "tools": [], "count": 0}
        tool_list = engine.tool_catalog.list_tools()
        tools = [
            {"name": t.name, "description": getattr(t, "description", ""), "source": getattr(t, "source", "")}
            for t in tool_list
        ]
        return {"status": "ok", "count": len(tools), "tools": tools}

    if name == "mindshard_request_stop":
        engine.request_stop()
        return {"status": "ok", "message": "Stop requested — loop will halt at next checkpoint."}

    return {"status": "error", "message": f"Unknown tool: {name}"}


# ── MCP wire protocol ─────────────────────────────────────────

def _read_message() -> dict | None:
    # MCP stdio transport uses newline-delimited JSON (one JSON object per line)
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


SERVER_INFO = {"name": "mindshard-agent", "version": "1.0.0"}


def _handle_request(engine, config, message: dict) -> dict | None:
    method = message.get("method")
    message_id = message.get("id")
    params = message.get("params", {})

    if method == "notifications/initialized":
        return None

    if method == "ping":
        return {"jsonrpc": "2.0", "id": message_id, "result": {}}

    if method == "initialize":
        # Echo back whichever version the client requested (we support all stable versions)
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
            result = _dispatch(engine, config, tool_name, arguments)
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
                "isError": result.get("status") == "error",
            },
        }

    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


# ── Main ──────────────────────────────────────────────────────

def main() -> int:
    print("[mindshard-mcp] Booting engine...", file=sys.stderr, flush=True)
    try:
        engine, config = _boot_engine()
    except Exception as exc:
        print(f"[mindshard-mcp] Engine boot failed: {exc}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return 1

    print(
        f"[mindshard-mcp] Ready — sandbox: {config.sandbox_root}",
        file=sys.stderr, flush=True,
    )

    while True:
        try:
            message = _read_message()
        except Exception:
            break
        if message is None:
            break
        try:
            response = _handle_request(engine, config, message)
        except Exception as exc:
            response = {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {"code": -32603, "message": str(exc)},
            }
        if response is not None:
            _write_message(response)

    engine.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
