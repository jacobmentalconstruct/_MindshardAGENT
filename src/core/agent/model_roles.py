"""Model-role resolution for multi-model orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.config.app_config import AppConfig

PRIMARY_CHAT_ROLE = "primary_chat"
PLANNER_ROLE = "planner"
RECOVERY_PLANNER_ROLE = "recovery_planner"
CODING_ROLE = "coding"
REVIEW_ROLE = "review"
FAST_PROBE_ROLE = "fast_probe"
EMBEDDING_ROLE = "embedding"

ROLE_ORDER = (
    PRIMARY_CHAT_ROLE,
    PLANNER_ROLE,
    RECOVERY_PLANNER_ROLE,
    CODING_ROLE,
    REVIEW_ROLE,
    FAST_PROBE_ROLE,
    EMBEDDING_ROLE,
)

ROLE_LABELS = {
    PRIMARY_CHAT_ROLE: "Primary Chat",
    PLANNER_ROLE: "Planner",
    RECOVERY_PLANNER_ROLE: "Recovery Planner",
    CODING_ROLE: "Coding",
    REVIEW_ROLE: "Review",
    FAST_PROBE_ROLE: "Fast Probe",
    EMBEDDING_ROLE: "Embedding",
}


def resolve_model_for_role(config: "AppConfig", role: str) -> str:
    """Return the configured model for a runtime role with sensible fallbacks."""
    config.normalize_model_roles()
    if role == PRIMARY_CHAT_ROLE:
        return config.primary_chat_model
    if role == PLANNER_ROLE:
        return config.planner_model or config.primary_chat_model
    if role == RECOVERY_PLANNER_ROLE:
        return config.recovery_planner_model or config.planner_model or config.primary_chat_model
    if role == CODING_ROLE:
        return config.coding_model or config.primary_chat_model
    if role == REVIEW_ROLE:
        return config.review_model or config.primary_chat_model
    if role == FAST_PROBE_ROLE:
        return config.fast_probe_model or config.primary_chat_model
    if role == EMBEDDING_ROLE:
        return config.embedding_model
    raise KeyError(f"Unknown model role: {role}")


def current_model_roles(config: "AppConfig") -> dict[str, str]:
    """Expose the effective role->model map for UI and diagnostics."""
    roles = {role: resolve_model_for_role(config, role) for role in ROLE_ORDER}
    if not getattr(config, "recovery_planning_enabled", True):
        roles[RECOVERY_PLANNER_ROLE] = ""
    return roles
