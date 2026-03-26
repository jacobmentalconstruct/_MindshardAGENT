"""MCP stdio server for Prompt Lab."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.core.prompt_lab.contracts import serialize_record
from src.prompt_lab.entrypoints import build_prompt_lab_entrypoints

PROJECT_ROOT = Path(__file__).resolve().parents[2]

TOOLS = [
    {
        "name": "prompt_lab_get_status",
        "description": "Get Prompt Lab paths, metadata, and active package status.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "prompt_lab_list_records",
        "description": "List Prompt Lab records for a specific kind.",
        "inputSchema": {
            "type": "object",
            "properties": {"kind": {"type": "string"}},
            "required": ["kind"],
            "additionalProperties": False,
        },
    },
    {
        "name": "prompt_lab_show_record",
        "description": "Show one Prompt Lab record by kind and id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string"},
                "record_id": {"type": "string"},
            },
            "required": ["kind", "record_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "prompt_lab_validate",
        "description": "Run Prompt Lab structural validation and persist the validation snapshot.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "prompt_lab_publish",
        "description": "Publish a validated Prompt Lab package from selected profiles, plan, and bindings.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "package_id": {"type": "string"},
                "package_name": {"type": "string"},
                "execution_plan_id": {"type": "string"},
                "prompt_profile_ids": {"type": "array", "items": {"type": "string"}},
                "binding_ids": {"type": "array", "items": {"type": "string"}},
                "published_by": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["package_id", "package_name", "execution_plan_id", "prompt_profile_ids", "binding_ids"],
            "additionalProperties": False,
        },
    },
    {
        "name": "prompt_lab_activate",
        "description": "Activate a published Prompt Lab package as the only runtime-consumable state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "package_id": {"type": "string"},
                "activated_by": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["package_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "prompt_lab_get_active",
        "description": "Get the current active Prompt Lab state and resolved package, if any.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "prompt_lab_get_operations",
        "description": "Return recent Prompt Lab operation log entries.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 20}},
            "additionalProperties": False,
        },
    },
]

SERVER_INFO = {"name": "mindshard-prompt-lab", "version": "1.0.0"}


def _read_message() -> dict | None:
    line = sys.stdin.buffer.readline()
    if not line:
        return None
    line = line.strip()
    if not line:
        return None
    return json.loads(line.decode("utf-8"))


def _write_message(payload: dict) -> None:
    sys.stdout.buffer.write(json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def _dispatch(entrypoints, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    services = entrypoints.services

    if name == "prompt_lab_get_status":
        active_state = services.package_service.get_active_state()
        result = {
            "status": "ok",
            "project_root": str(entrypoints.project_root),
            "paths": {
                field: str(getattr(services.storage.paths, field))
                for field in services.storage.paths.__dataclass_fields__
            },
            "metadata": services.metadata,
            "active_package_id": active_state.published_package_id if active_state else "",
        }
        services.operation_log.record(channel="mcp", action=name, status="ok", details={"active_package_id": result["active_package_id"]})
        return result

    if name == "prompt_lab_list_records":
        kind = str(arguments.get("kind", "")).strip()
        if kind in {"eval_run", "promotion_record", "validation_snapshot"}:
            records = services.storage.list_history_records(kind)
        else:
            records = services.storage.list_design_objects(kind)
        services.operation_log.record(channel="mcp", action=name, status="ok", details={"kind": kind, "count": len(records)})
        return {"status": "ok", "kind": kind, "count": len(records), "records": records}

    if name == "prompt_lab_show_record":
        kind = str(arguments.get("kind", "")).strip()
        record_id = str(arguments.get("record_id", "")).strip()
        if kind in {"eval_run", "promotion_record", "validation_snapshot"}:
            record = services.storage.load_history_record(kind, record_id)
        else:
            record = services.storage.load_design_object(kind, record_id)
        services.operation_log.record(channel="mcp", action=name, status="ok", details={"kind": kind, "record_id": record_id})
        return {"status": "ok", "kind": kind, "record": serialize_record(record)}

    if name == "prompt_lab_validate":
        snapshot = services.validate_state(services.storage)
        services.storage.save_validation_snapshot(snapshot)
        services.operation_log.record(channel="mcp", action=name, status=snapshot.status, details={"snapshot_id": snapshot.id})
        return {"status": snapshot.status, "record": serialize_record(snapshot)}

    if name == "prompt_lab_publish":
        result = services.package_service.publish_package(
            package_id=str(arguments["package_id"]),
            package_name=str(arguments["package_name"]),
            execution_plan_id=str(arguments["execution_plan_id"]),
            prompt_profile_ids=[str(item) for item in arguments.get("prompt_profile_ids", [])],
            binding_ids=[str(item) for item in arguments.get("binding_ids", [])],
            published_by=str(arguments.get("published_by", "mcp")),
            notes=str(arguments.get("notes", "")),
        )
        services.operation_log.record(channel="mcp", action=name, status="ok", details={"package_id": result.package.id})
        return {
            "status": "ok",
            "package": serialize_record(result.package),
            "validation_snapshot_id": result.validation_snapshot_id,
            "promotion_record_id": result.promotion_record_id,
        }

    if name == "prompt_lab_activate":
        active_state = services.package_service.activate_package(
            str(arguments["package_id"]),
            activated_by=str(arguments.get("activated_by", "mcp")),
            notes=str(arguments.get("notes", "")),
        )
        services.operation_log.record(channel="mcp", action=name, status="ok", details={"package_id": active_state.published_package_id})
        return {"status": "ok", "record": serialize_record(active_state)}

    if name == "prompt_lab_get_active":
        active_state = services.package_service.get_active_state()
        package = services.package_service.resolve_active_package()
        services.operation_log.record(
            channel="mcp",
            action=name,
            status="ok" if active_state else "empty",
            details={"package_id": active_state.published_package_id if active_state else ""},
        )
        return {
            "status": "ok" if active_state else "empty",
            "record": serialize_record(active_state) if active_state else None,
            "package": serialize_record(package) if package else None,
        }

    if name == "prompt_lab_get_operations":
        limit = int(arguments.get("limit", 20) or 20)
        records = services.operation_log.tail(limit=limit)
        services.operation_log.record(channel="mcp", action=name, status="ok", details={"limit": limit})
        return {"status": "ok", "records": records}

    return {"status": "error", "message": f"Unknown tool: {name}"}


def _handle_request(entrypoints, message: dict[str, Any]) -> dict[str, Any] | None:
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
            result = _dispatch(entrypoints, tool_name, arguments)
        except Exception as exc:
            result = {
                "status": "error",
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
        return {
            "jsonrpc": "2.0",
            "id": message_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                "structuredContent": result,
                "isError": result.get("status") == "error",
            },
        }
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main(project_root: str | Path | None = None) -> int:
    entrypoints = build_prompt_lab_entrypoints(project_root or PROJECT_ROOT)
    while True:
        try:
            message = _read_message()
        except Exception:
            break
        if message is None:
            break
        try:
            response = _handle_request(entrypoints, message)
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
