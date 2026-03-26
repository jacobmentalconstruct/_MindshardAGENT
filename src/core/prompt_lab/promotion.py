"""Publish/apply stubs for Prompt Lab."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromotionStatus:
    state: str
    message: str


def get_promotion_status() -> PromotionStatus:
    """Return the current scaffold-only promotion status."""
    return PromotionStatus(
        state="scaffold_only",
        message="Prompt Lab publish/apply flow is not implemented yet.",
    )
