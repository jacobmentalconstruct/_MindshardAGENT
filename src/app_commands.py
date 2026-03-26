"""Action-button command handlers — thin dispatcher shims.

Each function here is a shim: it collects UI I/O (file dialogs, confirmation
dialogs, simple input), validates the result, and routes intent to the
appropriate domain handler. No workflow logic lives here.

Domain handlers:
  - src.core.project.project_command_handler  — project lifecycle operations
  - src.core.project.sync_command_handler     — sync-to-source workflow
  - src.core.config.settings_command_handler  — settings dialog apply + runtime sync
  - src.core.agent.thought_chain_command_handler — CTC planning workflow
"""

from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog
from typing import TYPE_CHECKING

from src.core.agent.model_roles import PRIMARY_CHAT_ROLE, current_model_roles, resolve_model_for_role

if TYPE_CHECKING:
    from src.app_state import AppState

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ── Model callbacks ───────────────────────────────────────────────────────────

def on_model_select(s: AppState, model: str) -> None:
    from src.app_session import log_model_roles
    from src.app_prompt import refresh_prompt_inspector

    s.config.primary_chat_model = model
    s.config.selected_model = model
    s.config.normalize_model_roles()
    s.ui_state.selected_model = model
    s.engine.tokenizer.set_model(model)
    s.window.set_model(model)
    s.activity.info("model", f"Model selected: {model}")
    log_model_roles(s)
    refresh_prompt_inspector(s, s.ui_state.last_user_input)


def on_model_refresh(s: AppState) -> None:
    s.activity.info("model", "Model refresh requested")
    s.window.set_status("Refreshing models...")

    def _worker():
        try:
            from src.core.ollama.model_scanner import scan_models
            models = scan_models(s.config.ollama_base_url)

            def _apply():
                if s.is_closing:
                    return
                primary_model = resolve_model_for_role(s.config, PRIMARY_CHAT_ROLE)
                if s.ui_facade:
                    s.ui_facade.set_models(models, primary_model)
                s.ui_state.available_models = models
                s.activity.info("model", f"Found {len(models)} model(s)")
                s.window.set_status("Ready — refresh models to begin")
            s.safe_ui(_apply)
        except Exception as e:
            def _err_ui(err=e):
                s.activity.error("model", f"Scan failed: {err}")
                s.window.set_status("Model refresh failed")
            s.safe_ui(_err_ui)

    threading.Thread(target=_worker, daemon=True, name="model-refresh").start()


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
    if not s.config.sandbox_root:
        return
    names = s.engine.reload_discovered_tools()
    if s.ui_facade:
        s.ui_facade.set_tool_count(len(names), names)
    s.activity.info("tools", f"Tools reloaded: {len(names)} discovered tool(s) available")


def on_reload_prompt_docs(s: AppState) -> None:
    from src.app_prompt import refresh_prompt_inspector
    refresh_prompt_inspector(s, s.ui_state.last_user_input, announce=True)


def on_set_tool_round_limit(s: AppState, value: int) -> None:
    s.config.max_tool_rounds = max(1, int(value))
    s.config.save(_PROJECT_ROOT)
    if s.ui_facade:
        s.ui_facade.set_tool_round_limit(s.config.max_tool_rounds)
    s.activity.info("tools", f"Max tool rounds set to {s.config.max_tool_rounds}")


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
    from src.app_prompt import refresh_prompt_inspector, snapshot_prompt_state

    if not s.engine.project_meta:
        if s.ui_facade:
            s.ui_facade.post_system_message("No project attached.")
        return
    from src.ui.dialogs.project_brief_dialog import ProjectBriefDialog

    meta = s.engine.project_meta
    dlg = ProjectBriefDialog(
        s.root,
        project_name=meta.display_name,
        is_self_edit=meta.is_self_edit,
        initial_data=meta.brief_form_data(),
        submit_label="SAVE BRIEF",
        title_text="EDIT PROJECT BRIEF",
    )
    if dlg.result is None:
        return

    meta.update(dlg.result)
    display = meta.display_name
    source_path = meta.source_path or ""
    s.window.set_project_name(display)
    s.window.set_project_paths(source_path, s.config.sandbox_root)
    s.activity.info("project", f"Project brief updated: {display}")
    prompt_build = refresh_prompt_inspector(s, s.ui_state.last_user_input, announce=True)
    snapshot_prompt_state(s, "project brief updated", changed_path=meta.path, prompt_build=prompt_build)


