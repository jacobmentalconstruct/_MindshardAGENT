"""Safety gate callbacks for engine command confirmation.

ROLE: Owns the blocking-with-timeout dialog pattern used to confirm destructive
      and GUI-launch commands during agent execution.

WHAT IT OWNS:
  - build_confirm_destructive: factory → on_confirm_destructive callable for Engine
  - build_confirm_gui_launch: factory → on_confirm_gui_launch callable for Engine

Both factories use get_safe_ui() indirection so they can be constructed before
AppState exists (required because Engine is created before AppState). The returned
callables close over a lazy get_safe_ui fn that resolves s.safe_ui at call time.

Domain: ui only (dialogs + safe_ui threading pattern)
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable


def build_confirm_destructive(
    get_safe_ui: Callable[[], Callable],
    root: Any,
) -> Callable[[str], bool]:
    """Return a thread-safe destructive command confirmation function.

    get_safe_ui: zero-arg callable that returns the active safe_ui dispatcher.
                 Use a lambda closing over an _s_ref holder to allow late binding.
    root: tk.Tk parent (kept for future expansion; dialogs currently use messagebox).
    """
    _result: dict[str, Any] = {"value": False, "event": threading.Event()}

    def confirm(command: str) -> bool:
        _result["event"].clear()
        _result["value"] = False

        def _ask() -> None:
            from tkinter import messagebox
            _result["value"] = messagebox.askyesno(
                "Destructive Command",
                f"The agent wants to run a destructive command:\n\n"
                f"  {command}\n\n"
                f"Allow this?",
            )
            _result["event"].set()

        get_safe_ui()(_ask)
        _result["event"].wait(timeout=60)
        return _result["value"]

    return confirm


def build_confirm_gui_launch(
    get_safe_ui: Callable[[], Callable],
    root: Any,
    config: Any,
    activity: Any,
    project_root: Path,
    get_window: Callable[[], Any],
) -> Callable[[str, Any], str]:
    """Return a thread-safe GUI launch confirmation function.

    get_safe_ui: zero-arg callable returning the active safe_ui dispatcher.
    root: tk.Tk parent for GuiLaunchDialog.
    config: AppConfig — policy changes (always_allow) are written back here.
    activity: ActivityStream for audit logging.
    project_root: Path used for config.save().
    get_window: zero-arg callable returning the current MainWindow (may be None).
    """
    _result: dict[str, Any] = {"value": "deny", "event": threading.Event()}

    _reason_map = {
        "python_tkinter_module": "The agent is trying to launch Tkinter directly via the Python module.",
        "python_script_tkinter": "The target script appears to import or construct Tkinter widgets.",
        "direct_python_script_tkinter": "The target script appears to import or construct Tkinter widgets.",
    }

    def confirm(command: str, match: Any) -> str:
        _result["event"].clear()
        _result["value"] = "deny"

        def _ask() -> None:
            from src.ui.dialogs.gui_launch_dialog import GuiLaunchDialog

            dialog = GuiLaunchDialog(
                root,
                command=command,
                target_path=getattr(match, "target_path", ""),
                reason=_reason_map.get(
                    getattr(match, "reason", ""),
                    "This looks like a local GUI or Tkinter launch.",
                ),
            )
            decision = dialog.result or "deny"

            if decision == "always_allow":
                config.gui_launch_policy = "allow"
                config.save(project_root)
                activity.info("settings", "GUI launch policy changed to allow")
                try:
                    win = get_window()
                    if win:
                        win.set_status("GUI policy updated — local windows now allowed")
                except Exception:
                    pass
            elif decision == "allow_once":
                activity.info("safety", f"GUI launch approved once: {command}")
            else:
                activity.warn("safety", f"GUI launch denied: {command}")

            _result["value"] = decision
            _result["event"].set()

        get_safe_ui()(_ask)
        _result["event"].wait(timeout=120)
        return _result["value"]

    return confirm
