"""Application entry point and composition root.

Responsibilities:
  - bootstrap logging
  - load config
  - create runtime infrastructure (activity stream, event bus)
  - create engine with sandbox support
  - create and launch the GUI
  - manage app lifecycle
"""

import sys
import threading
import tkinter as tk
from tkinter import filedialog
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
from src.core.sessions.session_store import SessionStore
from src.core.sessions.knowledge_store import KnowledgeStore
from src.core.registry.state_registry import StateRegistry
from src.core.registry.session_registry import register_session, register_message
from src.ui.ui_state import UIState
from src.ui.gui_main import MainWindow
import src.core.runtime.action_journal as aj


def main() -> None:
    # ── Load config ───────────────────────────────────
    config = AppConfig.load(PROJECT_ROOT)

    # ── Init logging ──────────────────────────────────
    log_dir = PROJECT_ROOT / config.log_dir
    init_logging(log_dir=log_dir)
    log = get_logger("app")
    log.info("=== MindshardAGENT starting ===")
    log.info("Project root: %s", PROJECT_ROOT)

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

        root.after(0, _ask)
        _confirm_result["event"].wait(timeout=60)
        return _confirm_result["value"]

    # ── Engine ────────────────────────────────────────
    def _on_tools_reloaded(count: int, names: list):
        """Update tool count badge on the main thread."""
        root.after(0, lambda: window.control_pane.set_tool_count(count, names))

    engine = Engine(config=config, activity=activity, bus=bus,
                    on_confirm_destructive=_confirm_destructive,
                    on_tools_reloaded=_on_tools_reloaded)

    # ── Default sandbox ───────────────────────────────
    default_sandbox = PROJECT_ROOT / "_sandbox"
    if not config.sandbox_root:
        config.sandbox_root = str(default_sandbox)
    engine.set_sandbox(config.sandbox_root)

    # ── Session store ─────────────────────────────────
    sessions_db = Path(config.sandbox_root) / ".mindshard" / "sessions" / "sessions.db"
    session_store = SessionStore(sessions_db)

    # ── Knowledge store (RAG) ─────────────────────────
    knowledge_store = KnowledgeStore(session_store._conn)
    engine.set_knowledge_store(
        knowledge_store,
        session_id_fn=lambda: active_session["sid"],
    )

    # ── Active session tracking ───────────────────────
    active_session = {"sid": None, "node_id": None}
    _autosave_timer = {"id": None}

    # ── Streaming state ───────────────────────────────
    _streaming_content: list[str] = []
    _stream_flush_id = {"id": None}   # timer ID for chunked flush
    _stream_dirty = {"val": False}    # new tokens since last flush

    # ── Session helpers ───────────────────────────────

    def _refresh_session_list():
        sessions = session_store.list_sessions()
        window.control_pane.session_panel.set_sessions(sessions, active_session["sid"])

    def _load_session(sid: str):
        """Switch to a session — load its messages into chat and engine."""
        session = session_store.get_session(sid)
        if not session:
            activity.error("session", f"Session not found: {sid}")
            return

        active_session["sid"] = sid
        # Register in state registry
        active_session["node_id"] = register_session(
            registry, sid, session["title"], session.get("active_model", ""))

        # Load messages into engine chat history
        messages = session_store.get_messages(sid)
        history = [{"role": m["role"], "content": m["content"]} for m in messages]
        engine.set_history(history)

        # Rebuild chat pane
        window.chat_pane.clear()
        for m in messages:
            window.chat_pane.add_message(m["role"], m["content"])

        window.set_session_title(session["title"])
        window.set_save_dirty(False)
        ui_state.session_title = session["title"]

        # Apply per-session command policy overrides
        policy = session_store.get_command_policy(sid)
        if policy and engine.command_policy:
            engine.command_policy.apply_session_overrides(policy)
        elif engine.command_policy:
            engine.command_policy.clear_session_overrides()

        activity.info("session", f"Loaded session: {session['title']}")
        _refresh_session_list()

    def _save_current_session():
        """Persist current chat history to the active session."""
        sid = active_session["sid"]
        if not sid:
            return
        session_store.save_session(sid, model=config.selected_model)
        window.set_save_dirty(False)
        activity.info("session", "Session saved")

    def _schedule_autosave():
        """Debounced autosave — saves 3 seconds after last turn completion."""
        if _autosave_timer["id"] is not None:
            root.after_cancel(_autosave_timer["id"])
        _autosave_timer["id"] = root.after(3000, _save_current_session)

    # ── Session callbacks ─────────────────────────────

    def on_session_new():
        sid = session_store.new_session(
            model=config.selected_model,
            sandbox_root=config.sandbox_root,
        )
        _load_session(sid)
        session = session_store.get_session(sid)
        title = session["title"] if session else sid
        activity.info("session", f"New session: {title}")
        if engine.journal:
            engine.journal.record(aj.SESSION_START, f"New session: {title}",
                                  {"session_id": sid, "title": title})

    def on_session_select(sid: str):
        if sid == active_session["sid"]:
            return
        _save_current_session()
        _load_session(sid)
        session = session_store.get_session(sid)
        if engine.journal:
            engine.journal.record(aj.SESSION_SWITCH,
                f"Switched to: {session['title'] if session else sid}",
                {"session_id": sid})

    def on_session_rename(sid: str, new_title: str):
        session_store.save_session(sid, title=new_title)
        if sid == active_session["sid"]:
            window.set_session_title(new_title)
            ui_state.session_title = new_title
        _refresh_session_list()
        activity.info("session", f"Renamed to: {new_title}")

    def on_session_delete(sid: str):
        session_store.delete_session(sid)
        if sid == active_session["sid"]:
            # Try to switch to another existing session first
            remaining = session_store.list_sessions()
            if remaining:
                _load_session(remaining[0]["session_id"])
            else:
                on_session_new()
        else:
            _refresh_session_list()
        activity.info("session", "Session deleted")

    def on_session_branch(sid: str):
        new_sid = session_store.branch_session(sid)
        _load_session(new_sid)
        activity.info("session", f"Session branched")

    def on_session_policy(sid: str):
        """Open a dialog to edit per-session command policy overrides."""
        from tkinter import simpledialog
        import json

        current = session_store.get_command_policy(sid)
        allow_add = ", ".join(current.get("allow_add", []))
        allow_remove = ", ".join(current.get("allow_remove", []))

        # Simple two-field dialog using askstring
        add_str = simpledialog.askstring(
            "Session Policy — Extra Allowed",
            "Commands to ADD to allowlist for this session\n"
            "(comma-separated, e.g. 'npm, yarn').\n"
            "Leave blank for defaults.\n"
            "Security-blocked commands (powershell, curl, etc.) cannot be added.",
            initialvalue=allow_add,
            parent=root,
        )
        if add_str is None:
            return  # cancelled

        remove_str = simpledialog.askstring(
            "Session Policy — Restricted",
            "Commands to REMOVE from allowlist for this session\n"
            "(comma-separated, e.g. 'git, rm').\n"
            "Leave blank for defaults.",
            initialvalue=allow_remove,
            parent=root,
        )
        if remove_str is None:
            return  # cancelled

        policy = {}
        adds = [c.strip() for c in add_str.split(",") if c.strip()]
        removes = [c.strip() for c in remove_str.split(",") if c.strip()]
        if adds:
            policy["allow_add"] = adds
        if removes:
            policy["allow_remove"] = removes

        session_store.set_command_policy(sid, policy)

        # Apply immediately if this is the active session
        if sid == active_session["sid"] and engine.command_policy:
            if policy:
                engine.command_policy.apply_session_overrides(policy)
            else:
                engine.command_policy.clear_session_overrides()

        desc = []
        if adds:
            desc.append(f"+{', '.join(adds)}")
        if removes:
            desc.append(f"-{', '.join(removes)}")
        msg = " | ".join(desc) if desc else "defaults"
        activity.info("policy", f"Session policy updated: {msg}")

    def _prompt_sources_text(prompt_build) -> str:
        lines = [
            f"Source fingerprint: {prompt_build.source_fingerprint[:12]}",
            f"Prompt fingerprint: {prompt_build.prompt_fingerprint[:12]}",
            "",
        ]
        if prompt_build.warnings:
            lines.append("Warnings:")
            for warning in prompt_build.warnings:
                lines.append(f"- {warning}")
            lines.append("")
        for section in prompt_build.sections:
            source = section.source_path or "(runtime)"
            lines.append(f"[{section.layer}] {section.name}")
            lines.append(source)
        return "\n".join(lines)

    def _set_prompt_inspector(prompt_build) -> None:
        if not prompt_build:
            return
        window.control_pane.set_prompt_inspector(
            prompt_text=prompt_build.prompt,
            sources_text=_prompt_sources_text(prompt_build),
        )

    def refresh_prompt_inspector(user_text: str = "", *, announce: bool = False):
        prompt_build = engine.preview_system_prompt(user_text=user_text)
        if prompt_build:
            _set_prompt_inspector(prompt_build)
            if announce:
                activity.info(
                    "prompt",
                    f"Prompt docs reloaded ({prompt_build.source_fingerprint[:12]})",
                )
        return prompt_build

    # ── Chat submit callback ──────────────────────────
    def on_submit(text: str):
        activity.info("user", f"Prompt submitted ({len(text)} chars)")
        ui_state.last_user_input = text
        window.chat_pane.add_message("user", text)
        window.control_pane.set_last_prompt(text)
        refresh_prompt_inspector(text)
        window.set_save_dirty(True)
        window.set_status("Thinking...")
        window.control_pane.input_pane.set_enabled(False)
        ui_state.is_streaming = True
        _streaming_content.clear()

        # Persist user message
        sid = active_session["sid"]
        if sid:
            mid = session_store.add_message(sid, "user", text)
            if active_session["node_id"]:
                register_message(registry, active_session["node_id"], "user", text[:50])

        # Placeholder assistant card for streaming
        window.chat_pane.add_message("assistant", "Thinking...")
        _stream_card = window.chat_pane._inner.winfo_children()[-1]
        _stream_dirty["val"] = False

        # ── Chunked streaming ──────────────────────────
        # Buffer tokens from the model thread; flush to UI every 150ms
        # instead of per-token. Much less main-thread pressure.
        FLUSH_INTERVAL_MS = 150

        def _on_token(token: str):
            _streaming_content.append(token)
            _stream_dirty["val"] = True

        def _flush_stream():
            """Called on main thread by a repeating timer."""
            if _stream_dirty["val"]:
                _stream_dirty["val"] = False
                try:
                    content = "".join(_streaming_content)
                    _stream_card.update_streaming_content(content)
                    window.chat_pane._inner.update_idletasks()
                    window.chat_pane._canvas.configure(
                        scrollregion=window.chat_pane._canvas.bbox("all"))
                    window.chat_pane._canvas.yview_moveto(1.0)
                except Exception:
                    pass
            # Keep pumping while streaming is active
            if ui_state.is_streaming:
                _stream_flush_id["id"] = root.after(FLUSH_INTERVAL_MS, _flush_stream)

        # Start the flush pump
        _stream_flush_id["id"] = root.after(FLUSH_INTERVAL_MS, _flush_stream)

        def _on_complete(result: dict):
            ui_state.is_streaming = False
            # Cancel flush timer
            if _stream_flush_id["id"] is not None:
                root.after_cancel(_stream_flush_id["id"])
                _stream_flush_id["id"] = None
            meta = result.get("metadata", {})
            root.after(0, _finish_stream, _stream_card, meta, result)

        def _finish_stream(card, meta, result):
            try:
                # Final flush — ensure all buffered content is shown
                content = result.get("content", "".join(_streaming_content))
                card.update_streaming_content(content)
                window.chat_pane._inner.update_idletasks()
                window.chat_pane._canvas.configure(
                    scrollregion=window.chat_pane._canvas.bbox("all"))
                window.chat_pane._canvas.yview_moveto(1.0)

                window.set_status("Ready")
                window.control_pane.input_pane.set_enabled(True)
                activity.info("chat",
                    f"Response: {meta.get('tokens_out', '?')} tokens, {meta.get('time', '?')}")

                # Update response preview in Watch tab
                window.control_pane.set_last_response(content)
                _set_prompt_inspector(result.get("prompt_build"))

                # Persist assistant message
                sid = active_session["sid"]
                if sid:
                    session_store.add_message(
                        sid, "assistant", content,
                        model_name=config.selected_model,
                        token_out=int(str(meta.get("tokens_out", "0")).replace("~", "") or 0),
                    )
                    if active_session["node_id"]:
                        register_message(registry, active_session["node_id"], "assistant", content[:50])

                _schedule_autosave()
            except Exception:
                pass

        def _on_error(err: str):
            ui_state.is_streaming = False
            # Cancel flush timer
            if _stream_flush_id["id"] is not None:
                root.after_cancel(_stream_flush_id["id"])
                _stream_flush_id["id"] = None
            root.after(0, _handle_error, err)

        def _handle_error(err):
            window.chat_pane.add_message("system", f"Error: {err}")
            window.set_status("Error — check model connection")
            window.control_pane.input_pane.set_enabled(True)

        engine.submit_prompt(
            user_text=text,
            on_token=_on_token,
            on_complete=_on_complete,
            on_error=_on_error,
        )

    # ── Model callbacks ───────────────────────────────
    def on_model_select(model: str):
        config.selected_model = model
        ui_state.selected_model = model
        engine.tokenizer.set_model(model)
        window.set_model(model)
        activity.info("model", f"Model selected: {model}")
        refresh_prompt_inspector(ui_state.last_user_input)

    def on_model_refresh():
        activity.info("model", "Model refresh requested")
        try:
            from src.core.ollama.model_scanner import scan_models
            models = scan_models(config.ollama_base_url)
            window.control_pane.model_picker.set_models(models, config.selected_model)
            ui_state.available_models = models
            activity.info("model", f"Found {len(models)} model(s)")
        except Exception as e:
            activity.error("model", f"Scan failed: {e}")

    # ── CLI panel callback ────────────────────────────
    def on_cli_command(command: str):
        activity.tool("cli_panel", f"User CLI: {command}")

        def _run():
            result = engine.run_cli(command)
            root.after(0, lambda: window.cli_pane.show_result(result))

        threading.Thread(target=_run, daemon=True, name="cli-panel").start()

    # ── Sandbox picker callback ───────────────────────
    def on_sandbox_pick():
        new_root = filedialog.askdirectory(
            title="Attach Project — Select Project Folder",
            initialdir=config.sandbox_root,
        )
        if not new_root:
            return

        # Show project brief dialog for new projects
        from src.ui.dialogs.project_brief_dialog import ProjectBriefDialog
        from src.core.project.project_meta import ProjectMeta
        from src.core.utils.clock import utc_iso

        folder_name = Path(new_root).name
        existing_meta = ProjectMeta(new_root)

        if not existing_meta.exists:
            # New project — require brief
            dlg = ProjectBriefDialog(root, project_name=folder_name)
            if dlg.result is None:
                return  # user cancelled
            brief_data = dlg.result
            brief_data["source_path"] = ""  # in-place for now
            brief_data["attached_at"] = utc_iso()
        else:
            brief_data = None  # existing meta, keep it

        config.sandbox_root = new_root
        engine.set_sandbox(new_root)

        if brief_data:
            engine.project_meta.update(brief_data)

        profile = engine.project_meta.get("profile", "standard")
        display = engine.project_meta.display_name
        source_path = engine.project_meta.source_path or ""
        window.set_project_paths(source_path, new_root)
        window.set_project_name(display)
        ui_state.sandbox_root = new_root

        # Re-initialize session store and knowledge store for new sandbox
        nonlocal session_store, knowledge_store
        new_db = Path(new_root) / ".mindshard" / "sessions" / "sessions.db"
        session_store.close()
        session_store = SessionStore(new_db)
        knowledge_store = KnowledgeStore(session_store._conn)
        engine.set_knowledge_store(
            knowledge_store,
            session_id_fn=lambda: active_session["sid"],
        )

        # Create initial session in new sandbox
        on_session_new()
        activity.info("project", f"Project attached: {display} [{profile}] at {new_root}")

        # Update tool count for new sandbox
        sandbox_tool_names = engine.tool_catalog.sandbox_tool_names()
        window.control_pane.set_tool_count(len(sandbox_tool_names), sandbox_tool_names)

        # Refresh VCS panel for new sandbox
        window.control_pane.vcs_panel.refresh()
        refresh_prompt_inspector()

    # ── Add Ref callback (bookshelf button in Sandbox tab) ─────
    def on_import():
        """Add reference material to .mindshard/ref/ — exposed directly in UI."""
        _handle_faux_click("Add Ref")

    # ── Reload tools callback (manual refresh from Watch tab) ─
    def on_reload_tools():
        if not config.sandbox_root:
            return
        names = engine.tool_catalog.reload_sandbox_tools(config.sandbox_root)
        window.control_pane.set_tool_count(len(names), names)
        activity.info("tools", f"Tools reloaded: {len(names)} available")

    def on_reload_prompt_docs():
        refresh_prompt_inspector(ui_state.last_user_input, announce=True)

    def on_set_tool_round_limit(value: int):
        config.max_tool_rounds = max(1, int(value))
        config.save(PROJECT_ROOT)
        window.control_pane.set_tool_round_limit(config.max_tool_rounds)
        activity.info("tools", f"Max tool rounds set to {config.max_tool_rounds}")

    def on_open_settings():
        from src.ui.dialogs.settings_dialog import SettingsDialog

        dialog = SettingsDialog(
            root,
            initial_tool_round_limit=config.max_tool_rounds,
            initial_gui_launch_policy=config.gui_launch_policy,
        )
        if not dialog.result:
            return

        config.max_tool_rounds = max(1, int(dialog.result.get("max_tool_rounds", config.max_tool_rounds)))
        config.gui_launch_policy = str(dialog.result.get("gui_launch_policy", config.gui_launch_policy) or "ask")
        config.save(PROJECT_ROOT)
        window.control_pane.set_tool_round_limit(config.max_tool_rounds)
        window.set_status(
            f"Settings saved — GUI policy: {config.gui_launch_policy}, tool rounds: {config.max_tool_rounds}"
        )
        activity.info(
            "settings",
            f"Updated settings: gui_launch_policy={config.gui_launch_policy}, "
            f"max_tool_rounds={config.max_tool_rounds}",
        )

    def on_edit_project_brief():
        if not engine.project_meta:
            window.chat_pane.add_message("system", "No project attached.")
            return
        from src.ui.dialogs.project_brief_dialog import ProjectBriefDialog

        meta = engine.project_meta
        dlg = ProjectBriefDialog(
            root,
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
        window.set_project_name(display)
        window.set_project_paths(source_path, config.sandbox_root)
        activity.info("project", f"Project brief updated: {display}")
        refresh_prompt_inspector(ui_state.last_user_input, announce=True)

    def on_edit_prompt_overrides():
        if not engine.project_meta:
            window.chat_pane.add_message("system", "No project attached.")
            return

        meta = engine.project_meta
        created = meta.ensure_prompt_override_scaffold()
        override_dir = meta.prompt_overrides_dir

        try:
            import os
            os.startfile(str(override_dir))  # type: ignore[attr-defined]
        except Exception:
            try:
                engine.run_cli(f'explorer "{override_dir}"')
            except Exception:
                pass

        if created:
            activity.info("prompt", f"Prompt override scaffold created at {override_dir}")
        else:
            activity.info("prompt", f"Opened prompt overrides at {override_dir}")
        refresh_prompt_inspector(ui_state.last_user_input, announce=True)

    # ── Action button handlers ────────────────────────
    def _handle_faux_click(label: str):
        if label == "Attach Self":
            # Pick a working directory to receive a copy of MindshardAGENT source
            dest_root = filedialog.askdirectory(
                title="Choose working copy destination for self-edit",
                initialdir=str(PROJECT_ROOT.parent),
            )
            if not dest_root:
                return

            from src.core.sandbox.project_loader import load_project, list_project_files
            from src.core.project.project_meta import ProjectMeta, PROFILE_SELF_EDIT
            from src.core.utils.clock import utc_iso

            window.chat_pane.add_message("system", f"Creating self-edit working copy at {dest_root}...")
            window.set_status("Loading...")

            def _do_load_self():
                target = Path(PROJECT_ROOT).name
                dest = load_project(PROJECT_ROOT, dest_root, target_name=target)
                files = list_project_files(dest_root, target_name=target)
                actual_root = str(Path(dest_root) / target)
                root.after(0, lambda: _finish_load_self(actual_root, len(files)))

            def _finish_load_self(actual_root, file_count):
                nonlocal session_store, knowledge_store
                config.sandbox_root = actual_root
                engine.set_sandbox(actual_root)

                brief_data = {
                    "display_name": Path(actual_root).name + " (self-edit)",
                    "project_purpose": "MindshardAGENT self-iteration — agent edits its own source",
                    "current_goal": "Iterate on MindshardAGENT source code",
                    "project_type": "Python app",
                    "constraints": "",
                    "profile": PROFILE_SELF_EDIT,
                    "source_path": str(PROJECT_ROOT),
                    "attached_at": utc_iso(),
                }
                engine.project_meta.update(brief_data)

                window.set_project_paths(str(PROJECT_ROOT), actual_root)
                window.set_project_name(Path(actual_root).name + " (self-edit)")
                window.set_status("Ready")
                ui_state.sandbox_root = actual_root

                new_db = Path(actual_root) / ".mindshard" / "sessions" / "sessions.db"
                session_store.close()
                session_store = SessionStore(new_db)
                knowledge_store = KnowledgeStore(session_store._conn)
                engine.set_knowledge_store(
                    knowledge_store,
                    session_id_fn=lambda: active_session["sid"],
                )
                on_session_new()

                window.chat_pane.add_message("system",
                    f"Self-edit working copy ready ({file_count} files). "
                    f"Source is YOUR MindshardAGENT code. "
                    f"Sync Back will write changes to the real source at {PROJECT_ROOT}.")
                if engine.journal:
                    engine.journal.record(aj.PROJECT_LOAD,
                        f"Self-edit: loaded {file_count} source files",
                        {"file_count": file_count, "dest": actual_root,
                         "source": str(PROJECT_ROOT)})

                sandbox_tool_names = engine.tool_catalog.sandbox_tool_names()
                window.control_pane.set_tool_count(len(sandbox_tool_names), sandbox_tool_names)
                window.control_pane.vcs_panel.refresh()
                refresh_prompt_inspector()

            threading.Thread(target=_do_load_self, daemon=True, name="load-self").start()
            return

        elif label == "Sync to Source":
            # Diff project root against source_path and apply changes
            from src.core.sandbox.project_syncer import diff_sandbox_to_source, apply_sync, log_sync

            # Determine source_path from project_meta
            sync_source = None
            if engine.project_meta:
                sync_source = engine.project_meta.source_path
            if not sync_source:
                activity.info("sync", "No source_path set — in-place project, sync unavailable")
                window.chat_pane.add_message("system",
                    "Sync Back is unavailable for in-place projects (no original source path configured).")
                return

            # For self-edit: sandbox IS the project root, sync to source_path
            diff = diff_sandbox_to_source(config.sandbox_root, sync_source, target_name="")

            if diff.get("error"):
                activity.error("sync", diff["error"])
                window.chat_pane.add_message("system", f"Sync failed: {diff['error']}")
                return

            n_add = len(diff["added"])
            n_mod = len(diff["modified"])
            n_del = len(diff["removed"])

            if n_add == 0 and n_mod == 0 and n_del == 0:
                activity.info("sync", "No changes to sync — project matches source")
                window.chat_pane.add_message("system", "No changes detected — project matches source.")
                return

            # Show diff summary and confirm
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
                activity.info("sync", "Sync cancelled by user")
                return

            result = apply_sync(config.sandbox_root, sync_source, target_name="", apply_deletes=False)
            log_sync(config.sandbox_root, result, direction="sandbox_to_source")

            total = result["total_applied"]
            errors = len(result["errors"])
            activity.info("sync",
                f"Sync complete: +{len(result['added'])} ~{len(result['modified'])} ({errors} errors)")
            window.chat_pane.add_message("system",
                f"🔄 Synced {total} file(s) back to source. "
                f"+{len(result['added'])} new, ~{len(result['modified'])} modified. "
                f"{f'{errors} error(s).' if errors else 'No errors.'}")

            if engine.journal:
                engine.journal.record(aj.PROJECT_SYNC,
                    f"Synced {total} files: +{len(result['added'])} ~{len(result['modified'])}",
                    {"added": result["added"], "modified": result["modified"],
                     "errors": result["errors"]})

            # VCS snapshot — commit the state after sync
            if engine.vcs.is_attached:
                snap_msg = (f"Post-sync snapshot: +{len(result['added'])} "
                            f"~{len(result['modified'])} files")
                try:
                    commit_hash = engine.vcs.snapshot(snap_msg)
                    if commit_hash:
                        activity.info("vcs", f"Snapshot committed: {commit_hash[:8]}")
                except Exception as vcs_err:
                    log.warning("VCS snapshot failed: %s", vcs_err)

        elif label in ("Add Ref", "Import"):
            # Add a folder to .mindshard/ref/ (bookshelf — reference docs/examples)
            from src.core.sandbox.project_loader import load_project, list_project_files
            src_dir = filedialog.askdirectory(
                title="Select folder to add to Bookshelf (.mindshard/ref/)",
            )
            if not src_dir:
                return
            folder_name = Path(src_dir).name
            ref_target = f".mindshard/ref/{folder_name}"

            def _do_add_ref():
                dest = load_project(src_dir, config.sandbox_root, target_name=ref_target)
                files = list_project_files(config.sandbox_root, target_name=ref_target)
                def _done():
                    activity.info("ref", f"Added {len(files)} files to bookshelf: .mindshard/ref/{folder_name}/")
                    window.chat_pane.add_message("system",
                        f"Added {len(files)} file(s) to bookshelf at .mindshard/ref/{folder_name}/. "
                        f"Agent can read these as reference material.")
                    if engine.journal:
                        engine.journal.record(aj.PROJECT_LOAD,
                            f"Added to bookshelf: '{folder_name}' ({len(files)} files)",
                            {"source": src_dir, "ref_folder": ref_target,
                             "file_count": len(files), "dest": str(dest)})
                root.after(0, _done)
            threading.Thread(target=_do_add_ref, daemon=True, name="add-ref").start()

        elif label == "Add Parts":
            # Add a folder to .mindshard/parts/ (parts bin — reusable code)
            from src.core.sandbox.project_loader import load_project, list_project_files
            src_dir = filedialog.askdirectory(
                title="Select folder to add to Parts Bin (.mindshard/parts/)",
            )
            if not src_dir:
                return
            folder_name = Path(src_dir).name
            parts_target = f".mindshard/parts/{folder_name}"

            def _do_add_parts():
                dest = load_project(src_dir, config.sandbox_root, target_name=parts_target)
                files = list_project_files(config.sandbox_root, target_name=parts_target)
                def _done():
                    activity.info("parts", f"Added {len(files)} files to parts bin: .mindshard/parts/{folder_name}/")
                    window.chat_pane.add_message("system",
                        f"Added {len(files)} file(s) to parts bin at .mindshard/parts/{folder_name}/. "
                        f"Agent can reuse these components.")
                    if engine.journal:
                        engine.journal.record(aj.PROJECT_LOAD,
                            f"Added to parts bin: '{folder_name}' ({len(files)} files)",
                            {"source": src_dir, "parts_folder": parts_target,
                             "file_count": len(files), "dest": str(dest)})
                root.after(0, _done)
            threading.Thread(target=_do_add_parts, daemon=True, name="add-parts").start()

        elif label == "Tools":
            tools_dir = Path(config.sandbox_root) / ".mindshard" / "tools"
            tools = list(tools_dir.glob("*.py")) if tools_dir.exists() else []
            if tools:
                names = ", ".join(t.stem for t in tools)
                activity.info("tools", f"Sandbox tools: {names}")
            else:
                activity.info("tools", "No sandbox tools found. Agent can create them in .mindshard/tools/")

        elif label == "Plan":
            # Cannibalistic Thought Chain — spiral a goal into tasks
            from tkinter import simpledialog
            goal = simpledialog.askstring(
                "Thought Chain",
                "Enter a goal to decompose into tasks:",
                parent=root,
            )
            if not goal or not goal.strip():
                return

            window.chat_pane.add_message("system",
                f"Starting thought chain for: {goal}")
            window.set_status("Planning...")

            def _on_ctc_round(round_num: int, text: str):
                root.after(0, lambda: window.chat_pane.add_message("system",
                    f"[Plan round {round_num}]\n{text}"))

            def _on_ctc_complete(result: dict):
                def _finish():
                    tasks = result.get("tasks", [])
                    if tasks:
                        task_lines = "\n".join(
                            f"  {t['number']}. {'[' + t['complexity'] + '] ' if t['complexity'] else ''}{t['text']}"
                            for t in tasks
                        )
                        window.chat_pane.add_message("system",
                            f"Task list ({len(tasks)} tasks):\n{task_lines}")
                    else:
                        window.chat_pane.add_message("system",
                            f"Plan complete (no structured tasks extracted):\n{result.get('final_text', '')}")
                    window.set_status("Ready")
                    if engine.journal:
                        engine.journal.record(aj.AGENT_TURN,
                            f"CTC plan: {len(tasks)} tasks for '{goal[:50]}'",
                            {"goal": goal, "task_count": len(tasks),
                             "tasks": [t["text"] for t in tasks[:10]]})
                root.after(0, _finish)

            def _on_ctc_error(err: str):
                root.after(0, lambda: (
                    window.chat_pane.add_message("system", f"Plan failed: {err}"),
                    window.set_status("Ready"),
                ))

            engine.run_thought_chain(
                goal=goal.strip(),
                depth=3,
                on_round=_on_ctc_round,
                on_complete=_on_ctc_complete,
                on_error=_on_ctc_error,
            )

        elif label == "Detach":
            if not config.sandbox_root:
                window.chat_pane.add_message("system", "No project attached.")
                return
            from src.ui.dialogs.detach_project_dialog import DetachProjectDialog

            project_display = engine.project_meta.display_name if engine.project_meta else Path(config.sandbox_root).name
            dlg = DetachProjectDialog(root, project_name=project_display, archive_dir=str(engine.vault.vault_dir))
            if not dlg.result or not dlg.result.get("confirmed"):
                return
            keep_sidecar = bool(dlg.result.get("keep_sidecar"))

            window.set_status("Detaching ...")
            window.chat_pane.add_message("system", f"Detaching project '{project_display}' ...")
            window.control_pane.input_pane.set_enabled(False)

            def _do_detach():
                def _prog(msg):
                    root.after(0, lambda m=msg: window.set_status(m))
                result = engine.detach_project(on_progress=_prog, keep_sidecar=keep_sidecar)
                root.after(0, lambda: _finish_detach(result))

            def _finish_detach(result):
                window.control_pane.input_pane.set_enabled(True)
                if result["success"]:
                    archive = result.get("archive_path", "")
                    retained = bool(result.get("sidecar_retained"))
                    window.set_status("Detached")
                    sidecar_msg = (
                        "The working copy still has `.mindshard/` for future reuse."
                        if retained else
                        "The working copy is clean — `.mindshard/` has been removed."
                    )
                    window.chat_pane.add_message(
                        "system",
                        f"✓ Project detached. Archive saved to:\n{archive}\n\n{sidecar_msg}",
                    )
                    window.set_project_name("")
                    window.set_project_paths("", "")
                    window.control_pane.set_prompt_inspector("", "")
                    window.control_pane.vcs_panel.refresh()
                else:
                    window.set_status("Detach failed")
                    window.chat_pane.add_message("system",
                        f"⚠ Detach failed: {result.get('error', 'Unknown error')}")

            threading.Thread(target=_do_detach, daemon=True, name="detach").start()

        elif label == "Clear":
            from tkinter import messagebox
            if messagebox.askyesno("Clear Chat", "Clear the chat transcript? (Session history is preserved.)"):
                window.chat_pane.clear()
                engine.clear_history()
                activity.info("ui", "Chat transcript cleared")

        else:
            activity.info("ui", f"Button '{label}' clicked (reserved)")

    # ── Docker callbacks ─────────────────────────────
    def _refresh_docker_status():
        """Update the Docker panel with current container state."""
        try:
            info = engine.docker_manager.get_info()
            window.control_pane.docker_panel.set_status(
                info["status"],
                docker_available=info["docker_available"],
                image_exists=info["image_exists"],
            )
            window.control_pane.docker_panel.set_enabled(config.docker_enabled)
        except Exception:
            pass

    def on_docker_toggle(enabled: bool):
        config.docker_enabled = enabled
        activity.info("docker", f"Docker mode {'enabled' if enabled else 'disabled'}")
        if config.sandbox_root:
            engine.set_sandbox(config.sandbox_root)
            refresh_prompt_inspector(ui_state.last_user_input)
        _refresh_docker_status()
        mode = "Docker container" if engine.docker_runner else "local subprocess"
        window.set_status(f"Sandbox mode: {mode}")
        if engine.journal:
            engine.journal.record(aj.DOCKER_EVENT,
                f"Docker mode {'enabled' if enabled else 'disabled'} → {mode}")

    def on_docker_build():
        activity.info("docker", "Building sandbox image...")

        def _build():
            dockerfile_dir = str(PROJECT_ROOT / "docker")
            success = engine.docker_manager.build_image(dockerfile_dir)
            root.after(0, lambda: _on_build_done(success))

        def _on_build_done(success):
            if success:
                activity.info("docker", "Image built successfully")
            else:
                activity.error("docker", "Image build failed — check Docker Desktop")
            _refresh_docker_status()

        threading.Thread(target=_build, daemon=True, name="docker-build").start()

    def on_docker_start():
        activity.info("docker", "Starting container...")

        def _start():
            # Ensure image exists
            if not engine.docker_manager.image_exists():
                root.after(0, lambda: activity.error("docker",
                    "No image — press Build first"))
                return
            success = engine.docker_manager.create_and_start(
                config.sandbox_root,
                memory_limit=config.docker_memory_limit,
                cpu_limit=config.docker_cpu_limit,
            )
            root.after(0, lambda: _on_start_done(success))

        def _on_start_done(success):
            if success:
                # If Docker mode is enabled, re-initialize to pick up the runner
                if config.docker_enabled:
                    engine.set_sandbox(config.sandbox_root)
                activity.info("docker", "Container started")
            else:
                activity.error("docker", "Container start failed")
            _refresh_docker_status()

        threading.Thread(target=_start, daemon=True, name="docker-start").start()

    def on_docker_stop():
        engine.docker_manager.stop()
        # If we were using Docker runner, re-init to fall back to local
        if engine.docker_runner:
            engine.set_sandbox(config.sandbox_root)
            refresh_prompt_inspector(ui_state.last_user_input)
        _refresh_docker_status()
        activity.info("docker", "Container stopped")

    def on_docker_destroy():
        from tkinter import messagebox
        if not messagebox.askyesno("Destroy Container",
                "This will remove the sandbox container.\n"
                "Files in the sandbox directory are NOT affected.\n\n"
                "Proceed?"):
            return
        engine.docker_manager.destroy()
        if engine.docker_runner:
            engine.set_sandbox(config.sandbox_root)
            refresh_prompt_inspector(ui_state.last_user_input)
        _refresh_docker_status()
        activity.info("docker", "Container destroyed")

    # ── Close callback ────────────────────────────────
    def on_close():
        log.info("Application closing")
        _save_current_session()
        config.save(PROJECT_ROOT)
        session_store.close()
        engine.stop()

    # ── Build window ──────────────────────────────────
    window = MainWindow(
        root, ui_state, activity,
        on_submit=on_submit,
        on_model_select=on_model_select,
        on_model_refresh=on_model_refresh,
        on_close=on_close,
        on_cli_command=on_cli_command,
        on_session_new=on_session_new,
        on_session_select=on_session_select,
        on_session_rename=on_session_rename,
        on_session_delete=on_session_delete,
        on_session_branch=on_session_branch,
        on_session_policy=on_session_policy,
        on_sandbox_pick=on_sandbox_pick,
        on_import=on_import,
        on_edit_project_brief=on_edit_project_brief,
        on_edit_prompt_overrides=on_edit_prompt_overrides,
        on_faux_click=_handle_faux_click,
        on_docker_toggle=on_docker_toggle,
        on_docker_build=on_docker_build,
        on_docker_start=on_docker_start,
        on_docker_stop=on_docker_stop,
        on_docker_destroy=on_docker_destroy,
        on_vcs_snapshot=lambda: window.control_pane.vcs_panel.refresh(),
        on_reload_tools=on_reload_tools,
        on_reload_prompt_docs=on_reload_prompt_docs,
        on_set_tool_round_limit=on_set_tool_round_limit,
        on_open_settings=on_open_settings,
        initial_tool_round_limit=config.max_tool_rounds,
    )

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
    window.set_status("Ready — refresh models to begin")
    ui_state.sandbox_root = config.sandbox_root
    refresh_prompt_inspector()

    # ── Initialize first session ──────────────────────
    # Purge empty sessions from previous launches (keep at most one)
    existing = session_store.list_sessions()
    if existing:
        session_store.purge_empty(keep_sid=existing[0]["session_id"])
        # Re-fetch after purge
        existing = session_store.list_sessions()

    if existing:
        _load_session(existing[0]["session_id"])
    else:
        on_session_new()

    # ── Auto-refresh models on startup ────────────────
    root.after(500, on_model_refresh)

    # ── Check embedding model availability ───────────
    def _check_embeddings():
        import threading
        def _worker():
            engine.check_embeddings()
        threading.Thread(target=_worker, daemon=True, name="embed-check").start()
    root.after(1500, _check_embeddings)

    # ── Resource monitor polling ──────────────────────
    def _poll_resources():
        try:
            from src.core.runtime.resource_monitor import poll_resources
            snap = poll_resources()
            window.control_pane.resources.update_stats(
                snap.cpu_percent, snap.ram_used_gb, snap.ram_total_gb,
                snap.gpu_available, snap.vram_used_gb, snap.vram_total_gb)
        except Exception:
            pass
        root.after(config.resource_poll_interval_ms, _poll_resources)

    root.after(1000, _poll_resources)

    # ── Docker status check on startup ─────────────
    def _init_docker_status():
        _refresh_docker_status()
    root.after(800, _init_docker_status)

    # ── Docker status polling (every 10s) ──────────
    def _poll_docker():
        try:
            _refresh_docker_status()
        except Exception:
            pass
        root.after(10000, _poll_docker)
    root.after(10000, _poll_docker)

    # ── Global keyboard shortcuts ────────────────────
    def _on_escape(event=None):
        """Stop streaming if active."""
        if ui_state.is_streaming:
            engine.request_stop()
            ui_state.is_streaming = False
            if _stream_flush_id["id"] is not None:
                root.after_cancel(_stream_flush_id["id"])
                _stream_flush_id["id"] = None
            window.control_pane.input_pane.set_enabled(True)
            window.set_status("Stopped")
            activity.info("ui", "Streaming stopped via Escape")
        return "break"

    def _on_ctrl_n(event=None):
        """New session."""
        on_session_new()
        return "break"

    def _on_ctrl_l(event=None):
        """Clear chat transcript."""
        window.chat_pane.clear()
        engine.clear_history()
        activity.info("ui", "Chat cleared via Ctrl+L")
        return "break"

    def _on_ctrl_tab(event=None):
        """Cycle through control pane tabs."""
        window.control_pane.cycle_workspace_tabs()
        return "break"

    def _on_ctrl_comma(event=None):
        """Open settings."""
        on_open_settings()
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
