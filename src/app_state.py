"""Shared mutable application state.

All state that was previously captured via closures in main() is now held
in a single AppState instance.  Every extracted module receives this object
instead of relying on nonlocal / closure capture.
"""

from __future__ import annotations

import threading
import tkinter as tk
from typing import Any, Callable, Optional

from src.core.config.app_config import AppConfig
from src.core.engine import Engine
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.event_bus import EventBus
from src.core.agent.prompt_tuning_store import PromptTuningStore
from src.core.sessions.session_store import SessionStore
from src.core.sessions.knowledge_store import KnowledgeStore
from src.core.registry.state_registry import StateRegistry
from src.ui.ui_state import UIState


class AppState:
    """Central holder for all mutable app-level state."""

    __slots__ = (
        "config", "log", "activity", "bus", "ui_state", "registry",
        "root", "engine", "prompt_tuning", "window",
        "session_store", "knowledge_store",
        # Lifecycle
        "app_closing", "scheduled_after",
        # Session
        "active_session", "autosave_timer",
        # Streaming
        "streaming_content", "stream_flush_id", "stream_dirty",
        # Confirmation (thread-sync)
        "confirm_result", "gui_confirm_result",
    )

    def __init__(
        self,
        *,
        config: AppConfig,
        log: Any,
        activity: ActivityStream,
        bus: EventBus,
        ui_state: UIState,
        registry: StateRegistry,
        root: tk.Tk,
        engine: Engine,
        prompt_tuning: PromptTuningStore,
        session_store: SessionStore,
        knowledge_store: KnowledgeStore,
    ) -> None:
        self.config = config
        self.log = log
        self.activity = activity
        self.bus = bus
        self.ui_state = ui_state
        self.registry = registry
        self.root = root
        self.engine = engine
        self.prompt_tuning = prompt_tuning
        self.window: Any = None  # set after MainWindow is created

        # Stores (can be reassigned when sandbox changes)
        self.session_store = session_store
        self.knowledge_store = knowledge_store

        # Lifecycle flags
        self.app_closing: dict[str, bool] = {"value": False}
        self.scheduled_after: dict[str, str] = {}

        # Session tracking
        self.active_session: dict[str, Optional[str]] = {"sid": None, "node_id": None}
        self.autosave_timer: dict[str, Any] = {"id": None}

        # Streaming state
        self.streaming_content: list[str] = []
        self.stream_flush_id: dict[str, Any] = {"id": None}
        self.stream_dirty: dict[str, bool] = {"val": False}

        # Confirmation state (thread-safe via Events)
        self.confirm_result: dict[str, Any] = {"value": False, "event": threading.Event()}
        self.gui_confirm_result: dict[str, Any] = {"value": "deny", "event": threading.Event()}

    # ── Timer helpers ─────────────────────────────────

    def safe_after(self, name: str, delay_ms: int, callback: Callable) -> Optional[str]:
        """Schedule a callback, protected against shutdown."""
        if self.app_closing["value"]:
            return None

        def _wrapped():
            self.scheduled_after.pop(name, None)
            if self.app_closing["value"]:
                return
            callback()

        try:
            after_id = self.root.after(delay_ms, _wrapped)
        except tk.TclError:
            return None
        self.scheduled_after[name] = after_id
        return after_id

    def cancel_after(self, name: str) -> None:
        """Cancel a named scheduled timer."""
        after_id = self.scheduled_after.pop(name, None)
        if after_id:
            try:
                self.root.after_cancel(after_id)
            except tk.TclError:
                pass

    def safe_ui(self, callback: Callable) -> None:
        """Marshal a callback to the main thread, protected against shutdown."""
        if self.app_closing["value"]:
            return
        try:
            self.root.after(0, lambda: None if self.app_closing["value"] else callback())
        except tk.TclError:
            pass