def on_edit_prompt_overrides(s: AppState) -> None:
    from src.app_prompt import refresh_prompt_inspector, snapshot_prompt_state

    if not s.engine.project_meta:
        if s.ui_facade:
            s.ui_facade.post_system_message("No project attached.")
        return

    meta = s.engine.project_meta
    created = meta.ensure_prompt_override_scaffold()
    override_dir = meta.prompt_overrides_dir

    try:
        import os
        os.startfile(str(override_dir))  # type: ignore[attr-defined]
    except Exception:
        try:
            s.engine.run_cli(f'explorer "{override_dir}"')
        except Exception:
            pass

    if created:
        s.activity.info("prompt", f"Prompt override scaffold created at {override_dir}")
        prompt_build = refresh_prompt_inspector(s, s.ui_state.last_user_input, announce=True)
        snapshot_prompt_state(s, "prompt override scaffold created", changed_path=override_dir, prompt_build=prompt_build)
    else:
        s.activity.info("prompt", f"Opened prompt overrides at {override_dir}")
        refresh_prompt_inspector(s, s.ui_state.last_user_input, announce=True)


# ── Faux button dispatcher ────────────────────────────────────────────────────

def handle_faux_click(s: AppState, label: str) -> None:
    """Route control panel button clicks to domain handlers.

    This dispatcher owns button-label-to-intent routing only.
    All workflow logic lives in domain handlers.
    """
    if label == "Attach Self":
        dest_root = filedialog.askdirectory(
            title="Choose working copy destination for self-edit",
            initialdir=str(_PROJECT_ROOT.parent),
        )
        if not dest_root:
            return
        from src.core.project.project_command_handler import attach_self
        attach_self(s, dest_root)

    elif label == "Sync to Source":
        from src.core.project.sync_command_handler import sync_to_source
        sync_to_source(s)

    elif label in ("Add Ref", "Import"):
        src_dir = filedialog.askdirectory(
            title="Select folder to add to Bookshelf (.mindshard/ref/)",
        )
        if not src_dir:
            return
        from src.core.project.project_command_handler import add_ref
        add_ref(s, src_dir)

    elif label == "Add Parts":
        src_dir = filedialog.askdirectory(
            title="Select folder to add to Parts Bin (.mindshard/parts/)",
        )
        if not src_dir:
            return
        from src.core.project.project_command_handler import add_parts
        add_parts(s, src_dir)

    elif label == "Tools":
        discovered = s.engine.tool_catalog.discovered_tool_names()
        if discovered:
            details = []
            for name in discovered:
                entry = s.engine.tool_catalog.get(name)
                if entry:
                    details.append(f"{name} ({entry.source})")
            s.activity.info("tools", f"Discovered tools: {', '.join(details)}")
        else:
            s.activity.info("tools", "No discovered tools found. Agent can create them in .mindshard/tools/")

    elif label == "Plan":
        from tkinter import simpledialog
        from src.core.agent.thought_chain_command_handler import run_thought_chain

        goal = simpledialog.askstring(
            "Thought Chain", "Enter a goal to decompose into tasks:", parent=s.root)
        if not goal or not goal.strip():
            return
        run_thought_chain(s, goal.strip(), depth=3)

    elif label == "Detach":
        if not s.config.sandbox_root:
            if s.ui_facade:
                s.ui_facade.post_system_message("No project attached.")
            return
        from src.ui.dialogs.detach_project_dialog import DetachProjectDialog
        from src.core.project.project_command_handler import detach

        project_display = (
            s.engine.project_meta.display_name
            if s.engine.project_meta
            else Path(s.config.sandbox_root).name
        )
        dlg = DetachProjectDialog(
            s.root, project_name=project_display, archive_dir=str(s.engine.vault.vault_dir)
        )
        if not dlg.result or not dlg.result.get("confirmed"):
            return
        detach(s, keep_sidecar=bool(dlg.result.get("keep_sidecar")))

    elif label == "Clear":
        from tkinter import messagebox
        if messagebox.askyesno("Clear Chat", "Clear the chat transcript? (Session history is preserved.)"):
            if s.ui_facade:
                s.ui_facade.clear_chat()
            s.engine.clear_history()
            s.activity.info("ui", "Chat transcript cleared")

    else:
        s.activity.info("ui", f"Button '{label}' clicked (reserved)")
