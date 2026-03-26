"""Faux-button action routing for the control pane."""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.app_state import AppState

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def dispatch_faux_click(s: AppState, label: str) -> None:
    """Route control-panel button labels to their action shims."""
    if label == "Attach Self":
        _handle_attach_self(s)
    elif label == "Sync to Source":
        from src.core.project.sync_command_handler import sync_to_source

        sync_to_source(s)
    elif label in ("Add Ref", "Import"):
        _handle_add_ref(s)
    elif label == "Add Parts":
        _handle_add_parts(s)
    elif label == "Tools":
        _handle_tools(s)
    elif label == "Plan":
        _handle_plan(s)
    elif label == "Detach":
        _handle_detach(s)
    elif label == "Clear":
        _handle_clear(s)
    else:
        s.activity.info("ui", f"Button '{label}' clicked (reserved)")


def _handle_attach_self(s: AppState) -> None:
    dest_root = filedialog.askdirectory(
        title="Choose working copy destination for self-edit",
        initialdir=str(_PROJECT_ROOT.parent),
    )
    if not dest_root:
        return
    from src.core.project.project_command_handler import attach_self

    attach_self(s, dest_root)


def _handle_add_ref(s: AppState) -> None:
    src_dir = filedialog.askdirectory(
        title="Select folder to add to Bookshelf (.mindshard/ref/)",
    )
    if not src_dir:
        return
    from src.core.project.project_command_handler import add_ref

    add_ref(s, src_dir)


def _handle_add_parts(s: AppState) -> None:
    src_dir = filedialog.askdirectory(
        title="Select folder to add to Parts Bin (.mindshard/parts/)",
    )
    if not src_dir:
        return
    from src.core.project.project_command_handler import add_parts

    add_parts(s, src_dir)


def _handle_tools(s: AppState) -> None:
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


def _handle_plan(s: AppState) -> None:
    from tkinter import simpledialog
    from src.core.agent.thought_chain_command_handler import run_thought_chain

    goal = simpledialog.askstring(
        "Thought Chain",
        "Enter a goal to decompose into tasks:",
        parent=s.root,
    )
    if not goal or not goal.strip():
        return
    run_thought_chain(s, goal.strip(), depth=3)


def _handle_detach(s: AppState) -> None:
    from src.core.project.project_command_handler import detach
    from src.ui.dialogs.detach_project_dialog import DetachProjectDialog

    if not s.config.sandbox_root:
        if s.ui_facade:
            s.ui_facade.post_system_message("No project attached.")
        return

    project_display = (
        s.engine.project_meta.display_name
        if s.engine.project_meta
        else Path(s.config.sandbox_root).name
    )
    dlg = DetachProjectDialog(
        s.root,
        project_name=project_display,
        archive_dir=str(s.engine.vault.vault_dir),
    )
    if not dlg.result or not dlg.result.get("confirmed"):
        return
    detach(s, keep_sidecar=bool(dlg.result.get("keep_sidecar")))


def _handle_clear(s: AppState) -> None:
    from tkinter import messagebox

    if messagebox.askyesno("Clear Chat", "Clear the chat transcript? (Session history is preserved.)"):
        if s.ui_facade:
            s.ui_facade.clear_chat()
        s.engine.clear_history()
        s.activity.info("ui", "Chat transcript cleared")
