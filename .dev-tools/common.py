"""
FILE: common.py
ROLE: Shared runtime for .final-tools.
WHAT IT DOES: Enforces a uniform metadata shape, CLI contract, and JSON result envelope across every final tool.
HOW TO USE:
  - Import `standard_main` in each tool script.
  - Export `FILE_METADATA`.
  - Export `run(arguments: dict) -> dict`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable


DEFAULT_IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
}


def emit_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=False))


def should_skip_dir(name: str) -> bool:
    return name in DEFAULT_IGNORED_DIRS


def tool_result(tool_name: str, arguments: dict[str, Any], result: Any, *, status: str = "ok") -> dict[str, Any]:
    return {
        "status": status,
        "tool": tool_name,
        "input": arguments,
        "result": result,
    }


def tool_error(tool_name: str, arguments: dict[str, Any], message: str) -> dict[str, Any]:
    return tool_result(tool_name, arguments, {"message": message}, status="error")


def load_input(input_json: str | None, input_file: str | None) -> dict[str, Any]:
    if input_json and input_file:
        raise ValueError("Use either --input-json or --input-file, not both.")
    if input_json:
        payload = json.loads(input_json)
    elif input_file:
        payload = json.loads(Path(input_file).read_text(encoding="utf-8"))
    else:
        payload = {}
    if not isinstance(payload, dict):
        raise ValueError("Tool input must be a JSON object.")
    return payload


def build_standard_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("metadata", help="Print tool metadata as JSON.")

    run_parser = subparsers.add_parser("run", help="Run the tool with a JSON object input.")
    run_parser.add_argument("--input-json", help="Inline JSON object input.")
    run_parser.add_argument("--input-file", help="Path to a JSON file containing the tool input object.")
    return parser


def standard_main(
    metadata: dict[str, Any],
    run_func: Callable[[dict[str, Any]], dict[str, Any]],
    argv: list[str] | None = None,
) -> int:
    parser = build_standard_parser(metadata["summary"])
    args = parser.parse_args(argv)

    if args.command == "metadata":
        emit_json(metadata)
        return 0

    if args.command == "run":
        try:
            payload = load_input(args.input_json, args.input_file)
            emit_json(run_func(payload))
            return 0
        except Exception as exc:
            emit_json(tool_error(metadata["tool_name"], {}, str(exc)))
            return 1

    parser.print_help()
    return 2
