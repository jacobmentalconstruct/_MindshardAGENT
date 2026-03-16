"""Simple synchronous event bus for internal runtime coordination.

Supports typed event names and observer callbacks.
Thread-safe for Tkinter's after()-based dispatch pattern.
"""

import threading
from typing import Any, Callable

from src.core.runtime.runtime_logger import get_logger

log = get_logger("event_bus")

Callback = Callable[[dict[str, Any]], None]


class EventBus:
    """Lightweight publish/subscribe event bus."""

    def __init__(self):
        self._subscribers: dict[str, list[Callback]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event_type: str, callback: Callback) -> None:
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(callback)

    def unsubscribe(self, event_type: str, callback: Callback) -> None:
        with self._lock:
            listeners = self._subscribers.get(event_type, [])
            if callback in listeners:
                listeners.remove(callback)

    def emit(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        data = data or {}
        with self._lock:
            listeners = list(self._subscribers.get(event_type, []))

        for cb in listeners:
            try:
                cb(data)
            except Exception:
                log.exception("Error in event handler for %s", event_type)
