"""App-layer model and tool-related command handlers."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING

from src.core.agent.model_roles import PRIMARY_CHAT_ROLE, resolve_model_for_role

if TYPE_CHECKING:
    from src.app_state import AppState

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


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


def on_reload_tools(s: AppState) -> None:
    if not s.config.sandbox_root:
        return
    names = s.engine.reload_discovered_tools()
    if s.ui_facade:
        s.ui_facade.set_tool_count(len(names), names)
    s.activity.info("tools", f"Tools reloaded: {len(names)} discovered tool(s) available")


def on_set_tool_round_limit(s: AppState, value: int) -> None:
    s.config.max_tool_rounds = max(1, int(value))
    s.config.save(_PROJECT_ROOT)
    if s.ui_facade:
        s.ui_facade.set_tool_round_limit(s.config.max_tool_rounds)
    s.activity.info("tools", f"Max tool rounds set to {s.config.max_tool_rounds}")
