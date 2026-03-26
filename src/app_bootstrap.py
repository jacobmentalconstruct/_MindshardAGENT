"""App bootstrap and composition assembly.

Owns creation and wiring of the desktop app runtime, but does not own runtime
behavior or shutdown policy. `app.py` calls into this module and then enters
the Tk main loop.
"""

from __future__ import annotations

import sys
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.app_commands import (
    handle_faux_click,
    on_cli_command,
    on_edit_project_brief,
    on_edit_prompt_overrides,
    on_import,
    on_model_refresh,
    on_model_select,
    on_open_settings,
    on_reload_prompt_docs,
    on_reload_tools,
    on_sandbox_pick,
    on_set_tool_round_limit,
)
from src.app_docker import (
    on_docker_build,
    on_docker_destroy,
    on_docker_start,
    on_docker_stop,
    on_docker_toggle,
)
from src.app_lifecycle import build_on_close, request_active_stop
from src.app_polling import schedule_startup_timers
from src.app_prompt import on_prompt_source_saved
from src.app_safety import build_confirm_destructive, build_confirm_gui_launch
from src.app_session import (
    log_model_roles,
    on_session_branch,
    on_session_delete,
    on_session_new,
    on_session_policy,
    on_session_rename,
    on_session_select,
    schedule_autosave,
)
from src.app_state import AppState
from src.app_streaming import on_submit
from src.app_ui_bridge import UIControlBridgeServer
from src.core.agent.model_roles import PRIMARY_CHAT_ROLE, resolve_model_for_role
from src.core.agent.prompt_tuning_store import PromptTuningStore
from src.core.config.app_config import AppConfig
from src.core.engine import Engine
from src.core.registry.state_registry import StateRegistry
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.event_bus import EventBus
from src.core.runtime.runtime_logger import get_logger, init_logging
from src.core.sessions.knowledge_store import KnowledgeStore
from src.core.sessions.session_store import SessionStore
from src.ui.gui_main import MainWindow
from src.ui.ui_facade import UIFacade
from src.ui.ui_state import UIState


@dataclass(frozen=True)
class AppBootstrapResult:
    root: tk.Tk
    state: AppState
    log: Any


def ensure_project_root_on_path(project_root: Path) -> None:
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))


def bootstrap_app(project_root: Path) -> AppBootstrapResult:
    """Create and wire the application runtime."""
    config = AppConfig.load(project_root)

    log_dir = project_root / config.log_dir
    init_logging(log_dir=log_dir)
    log = get_logger("app")
    log.info("=== MindshardAGENT starting ===")
    log.info("Project root: %s", project_root)

    prompt_tuning = PromptTuningStore(project_root)
    activity = ActivityStream()
    bus = EventBus()
    ui_state = UIState()
    registry = StateRegistry()

    root = tk.Tk()
    dpi_scale = _apply_dpi(root, log)

    s_ref: dict[str, AppState | None] = {"s": None}
    on_confirm_destructive = build_confirm_destructive(
        get_safe_ui=lambda: s_ref["s"].safe_ui,
        root=root,
    )
    on_confirm_gui_launch = build_confirm_gui_launch(
        get_safe_ui=lambda: s_ref["s"].safe_ui,
        root=root,
        config=config,
        activity=activity,
        project_root=project_root,
        get_window=lambda: getattr(s_ref["s"], "window", None),
    )

    engine = _create_engine(
        config=config,
        activity=activity,
        bus=bus,
        on_confirm_destructive=on_confirm_destructive,
        on_confirm_gui_launch=on_confirm_gui_launch,
        s_ref=s_ref,
        project_root=project_root,
    )
    session_store, knowledge_store = _create_stores(config)

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
    s_ref["s"] = s

    engine.set_knowledge_store(
        knowledge_store,
        session_id_fn=lambda: s.active_session_id,
    )

    on_close = build_on_close(s, project_root)
    window = _build_window(s, root=root, ui_state=ui_state, activity=activity, dpi_scale=dpi_scale, on_close=on_close)
    s.window = window

    ui_facade = UIFacade(window)
    s.ui_facade = ui_facade

    _start_ui_bridge_if_enabled(s, config, activity)
    ui_facade.wire_vcs(engine.vcs)
    _attach_context_menus(ui_facade)
    _seed_initial_ui(s, config)
    _start_runtime(s)
    _bind_global_shortcuts(root, s, ui_facade)

    return AppBootstrapResult(root=root, state=s, log=log)


def _apply_dpi(root: tk.Tk, log: Any) -> float:
    from src.ui.theme import apply_dpi_scale, enable_dpi_awareness

    dpi_scale = enable_dpi_awareness(root)
    apply_dpi_scale(dpi_scale)
    log.info("DPI scale: %.2f", dpi_scale)
    return dpi_scale


