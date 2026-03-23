"""
FILE: journal_store.py
ROLE: Shared SQLite store for _app-journal.
WHAT IT DOES: Creates the project journal database, writes and updates entries, queries notes, and exports views for both MCP tools and the Tkinter UI.
HOW TO USE:
  - Import from tools/ or ui/
  - Call `initialize_store(...)` before using the database
  - Use `write_entry`, `query_entries`, `get_entry`, and `export_entries`
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from common import ensure_dir, now_stamp, read_json, write_json


SCHEMA = """
CREATE TABLE IF NOT EXISTS journal_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journal_migrations (
    schema_version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL,
    notes TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_uid TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    source TEXT NOT NULL,
    author TEXT NOT NULL,
    status TEXT NOT NULL,
    importance INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    related_path TEXT NOT NULL,
    related_ref TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_journal_entries_updated_at ON journal_entries(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_journal_entries_kind ON journal_entries(kind);
CREATE INDEX IF NOT EXISTS idx_journal_entries_source ON journal_entries(source);
CREATE INDEX IF NOT EXISTS idx_journal_entries_status ON journal_entries(status);
"""

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_MANIFEST_PATH = PACKAGE_ROOT / "tool_manifest.json"
SCHEMA_VERSION = "1.0.0"
SQLITE_USER_VERSION = 1


def _resolve_project_root(project_root: str | Path | None) -> Path:
    if project_root:
        return Path(project_root).resolve()
    return Path.cwd().resolve()


def resolve_paths(project_root: str | Path | None = None, db_path: str | Path | None = None) -> dict[str, str]:
    if db_path:
        resolved_db_path = Path(db_path).resolve()
        docs_dir = resolved_db_path.parent.parent if resolved_db_path.parent.name == "_journalDB" else resolved_db_path.parent
        project_root_path = docs_dir.parent if docs_dir.name == "_docs" else resolved_db_path.parent
    else:
        project_root_path = _resolve_project_root(project_root)
        resolved_db_path = project_root_path / "_docs" / "_journalDB" / "app_journal.sqlite3"

    docs_root = project_root_path / "_docs"
    db_dir = docs_root / "_journalDB"
    app_dir = docs_root / "_AppJOURNAL"
    exports_dir = app_dir / "exports"
    config_path = app_dir / "journal_config.json"

    return {
        "project_root": str(project_root_path),
        "docs_root": str(docs_root),
        "db_dir": str(db_dir),
        "db_path": str(resolved_db_path),
        "app_dir": str(app_dir),
        "exports_dir": str(exports_dir),
        "config_path": str(config_path),
    }


def _connect(db_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    return connection


def _package_manifest() -> dict[str, Any]:
    return read_json(PACKAGE_MANIFEST_PATH)


def _db_manifest(paths: dict[str, str]) -> dict[str, Any]:
    package_manifest = _package_manifest()
    return {
        "db_manifest_version": "1.0",
        "schema_version": SCHEMA_VERSION,
        "sqlite_user_version": SQLITE_USER_VERSION,
        "package_name": package_manifest.get("name", "app-journal"),
        "package_manifest_version": package_manifest.get("manifest_version", "1.0"),
        "package_status": package_manifest.get("status", "active"),
        "package_description": package_manifest.get("description", ""),
        "db_schema": {
            "table_names": ["journal_meta", "journal_migrations", "journal_entries"],
            "entry_primary_id": "entry_uid",
            "metadata_store": "journal_meta",
            "migration_store": "journal_migrations",
            "schema_version": SCHEMA_VERSION,
        },
        "project_convention": {
            "project_root": paths["project_root"],
            "db_path": paths["db_path"],
            "app_dir": paths["app_dir"],
            "exports_dir": paths["exports_dir"],
        },
        "agent_entrypoints": {
            "mcp": "mcp_server.py",
            "cli_tools": [
                "tools/journal_init.py",
                "tools/journal_write.py",
                "tools/journal_query.py",
                "tools/journal_export.py",
                "tools/journal_manifest.py",
            ],
        },
        "notes": [
            "The database is intended to be self-describing enough for an agent to inspect and use it directly.",
            "The package manifest on disk remains the source of truth for the vendored tool folder.",
        ],
    }


def _normalize_tags(tags: list[str] | None) -> list[str]:
    values = []
    seen = set()
    for raw in tags or []:
        tag = str(raw).strip()
        if tag and tag not in seen:
            values.append(tag)
            seen.add(tag)
    return values


def _row_to_entry(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "entry_uid": row["entry_uid"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "kind": row["kind"],
        "source": row["source"],
        "author": row["author"],
        "status": row["status"],
        "importance": row["importance"],
        "title": row["title"],
        "body": row["body"],
        "tags": json.loads(row["tags_json"]),
        "related_path": row["related_path"],
        "related_ref": row["related_ref"],
        "metadata": json.loads(row["metadata_json"]),
    }


def initialize_store(project_root: str | Path | None = None, db_path: str | Path | None = None) -> dict[str, str]:
    paths = resolve_paths(project_root=project_root, db_path=db_path)
    ensure_dir(Path(paths["db_dir"]))
    ensure_dir(Path(paths["app_dir"]))
    ensure_dir(Path(paths["exports_dir"]))
    package_manifest = _package_manifest()
    db_manifest = _db_manifest(paths)

    with _connect(paths["db_path"]) as connection:
        connection.executescript(SCHEMA)
        connection.execute(f"PRAGMA user_version = {SQLITE_USER_VERSION}")
        connection.execute(
            "INSERT OR REPLACE INTO journal_meta(key, value) VALUES(?, ?)",
            ("project_root", paths["project_root"]),
        )
        connection.execute(
            "INSERT OR IGNORE INTO journal_meta(key, value) VALUES(?, ?)",
            ("initialized_at", now_stamp()),
        )
        connection.execute(
            "INSERT OR REPLACE INTO journal_meta(key, value) VALUES(?, ?)",
            ("package_manifest_json", json.dumps(package_manifest, sort_keys=True)),
        )
        connection.execute(
            "INSERT OR REPLACE INTO journal_meta(key, value) VALUES(?, ?)",
            ("db_manifest_json", json.dumps(db_manifest, sort_keys=True)),
        )
        connection.execute(
            "INSERT OR REPLACE INTO journal_meta(key, value) VALUES(?, ?)",
            ("schema_version", SCHEMA_VERSION),
        )
        connection.execute(
            "INSERT OR REPLACE INTO journal_meta(key, value) VALUES(?, ?)",
            ("sqlite_user_version", str(SQLITE_USER_VERSION)),
        )
        connection.execute(
            "INSERT OR IGNORE INTO journal_migrations(schema_version, applied_at, notes) VALUES(?, ?, ?)",
            (SCHEMA_VERSION, now_stamp(), "Initial vendorable app-journal schema."),
        )
        connection.commit()

    write_json(
        Path(paths["config_path"]),
        {
            "project_root": paths["project_root"],
            "db_path": paths["db_path"],
            "ui_hint": "python .dev-tools/_app-journal/launch_ui.py --project-root <project>",
            "mcp_hint": "python .dev-tools/_app-journal/mcp_server.py",
            "manifest_hint": "python .dev-tools/_app-journal/tools/journal_manifest.py run --input-json '{\"project_root\":\"...\"}'",
        },
    )
    write_json(Path(paths["app_dir"]) / "db_manifest.json", db_manifest)
    return paths


def get_manifest(*, project_root: str | Path | None = None, db_path: str | Path | None = None) -> dict[str, Any]:
    paths = initialize_store(project_root=project_root, db_path=db_path)
    with _connect(paths["db_path"]) as connection:
        rows = connection.execute(
            "SELECT key, value FROM journal_meta WHERE key IN ('project_root', 'initialized_at', 'package_manifest_json', 'db_manifest_json', 'schema_version', 'sqlite_user_version')"
        ).fetchall()
        entry_count_row = connection.execute("SELECT COUNT(*) AS count FROM journal_entries").fetchone()
        migration_rows = connection.execute(
            "SELECT schema_version, applied_at, notes FROM journal_migrations ORDER BY applied_at ASC"
        ).fetchall()

    meta = {row["key"]: row["value"] for row in rows}
    package_manifest = json.loads(meta.get("package_manifest_json", "{}"))
    db_manifest = json.loads(meta.get("db_manifest_json", "{}"))
    return {
        "paths": paths,
        "package_manifest_path": str(PACKAGE_MANIFEST_PATH),
        "package_manifest": package_manifest,
        "db_manifest": db_manifest,
        "db_summary": {
            "initialized_at": meta.get("initialized_at", ""),
            "schema_version": meta.get("schema_version", ""),
            "sqlite_user_version": int(meta.get("sqlite_user_version", "0") or 0),
            "entry_count": int(entry_count_row["count"]) if entry_count_row else 0,
        },
        "migrations": [
            {
                "schema_version": row["schema_version"],
                "applied_at": row["applied_at"],
                "notes": row["notes"],
            }
            for row in migration_rows
        ],
    }


def write_entry(
    *,
    project_root: str | Path | None = None,
    db_path: str | Path | None = None,
    action: str = "create",
    entry_uid: str | None = None,
    title: str = "",
    body: str = "",
    kind: str = "note",
    source: str | None = None,
    author: str | None = None,
    tags: list[str] | None = None,
    status: str | None = None,
    importance: int | None = None,
    related_path: str | None = None,
    related_ref: str | None = None,
    metadata: dict[str, Any] | None = None,
    append_text: str = "",
) -> dict[str, Any]:
    paths = initialize_store(project_root=project_root, db_path=db_path)
    now = now_stamp()
    normalized_tags = _normalize_tags(tags)
    payload_metadata = metadata or {}

    with _connect(paths["db_path"]) as connection:
        if action == "create":
            if not title.strip() and not body.strip():
                raise ValueError("Provide at least a title or body for a new journal entry.")
            new_uid = entry_uid or f"journal_{uuid.uuid4().hex[:12]}"
            connection.execute(
                """
                INSERT INTO journal_entries(
                    entry_uid, created_at, updated_at, kind, source, author, status,
                    importance, title, body, tags_json, related_path, related_ref, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_uid,
                    now,
                    now,
                    kind,
                    source or "agent",
                    author or "",
                    status or "open",
                    int(importance or 0),
                    title.strip() or "(untitled)",
                    body.strip(),
                    json.dumps(normalized_tags),
                    related_path or "",
                    related_ref or "",
                    json.dumps(payload_metadata),
                ),
            )
            connection.commit()
            return get_entry(entry_uid=new_uid, db_path=paths["db_path"])

        if not entry_uid:
            raise ValueError("entry_uid is required for update or append.")

        if action == "append":
            existing = get_entry(entry_uid=entry_uid, db_path=paths["db_path"])
            joiner = "\n\n" if existing["body"].strip() and append_text.strip() else ""
            updated_body = f"{existing['body']}{joiner}{append_text.strip()}".strip()
            connection.execute(
                """
                UPDATE journal_entries
                SET body = ?, updated_at = ?, status = ?, importance = ?
                WHERE entry_uid = ?
                """,
                (
                    updated_body,
                    now,
                    status or existing["status"],
                    int(importance if importance is not None else existing["importance"]),
                    entry_uid,
                ),
            )
            connection.commit()
            return get_entry(entry_uid=entry_uid, db_path=paths["db_path"])

        if action == "update":
            existing = get_entry(entry_uid=entry_uid, db_path=paths["db_path"])
            connection.execute(
                """
                UPDATE journal_entries
                SET title = ?, body = ?, kind = ?, source = ?, author = ?, status = ?,
                    importance = ?, tags_json = ?, related_path = ?, related_ref = ?,
                    metadata_json = ?, updated_at = ?
                WHERE entry_uid = ?
                """,
                (
                    title.strip() or existing["title"],
                    body if body != "" else existing["body"],
                    kind or existing["kind"],
                    source if source is not None else existing["source"],
                    author if author is not None else existing["author"],
                    status if status is not None else existing["status"],
                    int(importance if importance is not None else existing["importance"]),
                    json.dumps(normalized_tags or existing["tags"]),
                    related_path if related_path is not None else existing["related_path"],
                    related_ref if related_ref is not None else existing["related_ref"],
                    json.dumps(payload_metadata or existing["metadata"]),
                    now,
                    entry_uid,
                ),
            )
            connection.commit()
            return get_entry(entry_uid=entry_uid, db_path=paths["db_path"])

        raise ValueError(f"Unsupported action: {action}")


def get_entry(*, entry_uid: str, project_root: str | Path | None = None, db_path: str | Path | None = None) -> dict[str, Any]:
    paths = initialize_store(project_root=project_root, db_path=db_path)
    with _connect(paths["db_path"]) as connection:
        row = connection.execute(
            "SELECT * FROM journal_entries WHERE entry_uid = ?",
            (entry_uid,),
        ).fetchone()
    if row is None:
        raise ValueError(f"Journal entry not found: {entry_uid}")
    return _row_to_entry(row)


def query_entries(
    *,
    project_root: str | Path | None = None,
    db_path: str | Path | None = None,
    query: str = "",
    kind: str = "",
    source: str = "",
    status: str = "",
    tags: list[str] | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    paths = initialize_store(project_root=project_root, db_path=db_path)
    conditions = []
    values: list[Any] = []

    if query.strip():
        needle = f"%{query.strip().lower()}%"
        conditions.append("(LOWER(title) LIKE ? OR LOWER(body) LIKE ? OR LOWER(tags_json) LIKE ?)")
        values.extend([needle, needle, needle])
    if kind.strip():
        conditions.append("kind = ?")
        values.append(kind.strip())
    if source.strip():
        conditions.append("source = ?")
        values.append(source.strip())
    if status.strip():
        conditions.append("status = ?")
        values.append(status.strip())

    for tag in _normalize_tags(tags):
        conditions.append("tags_json LIKE ?")
        values.append(f'%"{tag}"%')

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    sql = f"""
    SELECT * FROM journal_entries
    {where_clause}
    ORDER BY updated_at DESC, created_at DESC, id DESC
    LIMIT ?
    """
    values.append(max(1, int(limit)))

    with _connect(paths["db_path"]) as connection:
        rows = connection.execute(sql, values).fetchall()
        count_row = connection.execute("SELECT COUNT(*) AS count FROM journal_entries").fetchone()

    entries = [_row_to_entry(row) for row in rows]
    return {
        "paths": paths,
        "summary": {
            "entry_count": len(entries),
            "total_entries": int(count_row["count"]) if count_row else 0,
        },
        "entries": entries,
    }


def export_entries(
    *,
    project_root: str | Path | None = None,
    db_path: str | Path | None = None,
    query: str = "",
    kind: str = "",
    source: str = "",
    status: str = "",
    tags: list[str] | None = None,
    limit: int = 200,
    format_name: str = "markdown",
) -> dict[str, Any]:
    result = query_entries(
        project_root=project_root,
        db_path=db_path,
        query=query,
        kind=kind,
        source=source,
        status=status,
        tags=tags,
        limit=limit,
    )
    paths = result["paths"]
    exports_dir = Path(paths["exports_dir"])
    stamp = now_stamp().replace(":", "").replace("-", "")

    if format_name == "json":
        export_path = exports_dir / f"journal_export_{stamp}.json"
        write_json(export_path, result)
        return {
            "export_path": str(export_path),
            "format": format_name,
            "entry_count": len(result["entries"]),
        }

    lines = ["# App Journal Export", ""]
    for entry in result["entries"]:
        lines.extend(
            [
                f"## {entry['title']}",
                f"- entry_uid: `{entry['entry_uid']}`",
                f"- kind: `{entry['kind']}`",
                f"- source: `{entry['source']}`",
                f"- status: `{entry['status']}`",
                f"- updated_at: `{entry['updated_at']}`",
                f"- tags: `{', '.join(entry['tags'])}`",
                "",
                entry["body"],
                "",
            ]
        )
    export_path = exports_dir / f"journal_export_{stamp}.md"
    export_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {
        "export_path": str(export_path),
        "format": "markdown",
        "entry_count": len(result["entries"]),
    }


def parse_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return _normalize_tags([str(item) for item in value])
    if isinstance(value, str):
        return _normalize_tags([part.strip() for part in value.split(",")])
    raise ValueError("tags must be a list of strings or a comma-separated string")
