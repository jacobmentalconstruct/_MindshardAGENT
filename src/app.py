"""Application entry point and composition root.

Responsibilities:
  - bootstrap logging
  - load config
  - create runtime infrastructure (activity stream, event bus)
  - create engine with sandbox support
  - create and launch the GUI
  - manage app lifecycle

This file was decomposed from a 66KB monolith into:
  app_state.py      — shared mutable state (AppState)
  app_session.py    — session management callbacks
  app_prompt.py     — prompt inspection and versioning
  app_docker.py     — Docker management callbacks
  app_streaming.py  — chat submission and streaming
  app_commands.py   — action-button / settings / model callbacks
  app_polling.py    — startup bootstrap and periodic polling
"""

import sys
import threading
import tkinter as tk
from pathlib import Path

# Project root is the _MindshardAGENT directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Ensure project root is on sys.path for package imports
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.runtime.runtime_logger import init_logging, get_logger
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.event_bus import EventBus
from src.core.config.app_config import AppConfig
from src.core.engine import Engine
from src.core.agent.prompt_tuning_store import PromptTuningStore
from src.core.sessions.session_store import SessionStore
from src.core.sessions.knowledge_store import KnowledgeStore
from src.core.registry.state_registry import StateRegistry
from src.ui.ui_state import UIState
from src.ui.gui_main import MainWindow
from src.app_state import AppState

# Extracted modules
from src.app_session import (
    log_model_roles, on_session_new, on_session_select,
    on_session_rename, on_session_delete, on_session_branch,
    on_session_policy, save_current_session,
)
from src.app_prompt import (
    on_prompt_source_saved, refresh_prompt_inspector,
)
from src.app_docker import (
    on_docker_toggle, on_docker_build, on_docker_start,
    on_docker_stop, on_docker_destroy,
)
from src.app_streaming import on_submit
from src.app_commands import (
    on_model_select, on_model_refresh, on_cli_command,
    on_sandbox_pick, on_import, on_reload_tools,
    on_reload_prompt_docs, on_set_tool_round_limit,
    on_open_settings, on_edit_project_brief,
    on_edit_prompt_overrides, handle_faux_click,
)
from src.app_polling import schedule_startup_timers


