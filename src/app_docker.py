"""Docker management callbacks — extracted from app.py."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING

import src.core.runtime.action_journal as aj

if TYPE_CHECKING:
    from src.app_state import AppState


# PROJECT_ROOT needed for Dockerfile path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def do_docker_probe(s: AppState) -> None:
    """Query Docker state in a background thread; marshal result to main thread."""
    def _bg():
        try:
            info = s.engine.docker_manager.get_info()
            if not s.app_closing["value"]:
                def _apply():
                    s.window.control_pane.docker_panel.set_status(
                        info["status"],
                        docker_available=info["docker_available"],
                        image_exists=info["image_exists"],
                    )
                    s.window.control_pane.docker_panel.set_enabled(s.config.docker_enabled)
                s.root.after(0, _apply)
        except Exception:
            pass
    threading.Thread(target=_bg, daemon=True, name="docker-probe").start()


def on_docker_toggle(s: AppState, enabled: bool) -> None:
    from src.app_prompt import refresh_prompt_inspector

    s.config.docker_enabled = enabled
    s.activity.info("docker", f"Docker mode {'enabled' if enabled else 'disabled'}")
    if s.config.sandbox_root:
        s.engine.set_sandbox(s.config.sandbox_root)
        refresh_prompt_inspector(s, s.ui_state.last_user_input)
    do_docker_probe(s)
    mode = "Docker container" if s.engine.docker_runner else "local subprocess"
    s.window.set_status(f"Sandbox mode: {mode}")
    if s.engine.journal:
        s.engine.journal.record(aj.DOCKER_EVENT,
            f"Docker mode {'enabled' if enabled else 'disabled'} → {mode}")


def on_docker_build(s: AppState) -> None:
    s.activity.info("docker", "Building sandbox image...")

    def _build():
        dockerfile_dir = str(_PROJECT_ROOT / "docker")
        success = s.engine.docker_manager.build_image(dockerfile_dir)
        s.safe_ui(lambda: _on_build_done(success))

    def _on_build_done(success):
        if success:
            s.activity.info("docker", "Image built successfully")
        else:
            s.activity.error("docker", "Image build failed — check Docker Desktop")
        do_docker_probe(s)

    threading.Thread(target=_build, daemon=True, name="docker-build").start()


def on_docker_start(s: AppState) -> None:
    s.activity.info("docker", "Starting container...")

    def _start():
        if not s.engine.docker_manager.image_exists():
            s.safe_ui(lambda: s.activity.error("docker", "No image — press Build first"))
            return
        success = s.engine.docker_manager.create_and_start(
            s.config.sandbox_root,
            memory_limit=s.config.docker_memory_limit,
            cpu_limit=s.config.docker_cpu_limit,
        )
        s.safe_ui(lambda: _on_start_done(success))

    def _on_start_done(success):
        if success:
            if s.config.docker_enabled:
                s.engine.set_sandbox(s.config.sandbox_root)
            s.activity.info("docker", "Container started")
        else:
            s.activity.error("docker", "Container start failed")
        do_docker_probe(s)

    threading.Thread(target=_start, daemon=True, name="docker-start").start()


def on_docker_stop(s: AppState) -> None:
    from src.app_prompt import refresh_prompt_inspector

    s.engine.docker_manager.stop()
    if s.engine.docker_runner:
        s.engine.set_sandbox(s.config.sandbox_root)
        refresh_prompt_inspector(s, s.ui_state.last_user_input)
    do_docker_probe(s)
    s.activity.info("docker", "Container stopped")


def on_docker_destroy(s: AppState) -> None:
    from tkinter import messagebox
    from src.app_prompt import refresh_prompt_inspector

    if not messagebox.askyesno("Destroy Container",
            "This will remove the sandbox container.\n"
            "Files in the sandbox directory are NOT affected.\n\n"
            "Proceed?"):
        return
    s.engine.docker_manager.destroy()
    if s.engine.docker_runner:
        s.engine.set_sandbox(s.config.sandbox_root)
        refresh_prompt_inspector(s, s.ui_state.last_user_input)
    do_docker_probe(s)
    s.activity.info("docker", "Container destroyed")


def poll_docker(s: AppState) -> None:
    """Periodic Docker status polling."""
    if s.app_closing["value"]:
        return
    if s.config.docker_enabled:
        do_docker_probe(s)
    s.safe_after("poll_docker", 10000, lambda: poll_docker(s))
