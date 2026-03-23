"""Action-button command handlers — extracted from app.py.

Handles the _handle_faux_click dispatcher and standalone callbacks
for model selection, CLI, sandbox picker, settings, etc.
"""

from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog
from typing import TYPE_CHECKING

from src.core.agent.model_roles import PRIMARY_CHAT_ROLE, current_model_roles, resolve_model_for_role
from src.core.sessions.session_store import SessionStore
from src.core.sessions.knowledge_store import KnowledgeStore
import src.core.runtime.action_journal as aj

if TYPE_CHECKING:
    from src.app_state import AppState

# Project root for self-edit / override paths
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ── Model callbacks ───────────────────────────────

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
                if s.app_closing["value"]:
                    return
                primary_model = resolve_model_for_role(s.config, PRIMARY_CHAT_ROLE)
                s.window.control_pane.model_picker.set_models(models, primary_model)
                s.ui_state.available_models = models
                s.activity.info("model", f"Found {len(models)} model(s)")
                s.window.set_status("Ready — refresh models to begin")
            s.safe_ui(_apply)
        except Exception as e:
            def _scan_error_ui(err=e):
                s.activity.error("model", f"Scan failed: {err}")
                s.window.set_status("Model refresh failed")
            s.safe_ui(_scan_error_ui)

    threading.Thread(target=_worker, daemon=True, name="model-refresh").start()


# ── CLI panel callback ────────────────────────────

def on_cli_command(s: AppState, command: str) -> None:
    s.activity.tool("cli_panel", f"User CLI: {command}")

    def _run():
        result = s.engine.run_cli(command)
        s.safe_ui(lambda: s.window.cli_pane.show_result(result))

    threading.Thread(target=_run, daemon=True, name="cli-panel").start()


# ── Sandbox picker callback ───────────────────────

def on_sandbox_pick(s: AppState) -> None:
    from src.app_session import on_session_new, refresh_session_list
    from src.app_prompt import refresh_prompt_inspector

    new_root = filedialog.askdirectory(
        title="Attach Project — Select Project Folder",
        initialdir=s.config.sandbox_root,
    )
    if not new_root:
        return

    from src.ui.dialogs.project_brief_dialog import ProjectBriefDialog
    from src.core.project.project_meta import ProjectMeta
    from src.core.utils.clock import utc_iso

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

    s.config.sandbox_root = new_root
    s.engine.set_sandbox(new_root)

    if brief_data:
        s.engine.project_meta.update(brief_data)

    profile = s.engine.project_meta.get("profile", "standard")
    display = s.engine.project_meta.display_name
    source_path = s.engine.project_meta.source_path or ""
    s.window.set_project_paths(source_path, new_root)
    s.window.set_project_name(display)
    s.ui_state.sandbox_root = new_root

    # Re-initialize stores for new sandbox
    new_db = Path(new_root) / ".mindshard" / "sessions" / "sessions.db"
    s.session_store.close()
    s.session_store = SessionStore(new_db)
    s.knowledge_store = KnowledgeStore(new_db)
    s.engine.set_knowledge_store(
        s.knowledge_store,
        session_id_fn=lambda: s.active_session["sid"],
    )

    on_session_new(s)
    s.activity.info("project", f"Project attached: {display} [{profile}] at {new_root}")

    sandbox_tool_names = s.engine.tool_catalog.sandbox_tool_names()
    s.window.control_pane.set_tool_count(len(sandbox_tool_names), sandbox_tool_names)
    s.window.control_pane.vcs_panel.refresh()
    refresh_prompt_inspector(s)


# ── Misc callbacks ────────────────────────────────

def on_import(s: AppState) -> None:
    handle_faux_click(s, "Add Ref")


def on_reload_tools(s: AppState) -> None:
    if not s.config.sandbox_root:
        return
    names = s.engine.tool_catalog.reload_sandbox_tools(s.config.sandbox_root)
    s.window.control_pane.set_tool_count(len(names), names)
    s.activity.info("tools", f"Tools reloaded: {len(names)} available")


def on_reload_prompt_docs(s: AppState) -> None:
    from src.app_prompt import refresh_prompt_inspector
    refresh_prompt_inspector(s, s.ui_state.last_user_input, announce=True)


def on_set_tool_round_limit(s: AppState, value: int) -> None:
    s.config.max_tool_rounds = max(1, int(value))
    s.config.save(_PROJECT_ROOT)
    s.window.control_pane.set_tool_round_limit(s.config.max_tool_rounds)
    s.activity.info("tools", f"Max tool rounds set to {s.config.max_tool_rounds}")


