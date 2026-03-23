"""
FILE: journal_manifest.py
ROLE: Manifest inspection tool for _app-journal.
WHAT IT DOES: Returns the vendored package manifest plus the embedded database manifest for a project journal.
HOW TO USE:
  - Metadata: python _app-journal/tools/journal_manifest.py metadata
  - Run: python _app-journal/tools/journal_manifest.py run --input-json "{\"project_root\":\"C:/path/to/project\"}"
INPUT OBJECT:
  - project_root: optional project root
  - db_path: optional explicit SQLite file path
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result
from lib.journal_store import get_manifest


FILE_METADATA = {
    "tool_name": "journal_manifest",
    "version": "1.0.0",
    "entrypoint": "tools/journal_manifest.py",
    "category": "introspection",
    "summary": "Inspect the vendored package manifest and embedded DB manifest for an app journal.",
    "mcp_name": "journal_manifest",
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
    result = get_manifest(
        project_root=arguments.get("project_root"),
        db_path=arguments.get("db_path"),
    )
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
