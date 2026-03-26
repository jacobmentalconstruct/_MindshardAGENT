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
    EVAL_RUN_KIND,
    EXECUTION_PLAN_KIND,
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
    return parser


def main(argv: list[str] | None = None, project_root: str | Path | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(project_root or args.project_root or Path.cwd()).resolve()
    entrypoints = build_prompt_lab_entrypoints(root)
    services = entrypoints.services

    if args.command == "paths":
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
        _dump(
            {
                "status": snapshot.status,
                "record": serialize_record(snapshot),
            }
        )
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
