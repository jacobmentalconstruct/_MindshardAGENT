"""
FILE: project_command_handler.py
ROLE: Project lifecycle command orchestrator (project + sandbox + sessions).
WHAT IT OWNS:
  - attach_sandbox: wire a chosen directory as the active project sandbox
  - attach_self: create a self-edit working copy and attach it
  - detach: archive and detach the current project
  - add_ref: load a folder into .mindshard/ref/ (bookshelf)
  - add_parts: load a folder into .mindshard/parts/ (parts bin)
  - _reinit_stores: shared store reinitialization after sandbox change

These functions own the WORKFLOW DECISION — what sequence of project/sandbox/session
steps to perform on each command. UI feedback is delivered via AppState threading
helpers (s.safe_ui, s.activity). Deep UI refreshes (vcs_panel, tool_count) are
called here as-is until the UI facade is built in Phase 1B.2.

Domains: project + sandbox + sessions (3 — valid fringe manager: tightly coupled
         during project lifecycle transitions; see builder contract Phase 1B.1)
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING

import src.core.runtime.action_journal as aj
from src.core.sessions.session_store import SessionStore
from src.core.sessions.knowledge_store import KnowledgeStore

if TYPE_CHECKING:
    from src.app_state import AppState

# Project root for self-edit source reference
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


# ── Shared store reinitialization ─────────────────────────────────────────────

def _reinit_stores(s: AppState, sandbox_root: str) -> None:
    """Re-initialize session and knowledge stores for a new sandbox root.

    Owns the store lifecycle decision: close old stores, open new ones at the
    canonical .mindshard/sessions/ path, and wire them into the engine.
    """
    new_db = Path(sandbox_root) / ".mindshard" / "sessions" / "sessions.db"
    s.session_store.close()
    s.session_store = SessionStore(new_db)
    s.knowledge_store = KnowledgeStore(new_db)
    s.engine.set_knowledge_store(
        s.knowledge_store,
        session_id_fn=lambda: s.active_session_id,
    )


# ── Attach sandbox ─────────────────────────────────────────────────────────────

def attach_sandbox(s: AppState, new_root: str, brief_data: dict | None = None) -> None:
    """Attach a chosen directory as the active project sandbox.

    Wires config, engine sandbox, project meta, stores, and UI paths.
    Called after the file dialog and optional brief dialog complete in app_commands.py.
    """
    from src.app_session import on_session_new, refresh_session_list  # noqa: F401
    from src.app_prompt import refresh_prompt_inspector
    from src.app_prompt_lab import refresh_prompt_lab_summary

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
    model = s.config.primary_chat_model or s.config.selected_model
    s.ui_state.selected_model = model
    s.engine.tokenizer.set_model(model)
    s.window.set_model(model)

    _reinit_stores(s, new_root)
    on_session_new(s)

    s.activity.info("project", f"Project attached: {display} [{profile}] at {new_root}")

    sandbox_tool_names = s.engine.tool_catalog.discovered_tool_names()
    if s.ui_facade:
        s.ui_facade.set_models(s.ui_state.available_models, model)
        s.ui_facade.set_tool_count(len(sandbox_tool_names), sandbox_tool_names)
        s.ui_facade.refresh_vcs()
    refresh_prompt_inspector(s)
    refresh_prompt_lab_summary(s, announce=False)


# ── Attach self (self-edit working copy) ──────────────────────────────────────

def attach_self(s: AppState, dest_root: str) -> None:
    """Create a self-edit working copy and attach it as the active sandbox.

    Runs the file-copy step on a background thread, then finishes wiring on
    the UI thread via s.safe_ui. Owns the full self-edit setup sequence.
    """
    from src.app_session import on_session_new
    from src.app_prompt import refresh_prompt_inspector
    from src.app_prompt_lab import refresh_prompt_lab_summary
    from src.core.sandbox.project_loader import load_project, list_project_files
    from src.core.project.project_meta import PROFILE_SELF_EDIT
    from src.core.utils.clock import utc_iso

    if s.ui_facade:
        s.ui_facade.post_system_message(f"Creating self-edit working copy at {dest_root}...")
    s.window.set_status("Loading...")

    def _do_load_self():
        target = Path(_PROJECT_ROOT).name
        load_project(_PROJECT_ROOT, dest_root, target_name=target)
        files = list_project_files(dest_root, target_name=target)
        actual_root = str(Path(dest_root) / target)
        s.safe_ui(lambda: _finish_load_self(actual_root, len(files)))

    def _finish_load_self(actual_root: str, file_count: int):
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
        model = s.config.primary_chat_model or s.config.selected_model
        s.ui_state.selected_model = model
        s.engine.tokenizer.set_model(model)
        s.window.set_model(model)

        _reinit_stores(s, actual_root)
        on_session_new(s)

        if s.ui_facade:
            s.ui_facade.post_system_message(
                f"Self-edit working copy ready ({file_count} files). "
                f"Source is YOUR MindshardAGENT code. "
                f"Sync Back will write changes to the real source at {_PROJECT_ROOT}."
            )
        if s.engine.journal:
            s.engine.journal.record(
                aj.PROJECT_LOAD,
                f"Self-edit: loaded {file_count} source files",
                {"file_count": file_count, "dest": actual_root, "source": str(_PROJECT_ROOT)},
            )

        sandbox_tool_names = s.engine.tool_catalog.discovered_tool_names()
        if s.ui_facade:
            s.ui_facade.set_models(s.ui_state.available_models, model)
            s.ui_facade.set_tool_count(len(sandbox_tool_names), sandbox_tool_names)
            s.ui_facade.refresh_vcs()
        refresh_prompt_inspector(s)
        refresh_prompt_lab_summary(s, announce=False)

    threading.Thread(target=_do_load_self, daemon=True, name="load-self").start()


# ── Detach project ─────────────────────────────────────────────────────────────

def detach(s: AppState, keep_sidecar: bool) -> None:
    """Archive and detach the current project.

    Owns the detach workflow: disable input, run archive on background thread,
    refresh UI on completion. Called after the confirmation dialog in app_commands.py.
    """
    project_display = (
        s.engine.project_meta.display_name
        if s.engine.project_meta
        else Path(s.config.sandbox_root).name
    )

    s.window.set_status("Detaching ...")
    if s.ui_facade:
        s.ui_facade.post_system_message(f"Detaching project '{project_display}' ...")
    if s.ui_facade:
        s.ui_facade.set_input_enabled(False)

    def _do_detach():
        def _prog(msg: str):
            s.safe_ui(lambda m=msg: s.window.set_status(m))
        result = s.engine.detach_project(on_progress=_prog, keep_sidecar=keep_sidecar)
        s.safe_ui(lambda: _finish_detach(result))

    def _finish_detach(result: dict):
        from src.app_prompt_lab import refresh_prompt_lab_summary

        if s.ui_facade:
            s.ui_facade.set_input_enabled(True)
        if result["success"]:
            archive = result.get("archive_path", "")
            retained = bool(result.get("sidecar_retained"))
            s.window.set_status("Detached")
            sidecar_msg = (
                "The working copy still has `.mindshard/` for future reuse."
                if retained
                else "The working copy is clean — `.mindshard/` has been removed."
            )
            if s.ui_facade:
                s.ui_facade.post_system_message(
                    f"Project detached. Archive saved to:\n{archive}\n\n{sidecar_msg}"
                )
            s.window.set_project_name("")
            s.window.set_project_paths("", "")
            if s.ui_facade:
                s.ui_facade.clear_prompt_inspector()
                s.ui_facade.refresh_vcs()
            refresh_prompt_lab_summary(s, announce=False)
        else:
            s.window.set_status("Detach failed")
            if s.ui_facade:
                s.ui_facade.post_system_message(
                    f"Detach failed: {result.get('error', 'Unknown error')}"
                )

    threading.Thread(target=_do_detach, daemon=True, name="detach").start()


# ── Add reference material ─────────────────────────────────────────────────────

def add_ref(s: AppState, src_dir: str) -> None:
    """Load a folder into .mindshard/ref/ (bookshelf).

    Owns the load + journal record sequence for reference material.
    Called after the directory dialog in app_commands.py.
    """
    from src.core.sandbox.project_loader import load_project, list_project_files

    folder_name = Path(src_dir).name
    ref_target = f".mindshard/ref/{folder_name}"

    def _do_add_ref():
        load_project(src_dir, s.config.sandbox_root, target_name=ref_target)
        files = list_project_files(s.config.sandbox_root, target_name=ref_target)

        def _done():
            s.activity.info("ref", f"Added {len(files)} files to bookshelf: .mindshard/ref/{folder_name}/")
            if s.ui_facade:
                s.ui_facade.post_system_message(
                    f"Added {len(files)} file(s) to bookshelf at .mindshard/ref/{folder_name}/. "
                    f"Agent can read these as reference material."
                )
            if s.engine.journal:
                s.engine.journal.record(
                    aj.PROJECT_LOAD,
                    f"Added to bookshelf: '{folder_name}' ({len(files)} files)",
                    {"source": src_dir, "ref_folder": ref_target, "file_count": len(files)},
                )

        s.safe_ui(_done)

    threading.Thread(target=_do_add_ref, daemon=True, name="add-ref").start()


# ── Add parts bin material ─────────────────────────────────────────────────────

def add_parts(s: AppState, src_dir: str) -> None:
    """Load a folder into .mindshard/parts/ (parts bin).

    Owns the load + journal record sequence for reusable components.
    Called after the directory dialog in app_commands.py.
    """
    from src.core.sandbox.project_loader import load_project, list_project_files

    folder_name = Path(src_dir).name
    parts_target = f".mindshard/parts/{folder_name}"

    def _do_add_parts():
        load_project(src_dir, s.config.sandbox_root, target_name=parts_target)
        files = list_project_files(s.config.sandbox_root, target_name=parts_target)

        def _done():
            s.activity.info("parts", f"Added {len(files)} files to parts bin: .mindshard/parts/{folder_name}/")
            if s.ui_facade:
                s.ui_facade.post_system_message(
                    f"Added {len(files)} file(s) to parts bin at .mindshard/parts/{folder_name}/. "
                    f"Agent can reuse these components."
                )
            if s.engine.journal:
                s.engine.journal.record(
                    aj.PROJECT_LOAD,
                    f"Added to parts bin: '{folder_name}' ({len(files)} files)",
                    {"source": src_dir, "parts_folder": parts_target, "file_count": len(files)},
                )

        s.safe_ui(_done)

    threading.Thread(target=_do_add_parts, daemon=True, name="add-parts").start()