def _create_engine(
    *,
    config: AppConfig,
    activity: ActivityStream,
    bus: EventBus,
    on_confirm_destructive,
    on_confirm_gui_launch,
    s_ref: dict[str, AppState | None],
    project_root: Path,
) -> Engine:
    def _on_tools_reloaded(count: int, names: list[str]) -> None:
        state = s_ref["s"]
        if state and state.ui_facade:
            state.safe_ui(lambda: state.ui_facade.set_tool_count(count, names))

    engine = Engine(
        config=config,
        activity=activity,
        bus=bus,
        on_confirm_destructive=on_confirm_destructive,
        on_tools_reloaded=_on_tools_reloaded,
        on_confirm_gui_launch=on_confirm_gui_launch,
    )

    default_sandbox = project_root / "_sandbox"
    if not config.sandbox_root:
        config.sandbox_root = str(default_sandbox)
    engine.set_sandbox(config.sandbox_root)
    return engine


def _create_stores(config: AppConfig) -> tuple[SessionStore, KnowledgeStore]:
    sessions_db = Path(config.sandbox_root) / ".mindshard" / "sessions" / "sessions.db"
    return SessionStore(sessions_db), KnowledgeStore(sessions_db)


def _build_window(
    s: AppState,
    *,
    root: tk.Tk,
    ui_state: UIState,
    activity: ActivityStream,
    dpi_scale: float,
    on_close,
) -> MainWindow:
    return MainWindow(
        root,
        ui_state,
        activity,
        on_submit=lambda text: on_submit(s, text),
        on_stop=lambda: request_active_stop(s),
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
        initial_tool_round_limit=s.config.max_tool_rounds,
        dpi_scale=dpi_scale,
    )


def _start_ui_bridge_if_enabled(s: AppState, config: AppConfig, activity: ActivityStream) -> None:
    if not config.ui_bridge_enabled:
        return
    ui_bridge = UIControlBridgeServer(
        s,
        host=config.ui_bridge_host,
        port=config.ui_bridge_port,
    )
    ui_bridge.start()
    s.ui_bridge = ui_bridge
    activity.info("ui_bridge", f"UI bridge ready at {ui_bridge.url}")


def _attach_context_menus(ui_facade: UIFacade) -> None:
    def _on_ask_selection(text: str) -> None:
        try:
            ui_facade.set_input_text(f"Regarding this:\n\n{text}\n\n")
            ui_facade.focus_input()
        except Exception:
            pass

    def _on_inject_selection(text: str) -> None:
        try:
            existing = ui_facade.get_input_text()
            injected = f"{existing}\n\n[Context]\n{text}" if existing.strip() else f"[Context]\n{text}"
            ui_facade.set_input_text(injected)
            ui_facade.focus_input()
        except Exception:
            pass

    ui_facade.attach_context_menus(on_ask=_on_ask_selection, on_inject=_on_inject_selection)


def _seed_initial_ui(s: AppState, config: AppConfig) -> None:
    if config.sandbox_root:
        initial_name = s.engine.project_meta.display_name if s.engine.project_meta else Path(config.sandbox_root).name
        initial_source = s.engine.project_meta.source_path if s.engine.project_meta else ""
        initial_model = resolve_model_for_role(config, PRIMARY_CHAT_ROLE) or "(none)"
        s.window.set_project_name(initial_name)
        s.window.set_project_paths(initial_source or "", config.sandbox_root)
        s.window.set_model(initial_model)
        s.ui_state.selected_model = initial_model if initial_model != "(none)" else ""
        s.engine.tokenizer.set_model(s.ui_state.selected_model)
        initial_tools = s.engine.tool_catalog.discovered_tool_names()
        s.ui_facade.set_tool_count(len(initial_tools), initial_tools)

    s.root.geometry(f"{config.window_width}x{config.window_height}")


def _start_runtime(s: AppState) -> None:
    s.engine.start()
    s.activity.info("app", "MindshardAGENT ready")
    s.activity.info("app", f"Sandbox: {s.config.sandbox_root}")
    log_model_roles(s)
    s.window.set_status("Starting up...")
    s.ui_state.sandbox_root = s.config.sandbox_root
    s.ui_facade.set_input_enabled(False)
    schedule_startup_timers(s)


def _bind_global_shortcuts(root: tk.Tk, s: AppState, ui_facade: UIFacade) -> None:
    def _on_escape(_event=None):
        if request_active_stop(s):
            s.activity.info("ui", f"Stop requested via Escape ({s.ui_state.busy_kind or 'busy'})")
        return "break"

    def _on_ctrl_n(_event=None):
        on_session_new(s)
        return "break"

    def _on_ctrl_l(_event=None):
        ui_facade.clear_chat()
        s.engine.clear_history()
        s.activity.info("ui", "Chat cleared via Ctrl+L")
        return "break"

    def _on_ctrl_tab(_event=None):
        ui_facade.cycle_workspace_tabs()
        return "break"

    def _on_ctrl_comma(_event=None):
        on_open_settings(s)
        return "break"

    def _on_ctrl_s(_event=None):
        schedule_autosave(s)
        s.window.set_status("Session saved")
        s.activity.info("ui", "Session saved via Ctrl+S")
        return "break"

    def _on_ctrl_shift_n(_event=None):
        sid = s.active_session_id or ""
        if sid:
            on_session_branch(s, sid)
        return "break"

    def _on_f5(_event=None):
        on_reload_tools(s)
        on_reload_prompt_docs(s)
        s.activity.info("ui", "Tools and prompt docs reloaded via F5")
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


def _refresh_evidence_bag(s: AppState) -> None:
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
