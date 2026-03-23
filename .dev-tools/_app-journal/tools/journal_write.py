"""
FILE: journal_write.py
ROLE: Write tool for _app-journal.
WHAT IT DOES: Creates, updates, or appends journal entries in the shared SQLite store.
HOW TO USE:
  - Metadata: python _app-journal/tools/journal_write.py metadata
  - Run: python _app-journal/tools/journal_write.py run --input-json "{...}"
INPUT OBJECT:
  - project_root: optional project root
  - db_path: optional explicit SQLite file path
  - action: create | update | append
  - entry_uid: required for update or append
  - title: optional title
  - body: optional full body
  - append_text: body text to append when action=append
  - kind: optional entry kind
  - source: optional source like user | agent | system
  - author: optional author label
  - tags: optional list or comma-separated string
  - status: optional status
  - importance: optional integer
  - related_path: optional related file path
  - related_ref: optional related symbol or note id
  - metadata: optional object
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result
from lib.journal_store import parse_tags, write_entry


FILE_METADATA = {
    "tool_name": "journal_write",
    "version": "1.0.0",
    "entrypoint": "tools/journal_write.py",
    "category": "write",
    "summary": "Create, update, or append journal entries in the shared SQLite journal.",
    "mcp_name": "journal_write",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_root": {"type": "string"},
            "db_path": {"type": "string"},
            "action": {"type": "string", "enum": ["create", "update", "append"], "default": "create"},
            "entry_uid": {"type": "string"},
            "title": {"type": "string"},
            "body": {"type": "string"},
            "append_text": {"type": "string"},
            "kind": {"type": "string"},
            "source": {"type": "string"},
            "author": {"type": "string"},
            "tags": {
                "oneOf": [
                    {"type": "array", "items": {"type": "string"}},
                    {"type": "string"}
                ]
            },
            "status": {"type": "string"},
            "importance": {"type": "integer"},
            "related_path": {"type": "string"},
            "related_ref": {"type": "string"},
            "metadata": {"type": "object"}
        },
        "additionalProperties": False
    }
}


def run(arguments: dict) -> dict:
    action = str(arguments.get("action", "create"))
    entry = write_entry(
        project_root=arguments.get("project_root"),
        db_path=arguments.get("db_path"),
        action=action,
        entry_uid=arguments.get("entry_uid"),
        title=str(arguments.get("title", "")),
        body=str(arguments.get("body", "")),
        append_text=str(arguments.get("append_text", "")),
        kind=str(arguments.get("kind", "note")),
        source=arguments.get("source"),
        author=arguments.get("author"),
        tags=parse_tags(arguments.get("tags")),
        status=arguments.get("status"),
        importance=arguments.get("importance"),
        related_path=arguments.get("related_path"),
        related_ref=arguments.get("related_ref"),
        metadata=arguments.get("metadata"),
    )
    return tool_result(FILE_METADATA["tool_name"], arguments, {"entry": entry})


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
