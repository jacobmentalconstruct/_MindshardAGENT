"""Promotion status helpers for Prompt Lab."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .storage import build_prompt_lab_storage


@dataclass(frozen=True)
class PromotionStatus:
    state: str
    message: str
    active_package_id: str = ""


def get_promotion_status(project_root: str | Path) -> PromotionStatus:
    """Return a small status view over Prompt Lab publish/activate state."""
    storage = build_prompt_lab_storage(project_root)
    try:
        active_state = storage.load_design_object("active_prompt_lab_state", "active")
    except FileNotFoundError:
        return PromotionStatus(
            state="no_active_package",
            message="No active Prompt Lab package is set yet.",
        )
    return PromotionStatus(
        state="active_package_present",
        message="Prompt Lab has an active published package.",
        active_package_id=active_state.published_package_id,
    )
