"""
FILE: settings_command_handler.py
ROLE: Settings dialog result → config + runtime sync.
WHAT IT OWNS:
  - apply_settings: consume the SettingsDialog result dict, write all config
    fields, persist to disk, and push the new state to engine/UI.

The dialog itself stays in app_commands.py (UI I/O belongs in the shim).
This handler owns "what does a settings save mean for the running system."

Domains: config + agent (2 — valid manager)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.core.agent.model_roles import (
    PRIMARY_CHAT_ROLE,
    PLANNER_ROLE,
    RECOVERY_PLANNER_ROLE,
    CODING_ROLE,
    REVIEW_ROLE,
    FAST_PROBE_ROLE,
    EMBEDDING_ROLE,
)

if TYPE_CHECKING:
    from src.app_state import AppState


def apply_settings(s: "AppState", result: dict[str, Any], project_root: Path) -> None:
    """Apply a SettingsDialog result to config, engine, and UI.

    Three internal stages:
      1. _apply_config_fields  — write result values into s.config
      2. _sync_settings_to_runtime — push new config to engine + UI
      3. _announce_settings_change — log status + activity messages
    """
    toolbox_root_changed = _apply_config_fields(s, result, project_root)
    _sync_settings_to_runtime(s, toolbox_root_changed)
    _announce_settings_change(s, toolbox_root_changed)


# ── Stage 1: config field mutations ───────────────────────────────────────────

def _apply_config_fields(s: "AppState", result: dict[str, Any],
                         project_root: Path) -> bool:
    """Write dialog result into s.config. Returns True if toolbox_root changed."""
    role_updates = result.get("model_roles", {})

    s.config.primary_chat_model = _str(
        role_updates.get(PRIMARY_CHAT_ROLE, s.config.primary_chat_model))
    s.config.selected_model = s.config.primary_chat_model
    s.config.planner_model = _str(
        role_updates.get(PLANNER_ROLE, s.config.planner_model))
    s.config.recovery_planner_model = _str(
        role_updates.get(RECOVERY_PLANNER_ROLE, s.config.recovery_planner_model))
    s.config.coding_model = _str(
        role_updates.get(CODING_ROLE, s.config.coding_model))
    s.config.review_model = _str(
        role_updates.get(REVIEW_ROLE, s.config.review_model))
    s.config.fast_probe_model = _str(
        role_updates.get(FAST_PROBE_ROLE, s.config.fast_probe_model))
    s.config.embedding_model = _str(
        role_updates.get(EMBEDDING_ROLE, s.config.embedding_model))

    s.config.max_tool_rounds = max(
        1, int(result.get("max_tool_rounds", s.config.max_tool_rounds)))
    s.config.gui_launch_policy = _str(
        result.get("gui_launch_policy", s.config.gui_launch_policy)) or "ask"
    s.config.planning_enabled = bool(
        result.get("planning_enabled", s.config.planning_enabled))
    s.config.recovery_planning_enabled = bool(
        result.get("recovery_planning_enabled", s.config.recovery_planning_enabled))
    s.config.probe_models = result.get("probe_models", s.config.probe_models)

    new_toolbox_root = _str(result.get("toolbox_root", s.config.toolbox_root))
    toolbox_changed = new_toolbox_root != (_str(s.config.toolbox_root))
    if toolbox_changed:
        s.config.toolbox_root = new_toolbox_root

    s.config.normalize_model_roles()
    s.config.save(project_root)
    return toolbox_changed


# ── Stage 2: push new config to engine + UI ───────────────────────────────────

def _sync_settings_to_runtime(s: "AppState", toolbox_root_changed: bool) -> None:
    """After config is written, sync engine tokenizer and UI widgets."""
    model = s.config.primary_chat_model
    s.ui_state.selected_model = model
    s.engine.tokenizer.set_model(model)
    s.window.set_model(model)
    if s.ui_facade:
        s.ui_facade.set_models(s.ui_state.available_models, model)
        s.ui_facade.set_tool_round_limit(s.config.max_tool_rounds)
    if toolbox_root_changed:
        names = s.engine.reload_discovered_tools()
        if s.ui_facade:
            s.ui_facade.set_tool_count(len(names), names)


# ── Stage 3: status + activity log ────────────────────────────────────────────

def _announce_settings_change(s: "AppState", toolbox_root_changed: bool) -> None:
    """Emit status bar update and activity log lines for the saved settings."""
    from src.app_session import log_model_roles

    primary = s.config.primary_chat_model or "(none)"
    planner = s.config.planner_model or "(none)"
    s.window.set_status(
        f"Settings saved — primary={primary}, "
        f"planner={planner}, tool rounds: {s.config.max_tool_rounds}"
    )
    s.activity.info(
        "settings",
        f"Updated settings: primary={primary}, "
        f"planner={planner}, "
        f"recovery_planner={s.config.recovery_planner_model or '(none)'}, "
        f"gui_launch_policy={s.config.gui_launch_policy}, "
        f"planning_enabled={s.config.planning_enabled}, "
        f"recovery_planning_enabled={s.config.recovery_planning_enabled}, "
        f"max_tool_rounds={s.config.max_tool_rounds}",
    )
    if toolbox_root_changed:
        if s.config.toolbox_root:
            s.activity.info("settings", f"Toolbox root updated: {s.config.toolbox_root}")
        else:
            s.activity.info("settings", "Toolbox root cleared")

    log_model_roles(s)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _str(value: Any) -> str:
    """Coerce a possibly-None value to a stripped string."""
    return str(value or "").strip()