# ── Settings dialog ───────────────────────────────

def on_open_settings(s: AppState) -> None:
    from src.ui.dialogs.settings_dialog import SettingsDialog
    from src.app_session import log_model_roles

    dialog = SettingsDialog(
        s.root,
        available_models=s.ui_state.available_models,
        initial_model_roles=current_model_roles(s.config),
        initial_tool_round_limit=s.config.max_tool_rounds,
        initial_gui_launch_policy=s.config.gui_launch_policy,
        initial_planning_enabled=s.config.planning_enabled,
        initial_recovery_planning_enabled=s.config.recovery_planning_enabled,
    )
    if not dialog.result:
        return

    role_updates = dialog.result.get("model_roles", {})
    s.config.primary_chat_model = str(role_updates.get(PRIMARY_CHAT_ROLE, s.config.primary_chat_model) or "").strip()
    s.config.selected_model = s.config.primary_chat_model
    s.config.planner_model = str(role_updates.get("planner", s.config.planner_model) or "").strip()
    s.config.recovery_planner_model = str(
        role_updates.get("recovery_planner", s.config.recovery_planner_model) or ""
    ).strip()
    s.config.coding_model = str(role_updates.get("coding", s.config.coding_model) or "").strip()
    s.config.review_model = str(role_updates.get("review", s.config.review_model) or "").strip()
    s.config.fast_probe_model = str(role_updates.get("fast_probe", s.config.fast_probe_model) or "").strip()
    s.config.embedding_model = str(role_updates.get("embedding", s.config.embedding_model) or "").strip()
    s.config.max_tool_rounds = max(1, int(dialog.result.get("max_tool_rounds", s.config.max_tool_rounds)))
    s.config.gui_launch_policy = str(dialog.result.get("gui_launch_policy", s.config.gui_launch_policy) or "ask")
    s.config.planning_enabled = bool(dialog.result.get("planning_enabled", s.config.planning_enabled))
    s.config.recovery_planning_enabled = bool(
        dialog.result.get("recovery_planning_enabled", s.config.recovery_planning_enabled)
    )
    s.config.normalize_model_roles()
    s.config.save(_PROJECT_ROOT)
    s.ui_state.selected_model = s.config.primary_chat_model
    s.engine.tokenizer.set_model(s.config.primary_chat_model)
    s.window.set_model(s.config.primary_chat_model)
    s.window.control_pane.model_picker.set_models(s.ui_state.available_models, s.config.primary_chat_model)
    s.window.control_pane.set_tool_round_limit(s.config.max_tool_rounds)
    s.window.set_status(
        f"Settings saved — primary={s.config.primary_chat_model or '(none)'}, "
        f"planner={s.config.planner_model or '(none)'}, tool rounds: {s.config.max_tool_rounds}"
    )
    s.activity.info(
        "settings",
        f"Updated settings: primary={s.config.primary_chat_model or '(none)'}, "
        f"planner={s.config.planner_model or '(none)'}, "
        f"recovery_planner={s.config.recovery_planner_model or '(none)'}, "
        f"gui_launch_policy={s.config.gui_launch_policy}, "
        f"planning_enabled={s.config.planning_enabled}, "
        f"recovery_planning_enabled={s.config.recovery_planning_enabled}, "
        f"max_tool_rounds={s.config.max_tool_rounds}",
    )
    log_model_roles(s)


# ── Project brief / prompt overrides ──────────────

def on_edit_project_brief(s: AppState) -> None:
    from src.app_prompt import refresh_prompt_inspector, snapshot_prompt_state

    if not s.engine.project_meta:
        s.window.chat_pane.add_message("system", "No project attached.")
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
        s.window.chat_pane.add_message("system", "No project attached.")
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


# ── Faux button dispatcher ───────────────────────

