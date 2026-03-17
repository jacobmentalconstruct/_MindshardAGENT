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
    engine = Engine(config=config, activity=activity, bus=bus,
                    on_confirm_destructive=_confirm_destructive)

    # ── Default sandbox ───────────────────────────────
    default_sandbox = PROJECT_ROOT / "_sandbox"
    if not config.sandbox_root:
        config.sandbox_root = str(default_sandbox)
    engine.set_sandbox(config.sandbox_root)

    # ── Session store ─────────────────────────────────
    sessions_db = Path(config.sandbox_root) / "_sessions" / "sessions.db"
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

    # ── Chat submit callback ──────────────────────────
    def on_submit(text: str):
        activity.info("user", f"Prompt submitted ({len(text)} chars)")
        ui_state.last_user_input = text
        window.chat_pane.add_message("user", text)
        window.control_pane.prompt_preview.set_text(text)
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
        window.chat_pane.add_message("assistant", "...")
        _stream_card = window.chat_pane._inner.winfo_children()[-1]

        def _on_token(token: str):
            _streaming_content.append(token)
            try:
                root.after(0, _update_stream, _stream_card)
            except Exception:
                pass

        def _update_stream(card):
            try:
                content = "".join(_streaming_content)
                card.update_streaming_content(content)
                # Force canvas to recalculate layout after card resize
                window.chat_pane._inner.update_idletasks()
                window.chat_pane._canvas.configure(
                    scrollregion=window.chat_pane._canvas.bbox("all"))
                window.chat_pane._canvas.yview_moveto(1.0)
            except Exception:
                pass

        def _on_complete(result: dict):
            ui_state.is_streaming = False
            meta = result.get("metadata", {})
            root.after(0, _finish_stream, _stream_card, meta, result)

        def _finish_stream(card, meta, result):
            try:
                _update_stream(card)
                window.set_status("Ready")
                window.control_pane.input_pane.set_enabled(True)
                activity.info("chat",
                    f"Response: {meta.get('tokens_out', '?')} tokens, {meta.get('time', '?')}")

                # Update response preview in Watch tab
                content = result.get("content", "".join(_streaming_content))
                window.control_pane.response_preview.set_text(content)

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
            title="Select Sandbox Root Directory",
            initialdir=config.sandbox_root,
        )
        if not new_root:
            return
        config.sandbox_root = new_root
        engine.set_sandbox(new_root)
        window.set_sandbox_path(new_root)
        ui_state.sandbox_root = new_root

        # Re-initialize session store and knowledge store for new sandbox
        nonlocal session_store, knowledge_store
        new_db = Path(new_root) / "_sessions" / "sessions.db"
        session_store.close()
        session_store = SessionStore(new_db)
        knowledge_store = KnowledgeStore(session_store._conn)
        engine.set_knowledge_store(
            knowledge_store,
            session_id_fn=lambda: active_session["sid"],
        )

        # Create initial session in new sandbox
        on_session_new()
        activity.info("sandbox", f"Sandbox changed to: {new_root}")

    # ── Action button handlers ────────────────────────
    def _handle_faux_click(label: str):
        if label == "Load Self":
            # Load project source into sandbox for agent self-iteration
            from src.core.sandbox.project_loader import load_project, list_project_files, snapshot_manifest
            dest = load_project(PROJECT_ROOT, config.sandbox_root)
            files = list_project_files(config.sandbox_root)
            activity.info("project", f"Project loaded: {len(files)} files -> sandbox/project/")
            window.chat_pane.add_message("system",
                f"📂 Project source loaded into sandbox/project/ ({len(files)} files). "
                f"This is YOUR source code — the MindshardAGENT application. "
                f"You can read and modify files here. Changes stay in sandbox until the user syncs back.")
            # Journal it
            if engine.journal:
                engine.journal.record(aj.PROJECT_LOAD,
                    f"Loaded {len(files)} source files into sandbox/project/",
                    {"file_count": len(files), "dest": str(dest)})

        elif label == "Sync Back":
            # Diff sandbox/project/ against real source and apply changes
            from src.core.sandbox.project_syncer import diff_sandbox_to_source, apply_sync, log_sync
            diff = diff_sandbox_to_source(config.sandbox_root, PROJECT_ROOT)

            if diff.get("error"):
                activity.error("sync", diff["error"])
                window.chat_pane.add_message("system", f"⚠ Sync failed: {diff['error']}")
                return

            n_add = len(diff["added"])
            n_mod = len(diff["modified"])
            n_del = len(diff["removed"])

            if n_add == 0 and n_mod == 0 and n_del == 0:
                activity.info("sync", "No changes to sync — sandbox matches source")
                window.chat_pane.add_message("system", "✓ No changes detected — sandbox matches source.")
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
                f"Apply sandbox changes to real source?\n\n{summary_text}\n\n"
                f"Deletions will NOT be applied (safety).\n"
                f"This overwrites real source files.")
            if not proceed:
                activity.info("sync", "Sync cancelled by user")
                return

            result = apply_sync(config.sandbox_root, PROJECT_ROOT, apply_deletes=False)
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

        elif label == "Tools":
            tools_dir = Path(config.sandbox_root) / "_tools"
            tools = list(tools_dir.glob("*.py")) if tools_dir.exists() else []
            if tools:
                names = ", ".join(t.stem for t in tools)
                activity.info("tools", f"Sandbox tools: {names}")
            else:
                activity.info("tools", "No sandbox tools found. Agent can create them.")

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
        on_sandbox_pick=on_sandbox_pick,
        on_faux_click=_handle_faux_click,
        on_docker_toggle=on_docker_toggle,
        on_docker_build=on_docker_build,
        on_docker_start=on_docker_start,
        on_docker_stop=on_docker_stop,
        on_docker_destroy=on_docker_destroy,
    )

    # ── Apply window geometry ─────────────────────────
    root.geometry(f"{config.window_width}x{config.window_height}")

    # ── Start engine ──────────────────────────────────
    engine.start()
    activity.info("app", "MindshardAGENT ready")
    activity.info("app", f"Sandbox: {config.sandbox_root}")
    window.set_status("Ready — refresh models to begin")
    window.set_sandbox_path(config.sandbox_root)
    ui_state.sandbox_root = config.sandbox_root

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

    # ── Main loop ─────────────────────────────────────
    log.info("Entering main loop")
    root.mainloop()
    log.info("=== MindshardAGENT shutdown complete ===")


if __name__ == "__main__":
    main()
