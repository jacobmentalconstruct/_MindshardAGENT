"""
FILE: journal_init.py
ROLE: Bootstrap tool for _app-journal.
WHAT IT DOES: Creates the SQLite journal database and project-local management folders under `_docs`.
HOW TO USE:
  - Metadata: python _app-journal/tools/journal_init.py metadata
  - Run: python _app-journal/tools/journal_init.py run --input-json "{\"project_root\":\"C:/path/to/project\"}"
INPUT OBJECT:
  - project_root: optional project root, defaults to current working directory
  - db_path: optional explicit SQLite file path
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result
from lib.journal_store import initialize_store


FILE_METADATA = {
    "tool_name": "journal_init",
    "version": "1.0.0",
    "entrypoint": "tools/journal_init.py",
    "category": "bootstrap",
    "summary": "Create or verify the project journal database and manager folders.",
    "mcp_name": "journal_init",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_root": {"type": "string"},
            "db_path": {"type": "string"}
        },
        "additionalProperties": False
    }
}


def run(arguments: dict) -> dict:
    paths = initialize_store(
        project_root=arguments.get("project_root"),
        db_path=arguments.get("db_path"),
    )
    return tool_result(FILE_METADATA["tool_name"], arguments, {"paths": paths})


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
