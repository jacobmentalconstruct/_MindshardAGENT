"""Primary Prompt Lab subsystem entrypoint.

This is intentionally named `main.py` instead of `app.py` to avoid confusing
the Prompt Lab subsystem with the main MindshardAGENT application entrypoint.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.prompt_lab.entrypoints import build_prompt_lab_entrypoints
from src.prompt_lab.workbench import run_prompt_lab_workbench


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prompt-lab-main", description="Prompt Lab subsystem entrypoint")
    parser.add_argument(
        "--project-root",
        default=None,
        help="Project root for Prompt Lab state. Defaults to the current working directory.",
    )
    parser.add_argument(
        "--describe",
        action="store_true",
        help="Print a JSON status payload instead of launching the dedicated workbench.",
    )
    return parser


def main(argv: list[str] | None = None, project_root: str | Path | None = None) -> int:
    args = _build_parser().parse_args(argv)
    resolved_root = Path(project_root or args.project_root or Path.cwd()).resolve()
    entrypoints = build_prompt_lab_entrypoints(resolved_root)
    if not args.describe:
        return run_prompt_lab_workbench(entrypoints.project_root)
    payload = {
        "status": "phase_2",
        "entrypoint": "prompt_lab.main",
        "project_root": str(entrypoints.project_root),
        "message": (
            "Prompt Lab now includes a dedicated minimal workbench over the "
            "settled services, MCP surface, operation monitoring, and main-app "
            "summary bridge. Use --describe for status-only output."
        ),
        "metadata": entrypoints.services.metadata,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
