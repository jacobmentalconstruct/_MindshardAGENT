"""
FILE: journal_query.py
ROLE: Query tool for _app-journal.
WHAT IT DOES: Retrieves recent or filtered journal entries from the shared SQLite store.
HOW TO USE:
  - Metadata: python _app-journal/tools/journal_query.py metadata
  - Run: python _app-journal/tools/journal_query.py run --input-json "{...}"
INPUT OBJECT:
  - project_root: optional project root
  - db_path: optional explicit SQLite file path
  - entry_uid: optional exact entry lookup
  - query: optional search text
  - kind: optional filter
  - source: optional filter
  - status: optional filter
  - tags: optional list or comma-separated string
  - limit: optional integer, defaults 50
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result
from lib.journal_store import get_entry, parse_tags, query_entries


FILE_METADATA = {
    "tool_name": "journal_query",
    "version": "1.0.0",
    "entrypoint": "tools/journal_query.py",
    "category": "query",
    "summary": "Query or fetch journal entries from the shared SQLite journal.",
    "mcp_name": "journal_query",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_root": {"type": "string"},
            "db_path": {"type": "string"},
            "entry_uid": {"type": "string"},
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
            "limit": {"type": "integer", "default": 50}
        },
        "additionalProperties": False
    }
}


def run(arguments: dict) -> dict:
    if arguments.get("entry_uid"):
        result = {
            "entry": get_entry(
                entry_uid=str(arguments["entry_uid"]),
                project_root=arguments.get("project_root"),
                db_path=arguments.get("db_path"),
            )
        }
    else:
        result = query_entries(
            project_root=arguments.get("project_root"),
            db_path=arguments.get("db_path"),
            query=str(arguments.get("query", "")),
            kind=str(arguments.get("kind", "")),
            source=str(arguments.get("source", "")),
            status=str(arguments.get("status", "")),
            tags=parse_tags(arguments.get("tags")),
            limit=int(arguments.get("limit", 50)),
        )
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
