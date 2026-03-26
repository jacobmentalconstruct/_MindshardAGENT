"""Docker management callbacks — extracted from app.py."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.app_docker_runtime import (
    build_image_async,
    record_docker_mode_change,
    rebind_sandbox_after_docker_change,
    run_docker_probe,
    start_container_async,
)

if TYPE_CHECKING:
    from src.app_state import AppState


def do_docker_probe(s: AppState) -> None:
    run_docker_probe(s)


def on_docker_toggle(s: AppState, enabled: bool) -> None:
    s.config.docker_enabled = enabled
    s.activity.info("docker", f"Docker mode {'enabled' if enabled else 'disabled'}")
    mode = rebind_sandbox_after_docker_change(s)
    do_docker_probe(s)
    s.window.set_status(f"Sandbox mode: {mode}")
    record_docker_mode_change(s, enabled, mode)


def on_docker_build(s: AppState) -> None:
    build_image_async(s)


def on_docker_start(s: AppState) -> None:
    start_container_async(s)


def on_docker_stop(s: AppState) -> None:
    s.engine.docker_manager.stop()
    if s.engine.docker_runner:
        rebind_sandbox_after_docker_change(s)
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
        rebind_sandbox_after_docker_change(s)
    do_docker_probe(s)
    s.activity.info("docker", "Container destroyed")


def poll_docker(s: AppState) -> None:
    """Periodic Docker status polling."""
    if s.is_closing:
        return
    if s.config.docker_enabled:
        do_docker_probe(s)
    s.safe_after("poll_docker", 10000, lambda: poll_docker(s))
