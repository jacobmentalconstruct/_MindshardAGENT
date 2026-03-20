"""Memory vault — global SQLite index of all detached Mindshard projects.

Stored at: <vault_dir>/vault_index.db
Archives at: <vault_dir>/<project>_<ts>.zip

Schema:
  projects table:
    id          INTEGER PRIMARY KEY
    project_name TEXT
    project_root TEXT     -- original working copy path
    source_path  TEXT     -- original source (if any)
    profile      TEXT     -- standard / self_edit
    purpose      TEXT
    goal         TEXT
    detached_at  TEXT     -- ISO timestamp
    archive_path TEXT     -- path to the zip bundle
    snapshot_hash TEXT
"""
from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Any

from src.core.runtime.runtime_logger import get_logger

log = get_logger("memory_vault")

_DDL = """
CREATE TABLE IF NOT EXISTS projects (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name  TEXT NOT NULL,
    project_root  TEXT,
    source_path   TEXT,
    profile       TEXT DEFAULT 'standard',
    purpose       TEXT,
    goal          TEXT,
    detached_at   TEXT,
    archive_path  TEXT,
    snapshot_hash TEXT
);
"""


def _default_vault_dir() -> Path:
    """Return the default global vault directory."""
    return Path.home() / ".mindshard_vault"


class MemoryVault:
    """Global index of detached Mindshard projects."""

    def __init__(self, vault_dir: str | Path | None = None):
        self.vault_dir = Path(vault_dir).resolve() if vault_dir else _default_vault_dir()
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self.vault_dir / "vault_index.db"
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_DDL)
        self._conn.commit()
        log.info("Memory vault: %s", self._db_path)

    def register(self, archive_result: dict, project_meta: dict | None = None) -> int:
        """Register a newly archived project. Returns row ID."""
        meta = project_meta or {}
        row = {
            "project_name": archive_result.get("project_name", ""),
            "project_root": meta.get("project_root", ""),
            "source_path": meta.get("source_path", ""),
            "profile": meta.get("profile", "standard"),
            "purpose": meta.get("project_purpose", ""),
            "goal": meta.get("current_goal", ""),
            "detached_at": archive_result.get("ts", ""),
            "archive_path": archive_result.get("archive_path", ""),
            "snapshot_hash": archive_result.get("snapshot_hash", ""),
        }
        cur = self._conn.execute(
            """INSERT INTO projects
               (project_name, project_root, source_path, profile,
                purpose, goal, detached_at, archive_path, snapshot_hash)
               VALUES
               (:project_name, :project_root, :source_path, :profile,
                :purpose, :goal, :detached_at, :archive_path, :snapshot_hash)""",
            row,
        )
        self._conn.commit()
        log.info("Vault: registered project '%s'", row["project_name"])
        return cur.lastrowid

    def list_projects(self, limit: int = 50) -> list[dict[str, Any]]:
        """List recent detached projects, newest first."""
        cur = self._conn.execute(
            "SELECT * FROM projects ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in cur.fetchall()]

    def get_project(self, project_id: int) -> dict[str, Any] | None:
        cur = self._conn.execute("SELECT * FROM projects WHERE id=?", (project_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def close(self) -> None:
        self._conn.close()

    @property
    def db_path(self) -> Path:
        return self._db_path
