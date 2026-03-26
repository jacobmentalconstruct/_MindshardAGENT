"""Prompt profile persistence service."""

from __future__ import annotations

from .operation_log import PromptLabOperationLog
from .contracts import PromptProfile
from .storage import PromptLabStorage


class ProfileService:
    def __init__(self, storage: PromptLabStorage, *, operation_log: PromptLabOperationLog | None = None):
        self.storage = storage
        self._operation_log = operation_log

    def list_profiles(self) -> list[dict[str, str]]:
        items = self.storage.list_design_objects("prompt_profile")
        if self._operation_log is not None:
            self._operation_log.record(
                channel="service",
                action="list_profiles",
                status="ok",
                details={"count": len(items)},
            )
        return items

    def get_profile(self, profile_id: str) -> PromptProfile:
        profile = self.storage.load_design_object("prompt_profile", profile_id)
        if self._operation_log is not None:
            self._operation_log.record(
                channel="service",
                action="get_profile",
                status="ok",
                details={"profile_id": profile_id},
            )
        return profile

    def save_profile(self, profile: PromptProfile) -> PromptProfile:
        saved = self.storage.save_prompt_profile(profile)
        if self._operation_log is not None:
            self._operation_log.record(
                channel="service",
                action="save_profile",
                status="ok",
                details={"profile_id": saved.id},
            )
        return saved
