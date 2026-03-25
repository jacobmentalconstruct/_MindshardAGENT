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
  app_safety.py     — safety gate callbacks (destructive + GUI launch confirm)
  app_session.py    — session management callbacks
  app_prompt.py     — prompt inspection and versioning
  app_docker.py     — Docker management callbacks
  app_streaming.py  — chat submission and streaming
  app_commands.py   — action-button / settings / model callbacks
  app_polling.py    — startup bootstrap and periodic polling
  src/ui/ui_facade.py — intent-level bridge between app.py and UI widget tree
"""

import sys
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
from src.ui.ui_facade import UIFacade
from src.app_state import AppState
from src.app_safety import build_confirm_destructive, build_confirm_gui_launch

# Extracted modules
from src.app_session import (
    log_model_roles, on_session_new, on_session_select,
    on_session_rename, on_session_delete, on_session_branch,
    on_session_policy, save_current_session,
)
from src.core.agent.model_roles import PRIMARY_CHAT_ROLE, resolve_model_for_role
from src.app_prompt import (
    on_prompt_source_saved, refresh_prompt_inspector,
)
from src.app_docker import (
    on_docker_toggle, on_docker_build, on_docker_start,
    on_docker_stop, on_docker_destroy,
)
from src.app_ui_bridge import UIControlBridgeServer
from src.app_streaming import on_submit
from src.app_commands import (
    on_model_select, on_model_refresh, on_cli_command,
    on_sandbox_pick, on_import, on_reload_tools,
    on_reload_prompt_docs, on_set_tool_round_limit,
    on_open_settings, on_edit_project_brief,
    on_edit_prompt_overrides, handle_faux_click,
)
from src.app_polling import schedule_startup_timers


def _refresh_evidence_bag(s) -> None:
    """Fetch current evidence bag state and push it to the UI explorer tab."""
    if not s.ui_facade:
        return
    bag = getattr(s.engine, "evidence_bag", None)
    if bag is None:
        s.safe_ui(lambda: s.ui_facade.set_evidence_bag_display("(evidence bag not enabled)", enabled=False))
        return
    try:
        content = bag.build_summary("", token_budget=800) or "(bag is empty — no falloff turns yet)"
        enabled = True
    except Exception as exc:
        content = f"(error fetching bag contents: {exc})"
        enabled = False
    s.safe_ui(lambda: s.ui_facade.set_evidence_bag_display(content, enabled=enabled))


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

    # ── Tkinter root ──────────────────────────────────
    root = tk.Tk()

    # ── DPI awareness ─────────────────────────────────
    from src.ui.theme import apply_dpi_scale, enable_dpi_awareness
    dpi_scale = enable_dpi_awareness(root)
    apply_dpi_scale(dpi_scale)
    log.info("DPI scale: %.2f", dpi_scale)

    # ── Safety callbacks (built before Engine; s is bound lazily via _s_ref) ─
    _s_ref: dict = {"s": None}

    on_confirm_destructive = build_confirm_destructive(
        get_safe_ui=lambda: _s_ref["s"].safe_ui,
        root=root,
    )
    on_confirm_gui_launch = build_confirm_gui_launch(
        get_safe_ui=lambda: _s_ref["s"].safe_ui,
        root=root,
        config=config,
        activity=activity,
        project_root=PROJECT_ROOT,
        get_window=lambda: getattr(_s_ref["s"], "window", None),
    )

    # ── Engine ────────────────────────────────────────
    def _on_tools_reloaded(count: int, names: list):
        if _s_ref["s"] and _s_ref["s"].ui_facade:
            _s_ref["s"].safe_ui(lambda: _s_ref["s"].ui_facade.set_tool_count(count, names))

    engine = Engine(
        config=config,
        activity=activity,
        bus=bus,
        on_confirm_destructive=on_confirm_destructive,
        on_tools_reloaded=_on_tools_reloaded,
        on_confirm_gui_launch=on_confirm_gui_launch,
    )

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
    _s_ref["s"] = s  # bind s so safety callbacks can resolve s.safe_ui

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
        # Wait up to 3s for every registered loop thread to drain before closing
        # shared resources (DB, UI).  Covers tool-agent, direct-chat, planner-only,
        # thought-chain (via loop_manager), and any future loop types.
        if hasattr(engine, "loop_manager") and engine.loop_manager:
            engine.loop_manager.join_all(timeout=3.0)
        # Also drain any standalone thought chain spawned via the Plan button
        # (bypasses loop_manager, goes through engine.run_thought_chain directly).
        ctc = getattr(engine, "_active_thought_chain", None)
        if ctc is not None:
            ctc.join(timeout=3.0)
        if s.ui_bridge is not None:
            s.ui_bridge.stop()
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
        on_vcs_snapshot=lambda: s.ui_facade.refresh_vcs() if s.ui_facade else None,
        on_bag_refresh=lambda: _refresh_evidence_bag(s),
        on_reload_tools=lambda: on_reload_tools(s),
        on_reload_prompt_docs=lambda: on_reload_prompt_docs(s),
        on_prompt_source_saved=lambda path: on_prompt_source_saved(s, path),
        on_set_tool_round_limit=lambda val: on_set_tool_round_limit(s, val),
        on_open_settings=lambda: on_open_settings(s),
        initial_tool_round_limit=config.max_tool_rounds,
        dpi_scale=dpi_scale,
    )
    s.window = window

    # ── Wire UI facade ────────────────────────────────
    ui_facade = UIFacade(window)
    s.ui_facade = ui_facade

    # ── Optional local UI control bridge ─────────────
    if config.ui_bridge_enabled:
        ui_bridge = UIControlBridgeServer(
            s,
            host=config.ui_bridge_host,
            port=config.ui_bridge_port,
        )
        ui_bridge.start()
        s.ui_bridge = ui_bridge
        activity.info("ui_bridge", f"UI bridge ready at {ui_bridge.url}")

    # ── Wire VCS panel to engine ──────────────────────
    ui_facade.wire_vcs(engine.vcs)

    # ── Wire right-click context menus (highlight → ask) ─────────

    def _on_ask_selection(text: str) -> None:
        """Pre-fill the input with the selected text as a question."""
        try:
            ui_facade.set_input_text(f"Regarding this:\n\n{text}\n\n")
            ui_facade.focus_input()
        except Exception:
            pass

    def _on_inject_selection(text: str) -> None:
        """Append the selected text as context into the current chat input."""
        try:
            existing = ui_facade.get_input_text()
            injected = f"{existing}\n\n[Context]\n{text}" if existing.strip() else f"[Context]\n{text}"
            ui_facade.set_input_text(injected)
            ui_facade.focus_input()
        except Exception:
            pass

    ui_facade.attach_context_menus(
        on_ask=_on_ask_selection, on_inject=_on_inject_selection
    )

    # ── Seed initial project name + tool count ────────
    if config.sandbox_root:
        initial_name = engine.project_meta.display_name if engine.project_meta else Path(config.sandbox_root).name
        initial_source = engine.project_meta.source_path if engine.project_meta else ""
        initial_model = resolve_model_for_role(config, PRIMARY_CHAT_ROLE) or "(none)"
        window.set_project_name(initial_name)
        window.set_project_paths(initial_source or "", config.sandbox_root)
        window.set_model(initial_model)
        ui_state.selected_model = initial_model if initial_model != "(none)" else ""
        engine.tokenizer.set_model(ui_state.selected_model)
        initial_tools = engine.tool_catalog.discovered_tool_names()
        ui_facade.set_tool_count(len(initial_tools), initial_tools)

    # ── Apply window geometry ─────────────────────────
    root.geometry(f"{config.window_width}x{config.window_height}")

    # ── Start engine ──────────────────────────────────
    engine.start()
    activity.info("app", "MindshardAGENT ready")
    activity.info("app", f"Sandbox: {config.sandbox_root}")
    log_model_roles(s)
    window.set_status("Starting up...")
    ui_state.sandbox_root = config.sandbox_root
    ui_facade.set_input_enabled(False)

    # ── Register startup and polling timers ───────────
    schedule_startup_timers(s)

    # ── Global keyboard shortcuts ─────────────────────
    def _on_escape(event=None):
        if ui_state.is_busy:
            engine.request_stop()
            s.mark_stop_requested(status_text="Stopping...")
            activity.info("ui", f"Stop requested via Escape ({ui_state.busy_kind or 'busy'})")
        return "break"

    def _on_ctrl_n(event=None):
        on_session_new(s)
        return "break"

    def _on_ctrl_l(event=None):
        ui_facade.clear_chat()
        engine.clear_history()
        activity.info("ui", "Chat cleared via Ctrl+L")
        return "break"

    def _on_ctrl_tab(event=None):
        ui_facade.cycle_workspace_tabs()
        return "break"

    def _on_ctrl_comma(event=None):
        on_open_settings(s)
        return "break"

    def _on_ctrl_s(event=None):
        """Save the active session."""
        from src.app_session import schedule_autosave
        schedule_autosave(s)
        window.set_status("Session saved")
        activity.info("ui", "Session saved via Ctrl+S")
        return "break"

    def _on_ctrl_shift_n(event=None):
        """Branch the active session."""
        from src.app_session import on_session_branch
        sid = s.active_session.get("sid", "")
        if sid:
            on_session_branch(s, sid)
        return "break"

    def _on_f5(event=None):
        """Reload tools and prompt docs."""
        from src.app_commands import on_reload_tools, on_reload_prompt_docs
        on_reload_tools(s)
        on_reload_prompt_docs(s)
        activity.info("ui", "Tools and prompt docs reloaded via F5")
        return "break"

    root.bind("<Escape>", _on_escape)
    root.bind("<Control-n>", _on_ctrl_n)
    root.bind("<Control-N>", _on_ctrl_n)
    root.bind("<Control-l>", _on_ctrl_l)
    root.bind("<Control-L>", _on_ctrl_l)
    root.bind("<Control-Tab>", _on_ctrl_tab)
    root.bind("<Control-comma>", _on_ctrl_comma)
    root.bind("<Control-s>", _on_ctrl_s)
    root.bind("<Control-S>", _on_ctrl_s)
    root.bind("<Control-Shift-n>", _on_ctrl_shift_n)
    root.bind("<Control-Shift-N>", _on_ctrl_shift_n)
    root.bind("<F5>", _on_f5)

    # ── Main loop ─────────────────────────────────────
    log.info("Entering main loop")
    root.mainloop()
    log.info("=== MindshardAGENT shutdown complete ===")


if __name__ == "__main__":
    main()
