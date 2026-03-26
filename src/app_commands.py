"""Action-button command handlers — app-layer routing shims."""

from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog
from typing import TYPE_CHECKING

from src.app_faux_button_commands import dispatch_faux_click
from src.app_model_commands import (
    on_model_refresh as _on_model_refresh,
    on_model_select as _on_model_select,
    on_reload_tools as _on_reload_tools,
    on_set_tool_round_limit as _on_set_tool_round_limit,
)
from src.app_prompt_lab import open_prompt_lab_surface as _open_prompt_lab_surface
from src.app_prompt_lab import refresh_prompt_lab_summary as _refresh_prompt_lab_summary
from src.app_project_edit_commands import (
    on_edit_project_brief as _on_edit_project_brief,
    on_edit_prompt_overrides as _on_edit_prompt_overrides,
)
from src.core.agent.model_roles import current_model_roles

if TYPE_CHECKING:
    from src.app_state import AppState

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def on_model_select(s: AppState, model: str) -> None:
    _on_model_select(s, model)


def on_model_refresh(s: AppState) -> None:
    _on_model_refresh(s)


# ── CLI panel callback ────────────────────────────────────────────────────────

def on_cli_command(s: AppState, command: str) -> None:
    s.activity.tool("cli_panel", f"User CLI: {command}")

    def _run():
        result = s.engine.run_cli(command)
        s.safe_ui(lambda: s.window.cli_pane.show_result(result))

    threading.Thread(target=_run, daemon=True, name="cli-panel").start()


# ── Sandbox picker callback ───────────────────────────────────────────────────

def on_sandbox_pick(s: AppState) -> None:
    """Shim: collect folder path + optional brief, then delegate to project handler."""
    from src.core.project.project_command_handler import attach_sandbox
    from src.ui.dialogs.project_brief_dialog import ProjectBriefDialog
    from src.core.project.project_meta import ProjectMeta
    from src.core.utils.clock import utc_iso

    new_root = filedialog.askdirectory(
        title="Attach Project — Select Project Folder",
        initialdir=s.config.sandbox_root,
    )
    if not new_root:
        return

    folder_name = Path(new_root).name
    existing_meta = ProjectMeta(new_root)

    if not existing_meta.exists:
        dlg = ProjectBriefDialog(s.root, project_name=folder_name)
        if dlg.result is None:
            return
        brief_data = dlg.result
        brief_data["source_path"] = ""
        brief_data["attached_at"] = utc_iso()
    else:
        brief_data = None

    attach_sandbox(s, new_root, brief_data=brief_data)


# ── Misc callbacks ────────────────────────────────────────────────────────────

def on_import(s: AppState) -> None:
    handle_faux_click(s, "Add Ref")


def on_reload_tools(s: AppState) -> None:
    _on_reload_tools(s)


def on_reload_prompt_docs(s: AppState) -> None:
    from src.app_prompt import refresh_prompt_inspector
    refresh_prompt_inspector(s, s.ui_state.last_user_input, announce=True)


def on_open_prompt_lab(s: AppState) -> None:
    _open_prompt_lab_surface(s)


def on_reload_prompt_lab_state(s: AppState) -> None:
    _refresh_prompt_lab_summary(s, announce=True)


def on_set_tool_round_limit(s: AppState, value: int) -> None:
    _on_set_tool_round_limit(s, value)


# ── Settings dialog ───────────────────────────────────────────────────────────

def on_open_settings(s: AppState) -> None:
    from src.ui.dialogs.settings_dialog import SettingsDialog
    from src.core.config.settings_command_handler import apply_settings

    dialog = SettingsDialog(
        s.root,
        available_models=s.ui_state.available_models,
        initial_model_roles=current_model_roles(s.config),
        initial_tool_round_limit=s.config.max_tool_rounds,
        initial_gui_launch_policy=s.config.gui_launch_policy,
        initial_planning_enabled=s.config.planning_enabled,
        initial_recovery_planning_enabled=s.config.recovery_planning_enabled,
        initial_probe_models=getattr(s.config, "probe_models", None) or {},
        initial_toolbox_root=getattr(s.config, "toolbox_root", "") or "",
    )
    if not dialog.result:
        return
    apply_settings(s, dialog.result, _PROJECT_ROOT)


# ── Project brief / prompt overrides ─────────────────────────────────────────

def on_edit_project_brief(s: AppState) -> None:
    _on_edit_project_brief(s)


def on_edit_prompt_overrides(s: AppState) -> None:
    _on_edit_prompt_overrides(s)


# ── Faux button dispatcher ────────────────────────────────────────────────────

def handle_faux_click(s: AppState, label: str) -> None:
    dispatch_faux_click(s, label)
