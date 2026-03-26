"""Inspection-first CLI for the app-owned Prompt Lab subsystem."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.core.prompt_lab.contracts import (
    ACTIVE_PROMPT_LAB_STATE_KIND,
    EVAL_RUN_KIND,
    EXECUTION_PLAN_KIND,
    PUBLISHED_PROMPT_LAB_PACKAGE_KIND,
    PROMOTION_RECORD_KIND,
    PROMPT_BUILD_ARTIFACT_KIND,
    PROMPT_PROFILE_KIND,
    VALIDATION_SNAPSHOT_KIND,
    BINDING_RECORD_KIND,
    serialize_record,
)
from src.prompt_lab.entrypoints import build_prompt_lab_entrypoints

CLI_KIND_ALIASES = {
    "profiles": PROMPT_PROFILE_KIND,
    "prompt-profiles": PROMPT_PROFILE_KIND,
    "plans": EXECUTION_PLAN_KIND,
    "execution-plans": EXECUTION_PLAN_KIND,
    "bindings": BINDING_RECORD_KIND,
    "artifacts": PROMPT_BUILD_ARTIFACT_KIND,
    "build-artifacts": PROMPT_BUILD_ARTIFACT_KIND,
    "published-packages": PUBLISHED_PROMPT_LAB_PACKAGE_KIND,
    "active-state": ACTIVE_PROMPT_LAB_STATE_KIND,
    "eval-runs": EVAL_RUN_KIND,
    "promotions": PROMOTION_RECORD_KIND,
    "promotion-records": PROMOTION_RECORD_KIND,
    "validation": VALIDATION_SNAPSHOT_KIND,
    "validation-snapshots": VALIDATION_SNAPSHOT_KIND,
}


def _resolve_kind(kind: str) -> str:
    try:
        return CLI_KIND_ALIASES[kind]
    except KeyError as exc:
        raise ValueError(f"Unknown Prompt Lab kind alias: {kind!r}") from exc


def _dump(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prompt-lab",
        description="Inspection-first Prompt Lab CLI",
    )
    parser.add_argument(
        "--project-root",
        default=None,
        help="Project root to inspect. Defaults to the current working directory.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("paths", help="Show Prompt Lab resolved paths")

    list_parser = subparsers.add_parser("list", help="List Prompt Lab records")
    list_parser.add_argument("kind", choices=sorted(CLI_KIND_ALIASES))

    show_parser = subparsers.add_parser("show", help="Show a single Prompt Lab record")
    show_parser.add_argument("kind", choices=sorted(CLI_KIND_ALIASES))
    show_parser.add_argument("record_id")

    subparsers.add_parser("validate", help="Validate stored Prompt Lab design state")
    ops_parser = subparsers.add_parser("ops", help="Show recent Prompt Lab operation log entries")
    ops_parser.add_argument("--limit", type=int, default=20)

    publish_parser = subparsers.add_parser("publish", help="Publish a validated Prompt Lab package")
    publish_parser.add_argument("package_id")
    publish_parser.add_argument("package_name")
    publish_parser.add_argument("execution_plan_id")
    publish_parser.add_argument(
        "--profiles",
        nargs="+",
        required=True,
        dest="prompt_profile_ids",
        help="Prompt profile ids to include in the published package.",
    )
    publish_parser.add_argument(
        "--bindings",
        nargs="+",
        required=True,
        dest="binding_ids",
        help="Binding ids to include in the published package.",
    )
    publish_parser.add_argument("--by", default="cli", dest="published_by")
    publish_parser.add_argument("--notes", default="")

    activate_parser = subparsers.add_parser("activate", help="Activate a published Prompt Lab package")
    activate_parser.add_argument("package_id")
    activate_parser.add_argument("--by", default="cli", dest="activated_by")
    activate_parser.add_argument("--notes", default="")

    subparsers.add_parser("active", help="Show the current active Prompt Lab package state")
    return parser


def main(argv: list[str] | None = None, project_root: str | Path | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(project_root or args.project_root or Path.cwd()).resolve()
    entrypoints = build_prompt_lab_entrypoints(root)
    services = entrypoints.services
    operation_log = services.operation_log

    if args.command == "paths":
        operation_log.record(
            channel="cli",
            action="paths",
            status="ok",
            details={"project_root": str(entrypoints.project_root)},
        )
        _dump(
            {
                "status": "ok",
                "project_root": str(entrypoints.project_root),
                "paths": {
                    field: str(getattr(services.storage.paths, field))
                    for field in services.storage.paths.__dataclass_fields__
                },
                "metadata": services.metadata,
            }
        )
        return 0

    if args.command == "list":
        kind = _resolve_kind(args.kind)
        if kind in {EVAL_RUN_KIND, PROMOTION_RECORD_KIND, VALIDATION_SNAPSHOT_KIND}:
            records = services.storage.list_history_records(kind)
        else:
            records = services.storage.list_design_objects(kind)
        operation_log.record(
            channel="cli",
            action="list",
            status="ok",
            details={"kind": kind, "count": len(records)},
        )
        _dump(
            {
                "status": "ok",
                "kind": kind,
                "count": len(records),
                "records": records,
            }
        )
        return 0

    if args.command == "show":
        kind = _resolve_kind(args.kind)
        if kind in {EVAL_RUN_KIND, PROMOTION_RECORD_KIND, VALIDATION_SNAPSHOT_KIND}:
            record = services.storage.load_history_record(kind, args.record_id)
        else:
            record = services.storage.load_design_object(kind, args.record_id)
        operation_log.record(
            channel="cli",
            action="show",
            status="ok",
            details={"kind": kind, "record_id": args.record_id},
        )
        _dump(
            {
                "status": "ok",
                "kind": kind,
                "record": serialize_record(record),
            }
        )
        return 0

    if args.command == "validate":
        snapshot = services.validate_state(services.storage)
        services.storage.save_validation_snapshot(snapshot)
        operation_log.record(
            channel="cli",
            action="validate",
            status=snapshot.status,
            details={"snapshot_id": snapshot.id},
        )
        _dump(
            {
                "status": snapshot.status,
                "record": serialize_record(snapshot),
            }
        )
        return 0

    if args.command == "ops":
        operation_log.record(
            channel="cli",
            action="ops",
            status="ok",
            details={"limit": args.limit},
        )
        _dump(
            {
                "status": "ok",
                "records": services.operation_log.tail(limit=args.limit),
            }
        )
        return 0

    if args.command == "publish":
        result = services.package_service.publish_package(
            package_id=args.package_id,
            package_name=args.package_name,
            execution_plan_id=args.execution_plan_id,
            prompt_profile_ids=args.prompt_profile_ids,
            binding_ids=args.binding_ids,
            published_by=args.published_by,
            notes=args.notes,
        )
        operation_log.record(
            channel="cli",
            action="publish",
            status="ok",
            details={"package_id": result.package.id},
        )
        _dump(
            {
                "status": "ok",
                "package": serialize_record(result.package),
                "validation_snapshot_id": result.validation_snapshot_id,
                "promotion_record_id": result.promotion_record_id,
            }
        )
        return 0

    if args.command == "activate":
        active_state = services.package_service.activate_package(
            args.package_id,
            activated_by=args.activated_by,
            notes=args.notes,
        )
        operation_log.record(
            channel="cli",
            action="activate",
            status="ok",
            details={"package_id": active_state.published_package_id},
        )
        _dump(
            {
                "status": "ok",
                "record": serialize_record(active_state),
            }
        )
        return 0

    if args.command == "active":
        active_state = services.package_service.get_active_state()
        operation_log.record(
            channel="cli",
            action="active",
            status="ok" if active_state is not None else "empty",
            details={"package_id": active_state.published_package_id if active_state is not None else ""},
        )
        if active_state is None:
            _dump(
                {
                    "status": "empty",
                    "record": None,
                }
            )
        else:
            package = services.package_service.resolve_active_package()
            _dump(
                {
                    "status": "ok",
                    "record": serialize_record(active_state),
                    "package": serialize_record(package) if package is not None else None,
                }
            )
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
