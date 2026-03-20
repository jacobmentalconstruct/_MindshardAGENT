"""Command audit log — persistent record of all executed commands.

Appends a JSON-lines entry for every command attempt (allowed, blocked,
cancelled, succeeded, failed). Lives at .mindshard/logs/audit.jsonl.
"""

import json
from pathlib import Path
from typing import Any

from src.core.utils.clock import utc_iso
from src.core.runtime.runtime_logger import get_logger

log = get_logger("audit_log")


class AuditLog:
    """Append-only JSON-lines audit trail for sandbox commands."""

    def __init__(self, log_path: str | Path):
        self._path = Path(log_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        log.info("AuditLog active: %s", self._path)

    def record(self, command: str, cwd: str, outcome: str,
               exit_code: int | None = None, reason: str = "",
               duration_ms: float = 0) -> None:
        """Append an audit entry.

        Args:
            command: The full command string
            cwd: Working directory
            outcome: "executed", "blocked", "cancelled", "error", "timeout"
            exit_code: Process exit code (None if not executed)
            reason: Why blocked/cancelled, or error message
            duration_ms: Execution time in milliseconds
        """
        entry = {
            "ts": utc_iso(),
            "command": command,
            "cwd": cwd,
            "outcome": outcome,
            "exit_code": exit_code,
            "reason": reason,
            "duration_ms": round(duration_ms, 1),
        }
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            log.error("Failed to write audit entry: %s", e)

    def get_entries(self, limit: int = 100) -> list[dict[str, Any]]:
        """Read recent audit entries."""
        if not self._path.exists():
            return []
        entries = []
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
        except Exception as e:
            log.error("Failed to read audit log: %s", e)
        return entries[-limit:]
