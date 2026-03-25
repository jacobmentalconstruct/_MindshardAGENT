"""SQLite-backed session persistence.

Supports: new, save, load, delete, branch, list.
Database lives at .mindshard/sessions/sessions.db by default.
"""

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.sessions.sqlite_schema import SCHEMA_SQL, run_migrations
from src.core.utils.ids import make_session_id, make_message_id
from src.core.utils.clock import utc_iso
from src.core.runtime.runtime_logger import get_logger

log = get_logger("session_store")


def auto_session_title() -> str:
    """Generate a unique session title from current timestamp.

    Format: 'Session Mar-17 14:32'  (compact, human-scannable, unique per minute)
    """
    now = datetime.now(timezone.utc)
    return now.strftime("Session %b-%d %H:%M")


class SessionStore:
    """SQLite session persistence manager."""

    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()  # RLock: methods may call other locked methods
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()
        run_migrations(self._conn)
        log.info("SessionStore initialized at %s", self._db_path)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ── Session CRUD ──────────────────────────────────

    def new_session(self, title: str = "", model: str = "",
                    sandbox_root: str = "", parent_id: str | None = None) -> str:
        if not title:
            title = auto_session_title()
        sid = make_session_id()
        now = utc_iso()
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions (session_id, title, parent_session_id, "
                "created_at, updated_at, active_model, sandbox_root) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (sid, title, parent_id, now, now, model, sandbox_root),
            )
            self._conn.commit()
        log.info("New session: %s (%s)", sid, title)
        return sid

    def save_session(self, session_id: str, title: str | None = None,
                     model: str | None = None) -> None:
        updates = ["updated_at = ?"]
        params: list[Any] = [utc_iso()]
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if model is not None:
            updates.append("active_model = ?")
            params.append(model)
        params.append(session_id)
        with self._lock:
            self._conn.execute(
                f"UPDATE sessions SET {', '.join(updates)} WHERE session_id = ?", params)
            self._conn.commit()
        log.info("Session saved: %s", session_id)

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            # Unlink child branches first so FK doesn't block delete
            self._conn.execute(
                "UPDATE sessions SET parent_session_id = NULL WHERE parent_session_id = ?",
                (session_id,))
            self._conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            self._conn.commit()
        log.info("Session deleted: %s", session_id)

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT session_id, title, parent_session_id, created_at, updated_at, "
                "active_model FROM sessions ORDER BY updated_at DESC")
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,))
            cols = [d[0] for d in cur.description]
            row = cur.fetchone()
            return dict(zip(cols, row)) if row else None

    # ── Messages ──────────────────────────────────────

    def add_message(self, session_id: str, role: str, content: str,
                    model_name: str = "", token_in: int = 0, token_out: int = 0,
                    inference_ms: float = 0, tool_count: int = 0) -> str:
        mid = make_message_id()
        with self._lock:
            self._conn.execute(
                "INSERT INTO messages (message_id, session_id, role, content, created_at, "
                "model_name, token_in_est, token_out_est, inference_ms, tool_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (mid, session_id, role, content, utc_iso(), model_name,
                 token_in, token_out, inference_ms, tool_count),
            )
            self._conn.commit()
        return mid

    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at",
                (session_id,))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def message_count(self, session_id: str) -> int:
        """Return the number of messages in a session."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,))
            return cur.fetchone()[0]

    def purge_empty(self, keep_sid: str | None = None) -> int:
        """Delete sessions with zero messages. Optionally keep one by ID.

        Returns count of purged sessions.

        The SELECT and all deletes run under a single lock acquisition so that
        no other thread can create or modify sessions between the read and the
        deletes (RLock allows the nested delete_session calls to re-acquire).
        """
        with self._lock:
            cur = self._conn.execute(
                "SELECT session_id FROM sessions WHERE session_id NOT IN "
                "(SELECT DISTINCT session_id FROM messages)")
            empty_sids = [row[0] for row in cur.fetchall()]
            purged = 0
            for sid in empty_sids:
                if sid == keep_sid:
                    continue
                self.delete_session(sid)
                purged += 1
        if purged:
            log.info("Purged %d empty session(s)", purged)
        return purged

    # ── Per-session command policy ─────────────────────

    def get_command_policy(self, session_id: str) -> dict:
        """Return the per-session command policy overrides (or empty dict).

        Policy JSON format:
          {"allow_add": ["npm", "yarn"], "allow_remove": ["git"], "notes": "..."}
        - allow_add: extra commands permitted beyond the global allowlist
        - allow_remove: global-allowed commands blocked for this session
        """
        import json
        with self._lock:
            cur = self._conn.execute(
                "SELECT command_policy_json FROM sessions WHERE session_id = ?",
                (session_id,))
            row = cur.fetchone()
        if not row or not row[0]:
            return {}
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_command_policy(self, session_id: str, policy: dict) -> None:
        """Save per-session command policy overrides."""
        import json
        policy_json = json.dumps(policy) if policy else ""
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET command_policy_json = ?, updated_at = ? "
                "WHERE session_id = ?",
                (policy_json, utc_iso(), session_id))
            self._conn.commit()
        log.info("Command policy updated for session %s", session_id)

    # ── Branching ─────────────────────────────────────

    def branch_session(self, source_session_id: str, title: str = "",
                       up_to_message_id: str | None = None) -> str:
        """Create a branch copying messages from source up to a given message."""
        source = self.get_session(source_session_id)
        if not source:
            raise ValueError(f"Source session not found: {source_session_id}")

        branch_title = title or f"Branch of {source['title']}"
        new_sid = self.new_session(
            title=branch_title,
            model=source.get("active_model", ""),
            sandbox_root=source.get("sandbox_root", ""),
            parent_id=source_session_id,
        )

        messages = self.get_messages(source_session_id)
        for msg in messages:
            self.add_message(
                session_id=new_sid,
                role=msg["role"],
                content=msg["content"],
                model_name=msg.get("model_name", ""),
                token_in=msg.get("token_in_est", 0),
                token_out=msg.get("token_out_est", 0),
                inference_ms=msg.get("inference_ms", 0),
                tool_count=msg.get("tool_count", 0),
            )
            if up_to_message_id and msg["message_id"] == up_to_message_id:
                break

        log.info("Branched session %s -> %s (%d messages)",
                 source_session_id, new_sid, len(messages))
        return new_sid

    # ── Tool runs ─────────────────────────────────────

    def add_tool_run(self, session_id: str, message_id: str | None,
                     tool_name: str, command_text: str, cwd: str,
                     stdout: str, stderr: str, exit_code: int | None,
                     started_at: str, finished_at: str) -> str:
        from src.core.utils.ids import make_tool_run_id
        trid = make_tool_run_id()
        with self._lock:
            self._conn.execute(
                "INSERT INTO tool_runs (tool_run_id, session_id, message_id, tool_name, "
                "command_text, cwd, stdout, stderr, exit_code, started_at, finished_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (trid, session_id, message_id, tool_name, command_text, cwd,
                 stdout, stderr, exit_code, started_at, finished_at),
            )
            self._conn.commit()
        return trid
