"""MCP stub for the app-owned Prompt Lab subsystem."""

from __future__ import annotations

import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.prompt_lab.entrypoints import build_prompt_lab_entrypoints


def main(project_root: str | Path | None = None) -> int:
    entrypoints = build_prompt_lab_entrypoints(project_root or Path.cwd())
    payload = {
        "status": "scaffold_only",
        "transport": "stdio",
        "subsystem": "prompt_lab",
        "project_root": str(entrypoints.project_root),
        "message": "Prompt Lab MCP server scaffold exists, but no tools are exposed yet.",
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