def main() -> None:
    # ── Load config ───────────────────────────────────
    config = AppConfig.load(PROJECT_ROOT)

    # ── Init logging ──────────────────────────────────
    log_dir = PROJECT_ROOT / config.log_dir
    init_logging(log_dir=log_dir)
    log = get_logger("app")
    log.info("=== MindshardAGENT starting ===")
    log.info("Project root: %s", PROJECT_ROOT)
    prompt_tuning = PromptTuningStore(PROJECT_ROOT)

    # ── Runtime infrastructure ────────────────────────
    activity = ActivityStream()
    bus = EventBus()
    ui_state = UIState()
    registry = StateRegistry()

    # ── Tkinter root (early — needed for confirm dialog) ─
    root = tk.Tk()

    # ── DPI awareness ─────────────────────────────────
    from src.ui.theme import enable_dpi_awareness
    dpi_scale = enable_dpi_awareness(root)
    log.info("DPI scale: %.2f", dpi_scale)

    # ── Destructive command confirmation ─────────────
    # These live here because they need root for dialog + threading.Event for sync
    _confirm_result = {"value": False, "event": threading.Event()}

    def _confirm_destructive(command: str) -> bool:
        """Ask user to confirm destructive commands. Thread-safe via root.after."""
        _confirm_result["event"].clear()
        _confirm_result["value"] = False

        def _ask():
            from tkinter import messagebox
            result = messagebox.askyesno(
                "Destructive Command",
                f"The agent wants to run a destructive command:\n\n"
                f"  {command}\n\n"
                f"Allow this?",
            )
            _confirm_result["value"] = result
            _confirm_result["event"].set()

        s.safe_ui(_ask)
        _confirm_result["event"].wait(timeout=60)
        return _confirm_result["value"]

    _gui_confirm_result = {"value": "deny", "event": threading.Event()}

    def _confirm_gui_launch(command: str, match) -> str:
        """Ask user whether an agent-triggered GUI launch should be allowed."""
        _gui_confirm_result["event"].clear()
        _gui_confirm_result["value"] = "deny"

        def _ask():
            from src.ui.dialogs.gui_launch_dialog import GuiLaunchDialog

            reason_map = {
                "python_tkinter_module": "The agent is trying to launch Tkinter directly via the Python module.",
                "python_script_tkinter": "The target script appears to import or construct Tkinter widgets.",
                "direct_python_script_tkinter": "The target script appears to import or construct Tkinter widgets.",
            }
            dialog = GuiLaunchDialog(
                root,
                command=command,
                target_path=getattr(match, "target_path", ""),
                reason=reason_map.get(getattr(match, "reason", ""), "This looks like a local GUI or Tkinter launch."),
            )
            decision = dialog.result or "deny"
            if decision == "always_allow":
                config.gui_launch_policy = "allow"
                config.save(PROJECT_ROOT)
                activity.info("settings", "GUI launch policy changed to allow")
                try:
                    s.window.set_status("GUI policy updated — local windows now allowed")
                except Exception:
                    pass
            elif decision == "allow_once":
                activity.info("safety", f"GUI launch approved once: {command}")
            else:
                activity.warn("safety", f"GUI launch denied: {command}")
            _gui_confirm_result["value"] = decision
            _gui_confirm_result["event"].set()

        s.safe_ui(_ask)
        _gui_confirm_result["event"].wait(timeout=120)
        return _gui_confirm_result["value"]

    # ── Engine ────────────────────────────────────────
    def _on_tools_reloaded(count: int, names: list):
        s.safe_ui(lambda: s.window.control_pane.set_tool_count(count, names))

    engine = Engine(config=config, activity=activity, bus=bus,
                    on_confirm_destructive=_confirm_destructive,
                    on_tools_reloaded=_on_tools_reloaded,
                    on_confirm_gui_launch=_confirm_gui_launch)

    # ── Default sandbox ───────────────────────────────
    default_sandbox = PROJECT_ROOT / "_sandbox"
    if not config.sandbox_root:
        config.sandbox_root = str(default_sandbox)
    engine.set_sandbox(config.sandbox_root)

    # ── Session store ─────────────────────────────────
    sessions_db = Path(config.sandbox_root) / ".mindshard" / "sessions" / "sessions.db"
    session_store = SessionStore(sessions_db)

    # ── Knowledge store (RAG) ─────────────────────────
    knowledge_store = KnowledgeStore(sessions_db)

    # ── Create AppState ───────────────────────────────
    s = AppState(
        config=config,
        log=log,
        activity=activity,
        bus=bus,
        ui_state=ui_state,
        registry=registry,
        root=root,
        engine=engine,
        prompt_tuning=prompt_tuning,
        session_store=session_store,
        knowledge_store=knowledge_store,
    )

    engine.set_knowledge_store(
        knowledge_store,
        session_id_fn=lambda: s.active_session["sid"],
    )

    # ── Close callback ────────────────────────────────
    def on_close():
        if s.app_closing["value"]:
            return
        s.app_closing["value"] = True
        for name in list(s.scheduled_after):
            s.cancel_after(name)
        if s.autosave_timer["id"] is not None:
            try:
                root.after_cancel(s.autosave_timer["id"])
            except tk.TclError:
                pass
            s.autosave_timer["id"] = None
        if s.stream_flush_id["id"] is not None:
            try:
                root.after_cancel(s.stream_flush_id["id"])
            except tk.TclError:
                pass
            s.stream_flush_id["id"] = None
        log.info("Application closing")
        engine.request_stop()
        save_current_session(s)
        config.save(PROJECT_ROOT)
        s.session_store.close()
        engine.stop()

    # ── Build window ──────────────────────────────────
    window = MainWindow(
        root, ui_state, activity,
        on_submit=lambda text: on_submit(s, text),
        on_model_select=lambda model: on_model_select(s, model),
        on_model_refresh=lambda: on_model_refresh(s),
        on_close=on_close,
        on_cli_command=lambda cmd: on_cli_command(s, cmd),
        on_session_new=lambda: on_session_new(s),
        on_session_select=lambda sid: on_session_select(s, sid),
        on_session_rename=lambda sid, title: on_session_rename(s, sid, title),
        on_session_delete=lambda sid: on_session_delete(s, sid),
        on_session_branch=lambda sid: on_session_branch(s, sid),
        on_session_policy=lambda sid: on_session_policy(s, sid),
        on_sandbox_pick=lambda: on_sandbox_pick(s),
        on_import=lambda: on_import(s),
        on_edit_project_brief=lambda: on_edit_project_brief(s),
        on_edit_prompt_overrides=lambda: on_edit_prompt_overrides(s),
        on_faux_click=lambda label: handle_faux_click(s, label),
        on_docker_toggle=lambda enabled: on_docker_toggle(s, enabled),
        on_docker_build=lambda: on_docker_build(s),
        on_docker_start=lambda: on_docker_start(s),
        on_docker_stop=lambda: on_docker_stop(s),
        on_docker_destroy=lambda: on_docker_destroy(s),
        on_vcs_snapshot=lambda: window.control_pane.vcs_panel.refresh(),
        on_reload_tools=lambda: on_reload_tools(s),
        on_reload_prompt_docs=lambda: on_reload_prompt_docs(s),
        on_prompt_source_saved=lambda path: on_prompt_source_saved(s, path),
        on_set_tool_round_limit=lambda val: on_set_tool_round_limit(s, val),
        on_open_settings=lambda: on_open_settings(s),
        initial_tool_round_limit=config.max_tool_rounds,
        dpi_scale=dpi_scale,
    )
    s.window = window

    # ── Wire VCS panel to engine ──────────────────────
    window.control_pane.vcs_panel.set_vcs(engine.vcs)

    # ── Seed initial project name + tool count ────────
    if config.sandbox_root:
        initial_name = engine.project_meta.display_name if engine.project_meta else Path(config.sandbox_root).name
        initial_source = engine.project_meta.source_path if engine.project_meta else ""
        window.set_project_name(initial_name)
        window.set_project_paths(initial_source or "", config.sandbox_root)
        initial_tools = engine.tool_catalog.sandbox_tool_names()
        window.control_pane.set_tool_count(len(initial_tools), initial_tools)

    # ── Apply window geometry ─────────────────────────
    root.geometry(f"{config.window_width}x{config.window_height}")

    # ── Start engine ──────────────────────────────────
    engine.start()
    activity.info("app", "MindshardAGENT ready")
    activity.info("app", f"Sandbox: {config.sandbox_root}")
    log_model_roles(s)
    window.set_status("Starting up...")
    ui_state.sandbox_root = config.sandbox_root
    window.control_pane.input_pane.set_enabled(False)

    # ── Register startup and polling timers ───────────
    schedule_startup_timers(s)

    # ── Global keyboard shortcuts ────────────────────
    def _on_escape(event=None):
        if ui_state.is_streaming:
            engine.request_stop()
            ui_state.is_streaming = False
            if s.stream_flush_id["id"] is not None:
                root.after_cancel(s.stream_flush_id["id"])
                s.stream_flush_id["id"] = None
            window.control_pane.input_pane.set_enabled(True)
            window.set_status("Stopped")
            activity.info("ui", "Streaming stopped via Escape")
        return "break"

    def _on_ctrl_n(event=None):
        on_session_new(s)
        return "break"

    def _on_ctrl_l(event=None):
        window.chat_pane.clear()
        engine.clear_history()
        activity.info("ui", "Chat cleared via Ctrl+L")
        return "break"

    def _on_ctrl_tab(event=None):
        window.control_pane.cycle_workspace_tabs()
        return "break"

    def _on_ctrl_comma(event=None):
        on_open_settings(s)
        return "break"

    root.bind("<Escape>", _on_escape)
    root.bind("<Control-n>", _on_ctrl_n)
    root.bind("<Control-N>", _on_ctrl_n)
    root.bind("<Control-l>", _on_ctrl_l)
    root.bind("<Control-L>", _on_ctrl_l)
    root.bind("<Control-Tab>", _on_ctrl_tab)
    root.bind("<Control-comma>", _on_ctrl_comma)

    # ── Main loop ─────────────────────────────────────
    log.info("Entering main loop")
    root.mainloop()
    log.info("=== MindshardAGENT shutdown complete ===")


if __name__ == "__main__":
    main()
