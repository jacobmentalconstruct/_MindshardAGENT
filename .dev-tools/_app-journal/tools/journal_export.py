"""
FILE: journal_export.py
ROLE: Export tool for _app-journal.
WHAT IT DOES: Exports filtered journal entries to Markdown or JSON in `_docs/_AppJOURNAL/exports`.
HOW TO USE:
  - Metadata: python _app-journal/tools/journal_export.py metadata
  - Run: python _app-journal/tools/journal_export.py run --input-json "{...}"
INPUT OBJECT:
  - project_root: optional project root
  - db_path: optional explicit SQLite file path
  - query: optional search text
  - kind: optional filter
  - source: optional filter
  - status: optional filter
  - tags: optional list or comma-separated string
  - limit: optional integer, defaults 200
  - format: markdown | json
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result
from lib.journal_store import export_entries, parse_tags


FILE_METADATA = {
    "tool_name": "journal_export",
    "version": "1.0.0",
    "entrypoint": "tools/journal_export.py",
    "category": "export",
    "summary": "Export filtered journal entries to Markdown or JSON.",
    "mcp_name": "journal_export",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_root": {"type": "string"},
            "db_path": {"type": "string"},
            "query": {"type": "string"},
            "kind": {"type": "string"},
            "source": {"type": "string"},
            "status": {"type": "string"},
            "tags": {
                "oneOf": [
                    {"type": "array", "items": {"type": "string"}},
                    {"type": "string"}
                ]
            },
            "limit": {"type": "integer", "default": 200},
            "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"}
        },
        "additionalProperties": False
    }
}


def run(arguments: dict) -> dict:
    result = export_entries(
        project_root=arguments.get("project_root"),
        db_path=arguments.get("db_path"),
        query=str(arguments.get("query", "")),
        kind=str(arguments.get("kind", "")),
        source=str(arguments.get("source", "")),
        status=str(arguments.get("status", "")),
        tags=parse_tags(arguments.get("tags")),
        limit=int(arguments.get("limit", 200)),
        format_name=str(arguments.get("format", "markdown")),
    )
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
