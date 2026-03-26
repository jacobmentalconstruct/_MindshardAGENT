"""Shared mutable application state.

All state that was previously captured via closures in main() is now held
in a single AppState instance.  Every extracted module receives this object
instead of relying on nonlocal / closure capture.
"""

from __future__ import annotations

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
        # UI intent facade (set after MainWindow is created)
        "ui_facade", "ui_bridge",
        # Lifecycle
        "app_closing", "scheduled_after",
        # Session
        "active_session", "autosave_timer",
        # Streaming
        "streaming_content", "stream_flush_id", "stream_dirty",
        # Busy operation tracking
        "busy_state",
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
        self.window: Any = None       # set after MainWindow is created
        self.ui_facade: Any = None    # set after UIFacade is wired in app.py
        self.ui_bridge: Any = None    # set if the local UI control bridge is started

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

        # Busy operation state
        self.busy_state: dict[str, Any] = {
            "next_token": 0,
            "active_token": 0,
            "kind": "",
            "input_locked": False,
        }

    # ── Timer helpers ─────────────────────────────────

    @property
    def is_closing(self) -> bool:
        return bool(self.app_closing["value"])

    def begin_shutdown(self) -> bool:
        """Mark shutdown start once; return False if already closing."""
        if self.app_closing["value"]:
            return False
        self.app_closing["value"] = True
        return True

    def safe_after(self, name: str, delay_ms: int, callback: Callable) -> Optional[str]:
        """Schedule a callback, protected against shutdown."""
        if self.is_closing:
            return None

        def _wrapped():
            self.scheduled_after.pop(name, None)
            if self.is_closing:
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
        if self.is_closing:
            return
        try:
            self.root.after(0, lambda: None if self.is_closing else callback())
        except tk.TclError:
            pass

    # ── Session helpers ───────────────────────────────

    @property
    def active_session_id(self) -> Optional[str]:
        return self.active_session["sid"]

    @property
    def active_session_node_id(self) -> Optional[str]:
        return self.active_session["node_id"]

    def set_active_session(self, *, sid: Optional[str], node_id: Optional[str]) -> None:
        self.active_session["sid"] = sid
        self.active_session["node_id"] = node_id

    @property
    def autosave_after_id(self) -> Any:
        return self.autosave_timer["id"]

    def set_autosave_after_id(self, after_id: Any) -> None:
        self.autosave_timer["id"] = after_id

    def clear_autosave_after_id(self) -> None:
        self.autosave_timer["id"] = None

    # ── Stream helpers ────────────────────────────────

    def reset_stream_buffer(self) -> None:
        self.streaming_content.clear()
        self.stream_dirty["val"] = False

    def append_stream_token(self, token: str) -> None:
        self.streaming_content.append(token)
        self.stream_dirty["val"] = True

    def current_stream_text(self) -> str:
        return "".join(self.streaming_content)

    def consume_stream_dirty(self) -> bool:
        dirty = bool(self.stream_dirty["val"])
        self.stream_dirty["val"] = False
        return dirty

    @property
    def stream_flush_after_id(self) -> Any:
        return self.stream_flush_id["id"]

    def set_stream_flush_after_id(self, after_id: Any) -> None:
        self.stream_flush_id["id"] = after_id

    def clear_stream_flush_after_id(self) -> None:
        self.stream_flush_id["id"] = None

    # ── Busy-operation helpers ─────────────────────────

    def begin_busy(
        self,
        kind: str,
        *,
        status_text: str | None = None,
        disable_input: bool = True,
    ) -> int:
        """Mark the app busy for a long-running operation and return its token."""
        token = int(self.busy_state.get("next_token", 0) or 0) + 1
        self.busy_state["next_token"] = token
        self.busy_state["active_token"] = token
        self.busy_state["kind"] = str(kind or "").strip()
        self.busy_state["input_locked"] = bool(disable_input)

        self.ui_state.is_busy = True
        self.ui_state.busy_kind = self.busy_state["kind"]
        self.ui_state.stop_requested = False

        if status_text and self.window is not None:
            self.window.set_status(status_text)
        if disable_input and self.ui_facade is not None:
            self.ui_facade.set_input_enabled(False)
        if self.ui_facade is not None:
            self.ui_facade.set_stop_requested(False)
            self.ui_facade.set_stop_enabled(True)
        return token

    def end_busy(
        self,
        token: int | None = None,
        *,
        status_text: str | None = "Ready",
        enable_input: bool = True,
    ) -> bool:
        """Clear the active busy marker if *token* still owns it."""
        active_token = int(self.busy_state.get("active_token", 0) or 0)
        if token is not None and active_token and int(token) != active_token:
            return False

        self.busy_state["active_token"] = 0
        self.busy_state["kind"] = ""
        self.busy_state["input_locked"] = False

        self.ui_state.is_busy = False
        self.ui_state.busy_kind = ""
        self.ui_state.stop_requested = False

        if status_text and self.window is not None:
            self.window.set_status(status_text)
        if self.ui_facade is not None:
            self.ui_facade.set_stop_requested(False)
            self.ui_facade.set_stop_enabled(False)
            if enable_input:
                self.ui_facade.set_input_enabled(True)
        return True

    def mark_stop_requested(self, *, status_text: str | None = "Stop requested") -> bool:
        """Mark that the current busy operation has been asked to stop."""
        if not self.ui_state.is_busy:
            return False
        self.ui_state.stop_requested = True
        if status_text and self.window is not None:
            self.window.set_status(status_text)
        if self.ui_facade is not None:
            self.ui_facade.set_stop_requested(True)
        return True
