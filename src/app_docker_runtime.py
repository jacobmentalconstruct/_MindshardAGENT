"""Shared docker runtime helpers for app-layer callbacks."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import src.core.runtime.action_journal as aj

if TYPE_CHECKING:
    from src.app_state import AppState

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_docker_probe(s: AppState) -> None:
    """Query Docker state in a background thread and apply it on the UI thread."""

    def _bg():
        try:
            info = s.engine.docker_manager.get_info()
            if not s.is_closing:
                def _apply():
                    if s.ui_facade:
                        s.ui_facade.set_docker_status(
                            info["status"],
                            docker_available=info["docker_available"],
                            image_exists=info["image_exists"],
                        )
                        s.ui_facade.set_docker_enabled(s.config.docker_enabled)

                s.root.after(0, _apply)
        except Exception:
            pass

    _start_background("docker-probe", _bg)


def rebind_sandbox_after_docker_change(s: AppState, *, refresh_prompt: bool = True) -> str:
    if s.config.sandbox_root:
        s.engine.set_sandbox(s.config.sandbox_root)
        if refresh_prompt:
            from src.app_prompt import refresh_prompt_inspector

            refresh_prompt_inspector(s, s.ui_state.last_user_input)
    return "Docker container" if s.engine.docker_runner else "local subprocess"


def record_docker_mode_change(s: AppState, enabled: bool, mode: str) -> None:
    if s.engine.journal:
        s.engine.journal.record(
            aj.DOCKER_EVENT,
            f"Docker mode {'enabled' if enabled else 'disabled'} → {mode}",
        )


def build_image_async(s: AppState) -> None:
    s.activity.info("docker", "Building sandbox image...")

    def _build():
        dockerfile_dir = str(_PROJECT_ROOT / "docker")
        success = s.engine.docker_manager.build_image(dockerfile_dir)
        s.safe_ui(lambda: _on_build_done(s, success))

    _start_background("docker-build", _build)


def start_container_async(s: AppState) -> None:
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
        s.safe_ui(lambda: _on_start_done(s, success))

    _start_background("docker-start", _start)


def _on_build_done(s: AppState, success: bool) -> None:
    if success:
        s.activity.info("docker", "Image built successfully")
    else:
        s.activity.error("docker", "Image build failed — check Docker Desktop")
    run_docker_probe(s)


def _on_start_done(s: AppState, success: bool) -> None:
    if success:
        if s.config.docker_enabled:
            rebind_sandbox_after_docker_change(s)
        s.activity.info("docker", "Container started")
    else:
        s.activity.error("docker", "Container start failed")
    run_docker_probe(s)


def _start_background(name: str, target: Callable[[], None]) -> None:
    threading.Thread(target=target, daemon=True, name=name).start()
