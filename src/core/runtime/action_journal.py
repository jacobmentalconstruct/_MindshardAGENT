"""Action journal — structured log of significant operations for agent orientation.

Records every meaningful event (project load, sync, session switch, tool use,
file operations, config changes) so the agent can query recent history and
orient itself after context loss or between operations.

Stored as JSON-lines at _sandbox/_logs/action_journal.jsonl.
Queryable by action type, recency, or full dump.

This is the agent's "short-term memory" for what has happened in the workspace.
It answers: "What was I doing? What changed? What happened since my last turn?"
"""

import json
from pathlib import Path
from typing import Any

from src.core.utils.clock import utc_iso
from src.core.runtime.runtime_logger import get_logger

log = get_logger("action_journal")

# Action categories
PROJECT_LOAD = "project_load"       # Source loaded into sandbox
PROJECT_SYNC = "project_sync"       # Sandbox synced back to source
FILE_WRITE = "file_write"           # Agent wrote a file
FILE_READ = "file_read"             # Agent read a file
TOOL_EXEC = "tool_exec"             # CLI tool executed
SESSION_START = "session_start"     # New or loaded session
SESSION_SWITCH = "session_switch"   # Switched active session
CONFIG_CHANGE = "config_change"     # Config changed (model, docker, etc.)
DOCKER_EVENT = "docker_event"       # Docker state change
USER_ACTION = "user_action"         # Manual user action (button click, etc.)
AGENT_TURN = "agent_turn"           # Agent completed a response turn


class ActionJournal:
    """Append-only structured event log for agent orientation."""

    def __init__(self, sandbox_root: str | Path):
        self._path = Path(sandbox_root).resolve() / "_logs" / "action_journal.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        log.info("ActionJournal active: %s", self._path)

    def record(self, action: str, summary: str,
               details: dict[str, Any] | None = None) -> None:
        """Record an action.

        Args:
            action: Action category constant (e.g. PROJECT_LOAD, FILE_WRITE)
            summary: One-line human-readable summary
            details: Optional structured data about the action
        """
        entry = {
            "ts": utc_iso(),
            "action": action,
            "summary": summary,
            "details": details or {},
        }
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            log.error("Failed to write journal entry: %s", e)

    def recent(self, limit: int = 20, action_type: str | None = None) -> list[dict]:
        """Get recent journal entries, optionally filtered by action type.

        Args:
            limit: Maximum entries to return
            action_type: If set, only return entries matching this action

        Returns:
            List of journal entries, newest first.
        """
        if not self._path.exists():
            return []
        entries = []
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entry = json.loads(line)
                        if action_type is None or entry.get("action") == action_type:
                            entries.append(entry)
        except Exception as e:
            log.error("Failed to read journal: %s", e)
        return list(reversed(entries[-limit:]))

    def summary_since(self, n: int = 10) -> str:
        """Build a human-readable summary of the last N actions.

        This is designed to be injected into the agent's prompt context
        so it can orient itself after context loss.
        """
        entries = self.recent(limit=n)
        if not entries:
            return "No recent actions recorded."

        lines = []
        for e in entries:
            ts = e["ts"]
            # Trim to just time portion for readability
            if "T" in ts:
                ts = ts.split("T")[1][:8]
            lines.append(f"[{ts}] {e['action']}: {e['summary']}")
        return "\n".join(lines)

    def last_of_type(self, action_type: str) -> dict | None:
        """Get the most recent entry of a specific action type."""
        entries = self.recent(limit=50, action_type=action_type)
        return entries[0] if entries else None

    def clear(self) -> None:
        """Clear the journal (usually on sandbox reset)."""
        if self._path.exists():
            self._path.unlink()
            log.info("Journal cleared")
