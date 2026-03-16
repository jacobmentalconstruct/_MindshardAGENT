"""UI-facing activity stream for the runtime/log panel.

Maintains an append-only list of activity entries that the UI
subscribes to via callback. Each entry is a typed dict with
timestamp, level, source, and message.
"""

from dataclasses import dataclass, field
from typing import Callable

from src.core.utils.clock import utc_iso


@dataclass
class ActivityEntry:
    timestamp: str
    level: str        # INFO, WARN, ERROR, DEBUG, TOOL, MODEL
    source: str       # subsystem name
    message: str


class ActivityStream:
    """Append-only activity log with UI observer support."""

    def __init__(self, max_entries: int = 2000):
        self._entries: list[ActivityEntry] = []
        self._max = max_entries
        self._listeners: list[Callable[[ActivityEntry], None]] = []

    def push(self, level: str, source: str, message: str) -> ActivityEntry:
        entry = ActivityEntry(
            timestamp=utc_iso(),
            level=level,
            source=source,
            message=message,
        )
        self._entries.append(entry)
        if len(self._entries) > self._max:
            self._entries = self._entries[-self._max:]

        for cb in self._listeners:
            try:
                cb(entry)
            except Exception:
                pass  # UI callback errors must not crash the stream
        return entry

    def info(self, source: str, message: str) -> ActivityEntry:
        return self.push("INFO", source, message)

    def warn(self, source: str, message: str) -> ActivityEntry:
        return self.push("WARN", source, message)

    def error(self, source: str, message: str) -> ActivityEntry:
        return self.push("ERROR", source, message)

    def tool(self, source: str, message: str) -> ActivityEntry:
        return self.push("TOOL", source, message)

    def model(self, source: str, message: str) -> ActivityEntry:
        return self.push("MODEL", source, message)

    def subscribe(self, callback: Callable[[ActivityEntry], None]) -> None:
        self._listeners.append(callback)

    @property
    def entries(self) -> list[ActivityEntry]:
        return list(self._entries)
