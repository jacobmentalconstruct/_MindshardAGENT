"""MCP stdio server for Prompt Lab."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.core.prompt_lab.contracts import (
    EVAL_RUN_KIND,
    PROMOTION_RECORD_KIND,
    TRAINING_RUN_KIND,
    VALIDATION_SNAPSHOT_KIND,
    serialize_record,
)
from src.core.prompt_lab.training_service import (
    DEFAULT_GENERATOR_MODEL,
    DEFAULT_GENERATOR_NUM_CTX,
    DEFAULT_JUDGE_MODEL,
    DEFAULT_JUDGE_NUM_CTX,
    DEFAULT_TARGET_MODEL,
    DEFAULT_TARGET_NUM_CTX,
)
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
    {
        "name": "prompt_lab_train_run",
        "description": "Run a manual batch Prompt Lab training job for one profile in one published package.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "package_id": {"type": "string"},
                "profile_id": {"type": "string"},
                "suite_id": {"type": "string"},
                "target_model": {"type": "string"},
                "generator_model": {"type": "string"},
                "judge_model": {"type": "string"},
                "candidate_count": {"type": "integer"},
                "target_num_ctx": {"type": "integer"},
                "generator_num_ctx": {"type": "integer"},
                "judge_num_ctx": {"type": "integer"},
            },
            "required": ["package_id", "profile_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "prompt_lab_train_list",
        "description": "List recorded Prompt Lab training runs.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "prompt_lab_train_show",
        "description": "Show one recorded Prompt Lab training run by id.",
        "inputSchema": {
            "type": "object",
            "properties": {"run_id": {"type": "string"}},
            "required": ["run_id"],
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
    history_kinds = {EVAL_RUN_KIND, TRAINING_RUN_KIND, PROMOTION_RECORD_KIND, VALIDATION_SNAPSHOT_KIND}

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
        if kind in history_kinds:
            records = services.storage.list_history_records(kind)
        else:
            records = services.storage.list_design_objects(kind)
        services.operation_log.record(channel="mcp", action=name, status="ok", details={"kind": kind, "count": len(records)})
        return {"status": "ok", "kind": kind, "count": len(records), "records": records}

    if name == "prompt_lab_show_record":
        kind = str(arguments.get("kind", "")).strip()
        record_id = str(arguments.get("record_id", "")).strip()
        if kind in history_kinds:
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

    if name == "prompt_lab_train_run":
        result = services.training_service.run_training(
            package_id=str(arguments["package_id"]),
            profile_id=str(arguments["profile_id"]),
            suite_id=str(arguments.get("suite_id", "")).strip() or services.training_service.ensure_default_training_suite().id,
            target_model=str(arguments.get("target_model", "")).strip() or DEFAULT_TARGET_MODEL,
            generator_model=str(arguments.get("generator_model", "")).strip() or DEFAULT_GENERATOR_MODEL,
            judge_model=str(arguments.get("judge_model", "")).strip() or DEFAULT_JUDGE_MODEL,
            candidate_count=int(arguments.get("candidate_count", 3) or 3),
            target_num_ctx=int(arguments.get("target_num_ctx", DEFAULT_TARGET_NUM_CTX) or DEFAULT_TARGET_NUM_CTX),
            generator_num_ctx=int(arguments.get("generator_num_ctx", DEFAULT_GENERATOR_NUM_CTX) or DEFAULT_GENERATOR_NUM_CTX),
            judge_num_ctx=int(arguments.get("judge_num_ctx", DEFAULT_JUDGE_NUM_CTX) or DEFAULT_JUDGE_NUM_CTX),
        )
        services.operation_log.record(channel="mcp", action=name, status="ok", details={"run_id": result.training_run.id})
        return {
            "status": "ok",
            "training_run": serialize_record(result.training_run),
            "baseline_profile_id": result.baseline_profile_id,
            "recommended_profile_id": result.recommended_profile_id,
        }

    if name == "prompt_lab_train_list":
        records = services.training_service.list_training_runs()
        services.operation_log.record(channel="mcp", action=name, status="ok", details={"count": len(records)})
        return {"status": "ok", "count": len(records), "records": records}

    if name == "prompt_lab_train_show":
        run_id = str(arguments.get("run_id", "")).strip()
        record = services.training_service.get_training_run(run_id)
        services.operation_log.record(channel="mcp", action=name, status="ok", details={"run_id": run_id})
        return {"status": "ok", "record": serialize_record(record)}

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