def handle_faux_click(s: AppState, label: str) -> None:
    from src.app_session import on_session_new
    from src.app_prompt import refresh_prompt_inspector

    if label == "Attach Self":
        dest_root = filedialog.askdirectory(
            title="Choose working copy destination for self-edit",
            initialdir=str(_PROJECT_ROOT.parent),
        )
        if not dest_root:
            return

        from src.core.sandbox.project_loader import load_project, list_project_files
        from src.core.project.project_meta import PROFILE_SELF_EDIT
        from src.core.utils.clock import utc_iso

        s.window.chat_pane.add_message("system", f"Creating self-edit working copy at {dest_root}...")
        s.window.set_status("Loading...")

        def _do_load_self():
            target = Path(_PROJECT_ROOT).name
            load_project(_PROJECT_ROOT, dest_root, target_name=target)
            files = list_project_files(dest_root, target_name=target)
            actual_root = str(Path(dest_root) / target)
            s.safe_ui(lambda: _finish_load_self(actual_root, len(files)))

        def _finish_load_self(actual_root, file_count):
            s.config.sandbox_root = actual_root
            s.engine.set_sandbox(actual_root)

            brief_data = {
                "display_name": Path(actual_root).name + " (self-edit)",
                "project_purpose": "MindshardAGENT self-iteration — agent edits its own source",
                "current_goal": "Iterate on MindshardAGENT source code",
                "project_type": "Python app",
                "constraints": "",
                "profile": PROFILE_SELF_EDIT,
                "source_path": str(_PROJECT_ROOT),
                "attached_at": utc_iso(),
            }
            s.engine.project_meta.update(brief_data)

            s.window.set_project_paths(str(_PROJECT_ROOT), actual_root)
            s.window.set_project_name(Path(actual_root).name + " (self-edit)")
            s.window.set_status("Ready")
            s.ui_state.sandbox_root = actual_root

            new_db = Path(actual_root) / ".mindshard" / "sessions" / "sessions.db"
            s.session_store.close()
            s.session_store = SessionStore(new_db)
            s.knowledge_store = KnowledgeStore(new_db)
            s.engine.set_knowledge_store(
                s.knowledge_store,
                session_id_fn=lambda: s.active_session["sid"],
            )
            on_session_new(s)

            s.window.chat_pane.add_message("system",
                f"Self-edit working copy ready ({file_count} files). "
                f"Source is YOUR MindshardAGENT code. "
                f"Sync Back will write changes to the real source at {_PROJECT_ROOT}.")
            if s.engine.journal:
                s.engine.journal.record(aj.PROJECT_LOAD,
                    f"Self-edit: loaded {file_count} source files",
                    {"file_count": file_count, "dest": actual_root,
                     "source": str(_PROJECT_ROOT)})

            sandbox_tool_names = s.engine.tool_catalog.sandbox_tool_names()
            s.window.control_pane.set_tool_count(len(sandbox_tool_names), sandbox_tool_names)
            s.window.control_pane.vcs_panel.refresh()
            refresh_prompt_inspector(s)

        threading.Thread(target=_do_load_self, daemon=True, name="load-self").start()

    elif label == "Sync to Source":
        from src.core.sandbox.project_syncer import diff_sandbox_to_source, apply_sync, log_sync

        sync_source = None
        if s.engine.project_meta:
            sync_source = s.engine.project_meta.source_path
        if not sync_source:
            s.activity.info("sync", "No source_path set — in-place project, sync unavailable")
            s.window.chat_pane.add_message("system",
                "Sync Back is unavailable for in-place projects (no original source path configured).")
            return

        diff = diff_sandbox_to_source(s.config.sandbox_root, sync_source, target_name="")

        if diff.get("error"):
            s.activity.error("sync", diff["error"])
            s.window.chat_pane.add_message("system", f"Sync failed: {diff['error']}")
            return

        n_add = len(diff["added"])
        n_mod = len(diff["modified"])
        n_del = len(diff["removed"])

        if n_add == 0 and n_mod == 0 and n_del == 0:
            s.activity.info("sync", "No changes to sync — project matches source")
            s.window.chat_pane.add_message("system", "No changes detected — project matches source.")
            return

        summary_lines = []
        if n_add:
            summary_lines.append(f"  + {n_add} new file(s): {', '.join(diff['added'][:5])}")
            if n_add > 5:
                summary_lines.append(f"    ... and {n_add - 5} more")
        if n_mod:
            summary_lines.append(f"  ~ {n_mod} modified: {', '.join(diff['modified'][:5])}")
            if n_mod > 5:
                summary_lines.append(f"    ... and {n_mod - 5} more")
        if n_del:
            summary_lines.append(f"  - {n_del} deleted: {', '.join(diff['removed'][:5])}")
            if n_del > 5:
                summary_lines.append(f"    ... and {n_del - 5} more")

        summary_text = "\n".join(summary_lines)
        from tkinter import messagebox
        proceed = messagebox.askyesno("Sync Back to Source",
            f"Apply project changes to source at:\n{sync_source}\n\n{summary_text}\n\n"
            f"Deletions will NOT be applied (safety).\n"
            f"This overwrites real source files.")
        if not proceed:
            s.activity.info("sync", "Sync cancelled by user")
            return

        result = apply_sync(s.config.sandbox_root, sync_source, target_name="", apply_deletes=False)
        log_sync(s.config.sandbox_root, result, direction="sandbox_to_source")

        total = result["total_applied"]
        errors = len(result["errors"])
        s.activity.info("sync",
            f"Sync complete: +{len(result['added'])} ~{len(result['modified'])} ({errors} errors)")
        s.window.chat_pane.add_message("system",
            f"Synced {total} file(s) back to source. "
            f"+{len(result['added'])} new, ~{len(result['modified'])} modified. "
            f"{f'{errors} error(s).' if errors else 'No errors.'}")

        if s.engine.journal:
            s.engine.journal.record(aj.PROJECT_SYNC,
                f"Synced {total} files: +{len(result['added'])} ~{len(result['modified'])}",
                {"added": result["added"], "modified": result["modified"],
                 "errors": result["errors"]})

        if s.engine.vcs.is_attached:
            snap_msg = (f"Post-sync snapshot: +{len(result['added'])} "
                        f"~{len(result['modified'])} files")
            try:
                commit_hash = s.engine.vcs.snapshot(snap_msg)
                if commit_hash:
                    s.activity.info("vcs", f"Snapshot committed: {commit_hash[:8]}")
            except Exception as vcs_err:
                s.log.warning("VCS snapshot failed: %s", vcs_err)

    elif label in ("Add Ref", "Import"):
        from src.core.sandbox.project_loader import load_project, list_project_files
        src_dir = filedialog.askdirectory(
            title="Select folder to add to Bookshelf (.mindshard/ref/)",
        )
        if not src_dir:
            return
        folder_name = Path(src_dir).name
        ref_target = f".mindshard/ref/{folder_name}"

        def _do_add_ref():
            load_project(src_dir, s.config.sandbox_root, target_name=ref_target)
            files = list_project_files(s.config.sandbox_root, target_name=ref_target)
            def _done():
                s.activity.info("ref", f"Added {len(files)} files to bookshelf: .mindshard/ref/{folder_name}/")
                s.window.chat_pane.add_message("system",
                    f"Added {len(files)} file(s) to bookshelf at .mindshard/ref/{folder_name}/. "
                    f"Agent can read these as reference material.")
                if s.engine.journal:
                    s.engine.journal.record(aj.PROJECT_LOAD,
                        f"Added to bookshelf: '{folder_name}' ({len(files)} files)",
                        {"source": src_dir, "ref_folder": ref_target, "file_count": len(files)})
            s.safe_ui(_done)
        threading.Thread(target=_do_add_ref, daemon=True, name="add-ref").start()

    elif label == "Add Parts":
        from src.core.sandbox.project_loader import load_project, list_project_files
        src_dir = filedialog.askdirectory(
            title="Select folder to add to Parts Bin (.mindshard/parts/)",
        )
        if not src_dir:
            return
        folder_name = Path(src_dir).name
        parts_target = f".mindshard/parts/{folder_name}"

        def _do_add_parts():
            load_project(src_dir, s.config.sandbox_root, target_name=parts_target)
            files = list_project_files(s.config.sandbox_root, target_name=parts_target)
            def _done():
                s.activity.info("parts", f"Added {len(files)} files to parts bin: .mindshard/parts/{folder_name}/")
                s.window.chat_pane.add_message("system",
                    f"Added {len(files)} file(s) to parts bin at .mindshard/parts/{folder_name}/. "
                    f"Agent can reuse these components.")
                if s.engine.journal:
                    s.engine.journal.record(aj.PROJECT_LOAD,
                        f"Added to parts bin: '{folder_name}' ({len(files)} files)",
                        {"source": src_dir, "parts_folder": parts_target, "file_count": len(files)})
            s.safe_ui(_done)
        threading.Thread(target=_do_add_parts, daemon=True, name="add-parts").start()

    elif label == "Tools":
        tools_dir = Path(s.config.sandbox_root) / ".mindshard" / "tools"
        tools = list(tools_dir.glob("*.py")) if tools_dir.exists() else []
        if tools:
            names = ", ".join(t.stem for t in tools)
            s.activity.info("tools", f"Sandbox tools: {names}")
        else:
            s.activity.info("tools", "No sandbox tools found. Agent can create them in .mindshard/tools/")

    elif label == "Plan":
        from tkinter import simpledialog
        goal = simpledialog.askstring("Thought Chain", "Enter a goal to decompose into tasks:", parent=s.root)
        if not goal or not goal.strip():
            return

        s.window.chat_pane.add_message("system", f"Starting thought chain for: {goal}")
        s.window.set_status("Planning...")

        def _on_ctc_round(round_num: int, text: str):
            s.safe_ui(lambda: s.window.chat_pane.add_message("system", f"[Plan round {round_num}]\n{text}"))

        def _on_ctc_complete(result: dict):
            def _finish():
                tasks = result.get("tasks", [])
                if tasks:
                    task_lines = "\n".join(
                        f"  {t['number']}. {'[' + t['complexity'] + '] ' if t['complexity'] else ''}{t['text']}"
                        for t in tasks
                    )
                    s.window.chat_pane.add_message("system", f"Task list ({len(tasks)} tasks):\n{task_lines}")
                else:
                    s.window.chat_pane.add_message("system",
                        f"Plan complete (no structured tasks extracted):\n{result.get('final_text', '')}")
                s.window.set_status("Ready")
                if s.engine.journal:
                    s.engine.journal.record(aj.AGENT_TURN,
                        f"CTC plan: {len(tasks)} tasks for '{goal[:50]}'",
                        {"goal": goal, "task_count": len(tasks),
                         "tasks": [t["text"] for t in tasks[:10]]})
            s.safe_ui(_finish)

        def _on_ctc_error(err: str):
            def _ctc_error_ui():
                s.window.chat_pane.add_message("system", f"Plan failed: {err}")
                s.window.set_status("Ready")
            s.safe_ui(_ctc_error_ui)

        s.engine.run_thought_chain(
            goal=goal.strip(),
            depth=3,
            on_round=_on_ctc_round,
            on_complete=_on_ctc_complete,
            on_error=_on_ctc_error,
        )

    elif label == "Detach":
        if not s.config.sandbox_root:
            s.window.chat_pane.add_message("system", "No project attached.")
            return
        from src.ui.dialogs.detach_project_dialog import DetachProjectDialog

        project_display = s.engine.project_meta.display_name if s.engine.project_meta else Path(s.config.sandbox_root).name
        dlg = DetachProjectDialog(s.root, project_name=project_display, archive_dir=str(s.engine.vault.vault_dir))
        if not dlg.result or not dlg.result.get("confirmed"):
            return
        keep_sidecar = bool(dlg.result.get("keep_sidecar"))

        s.window.set_status("Detaching ...")
        s.window.chat_pane.add_message("system", f"Detaching project '{project_display}' ...")
        s.window.control_pane.input_pane.set_enabled(False)

        def _do_detach():
            def _prog(msg):
                s.safe_ui(lambda m=msg: s.window.set_status(m))
            result = s.engine.detach_project(on_progress=_prog, keep_sidecar=keep_sidecar)
            s.safe_ui(lambda: _finish_detach(result))

        def _finish_detach(result):
            s.window.control_pane.input_pane.set_enabled(True)
            if result["success"]:
                archive = result.get("archive_path", "")
                retained = bool(result.get("sidecar_retained"))
                s.window.set_status("Detached")
                sidecar_msg = (
                    "The working copy still has `.mindshard/` for future reuse."
                    if retained else
                    "The working copy is clean — `.mindshard/` has been removed."
                )
                s.window.chat_pane.add_message("system",
                    f"Project detached. Archive saved to:\n{archive}\n\n{sidecar_msg}")
                s.window.set_project_name("")
                s.window.set_project_paths("", "")
                s.window.control_pane.set_prompt_inspector("", "")
                s.window.control_pane.vcs_panel.refresh()
            else:
                s.window.set_status("Detach failed")
                s.window.chat_pane.add_message("system",
                    f"Detach failed: {result.get('error', 'Unknown error')}")

        threading.Thread(target=_do_detach, daemon=True, name="detach").start()

    elif label == "Clear":
        from tkinter import messagebox
        if messagebox.askyesno("Clear Chat", "Clear the chat transcript? (Session history is preserved.)"):
            s.window.chat_pane.clear()
            s.engine.clear_history()
            s.activity.info("ui", "Chat transcript cleared")

    else:
        s.activity.info("ui", f"Button '{label}' clicked (reserved)")
