"""Primary Prompt Lab subsystem entrypoint.

This is intentionally named `main.py` instead of `app.py` to avoid confusing
the Prompt Lab subsystem with the main MindshardAGENT application entrypoint.
"""

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
        "status": "phase_1a",
        "entrypoint": "prompt_lab.main",
        "project_root": str(entrypoints.project_root),
        "message": "Prompt Lab foundations are present. Use the CLI for inspection commands while UI/runtime integration remains deferred.",
        "metadata": entrypoints.services.metadata,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
