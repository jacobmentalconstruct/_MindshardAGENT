"""Startup bootstrap and periodic polling — extracted from app.py."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.app_state import AppState


def startup_bootstrap(s: AppState) -> None:
    """Load initial session + prompt in background, apply to UI on main thread."""
    from src.app_prompt import set_prompt_inspector
    from src.app_session import load_session, on_session_new

    def _background_work():
        try:
            s.activity.info("startup", "Refreshing prompt inspector")
            prompt_build = s.engine.preview_system_prompt(user_text="")

            s.activity.info("startup", "Loading session list")
            existing = s.session_store.list_sessions()
            if existing:
                s.session_store.purge_empty(keep_sid=existing[0]["session_id"])
                existing = s.session_store.list_sessions()
        except Exception as exc:
            s.activity.error("startup", f"Startup bootstrap (bg) failed: {exc}")
            prompt_build = None
            existing = []

        def _ui_work():
            try:
                if prompt_build:
                    set_prompt_inspector(s, prompt_build)
                if existing:
                    s.activity.info("startup", f"Restoring session {existing[0]['session_id']}")
                    load_session(s, existing[0]["session_id"])
                else:
                    s.activity.info("startup", "Creating fresh session")
                    on_session_new(s)
                s.activity.info("startup", "Deferred startup bootstrap complete")
            except Exception as exc:
                s.activity.error("startup", f"Startup bootstrap (ui) failed: {exc}")
            finally:
                s.window.control_pane.input_pane.set_enabled(True)
                s.window.set_status("Ready — refresh models to begin")

        s.root.after(0, _ui_work)

    threading.Thread(target=_background_work, daemon=True, name="startup-bootstrap").start()


def check_embeddings(s: AppState) -> None:
    def _worker():
        s.engine.check_embeddings()
    threading.Thread(target=_worker, daemon=True, name="embed-check").start()


def poll_resources(s: AppState) -> None:
    if s.app_closing["value"]:
        return

    def _bg():
        try:
            from src.core.runtime.resource_monitor import poll_resources as _poll
            snap = _poll()
            if not s.app_closing["value"]:
                s.root.after(0, lambda: s.window.control_pane.resources.update_stats(
                    snap.cpu_percent, snap.ram_used_gb, snap.ram_total_gb,
                    snap.gpu_available, snap.vram_used_gb, snap.vram_total_gb))
        except Exception:
            pass

    threading.Thread(target=_bg, daemon=True, name="poll-resources").start()
    s.safe_after("poll_resources", s.config.resource_poll_interval_ms, lambda: poll_resources(s))


def schedule_startup_timers(s: AppState) -> None:
    """Register all startup and polling timers. Called once from main()."""
    from src.app_commands import on_model_refresh
    from src.app_docker import do_docker_probe, poll_docker

    s.safe_after("startup_bootstrap", 50, lambda: startup_bootstrap(s))
    s.safe_after("model_refresh", 1200, lambda: on_model_refresh(s))
    s.safe_after("check_embeddings", 1500, lambda: check_embeddings(s))
    s.safe_after("poll_resources", 1000, lambda: poll_resources(s))

    if s.config.docker_enabled:
        s.safe_after("init_docker_status", 800, lambda: do_docker_probe(s))
    s.safe_after("poll_docker", 10000, lambda: poll_docker(s))
