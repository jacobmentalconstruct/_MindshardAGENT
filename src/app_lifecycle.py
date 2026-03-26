"""App lifecycle orchestration.

Owns runtime-control callbacks and the full shutdown sequence for the desktop
app. This keeps `app.py` as a composition root instead of an inline lifecycle
container.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from src.app_session import save_current_session

if TYPE_CHECKING:
    from src.app_state import AppState


def request_active_stop(s: "AppState") -> bool:
    """Request a real stop for the current busy operation, if any."""
    if not s.ui_state.is_busy:
        return False
    s.engine.request_stop()
    s.mark_stop_requested(status_text="Stop requested")
    s.activity.info("ui", f"Stop requested ({s.ui_state.busy_kind or 'busy'})")
    return True


def build_on_close(s: "AppState", project_root: Path) -> Callable[[], None]:
    """Build the full shutdown callback for the running app."""

    def _on_close() -> None:
        shutdown_app(s, project_root)

    return _on_close


def shutdown_app(s: "AppState", project_root: Path) -> None:
    """Run the full app shutdown sequence exactly once."""
    if not s.begin_shutdown():
        return
    _cancel_scheduled_callbacks(s)

    s.log.info("Application closing")
    s.engine.request_stop()

    if getattr(s.engine, "loop_manager", None):
        s.engine.loop_manager.join_all(timeout=3.0)

    ctc = getattr(s.engine, "_active_thought_chain", None)
    if ctc is not None:
        ctc.join(timeout=3.0)

    if s.ui_bridge is not None:
        s.ui_bridge.stop()

    save_current_session(s)
    s.config.save(project_root)
    s.session_store.close()
    s.engine.stop()


def _cancel_scheduled_callbacks(s: "AppState") -> None:
    """Cancel all known Tk timers before teardown."""
    for name in list(s.scheduled_after):
        s.cancel_after(name)
    if s.autosave_after_id is not None:
        _cancel_after_id(s.root, s.autosave_after_id)
        s.clear_autosave_after_id()
    if s.stream_flush_after_id is not None:
        _cancel_after_id(s.root, s.stream_flush_after_id)
        s.clear_stream_flush_after_id()


def _cancel_after_id(root: tk.Tk, after_id) -> None:
    try:
        root.after_cancel(after_id)
    except tk.TclError:
        pass
