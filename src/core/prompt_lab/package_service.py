"""Published/active package contract for Prompt Lab."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.core.utils.clock import utc_iso

from .operation_log import PromptLabOperationLog
from .contracts import (
    ActivePromptLabState,
    PromotionRecord,
    PublishedPromptLabPackage,
)
from .storage import PromptLabStorage
from .validation import (
    validate_active_state,
    validate_package_selection,
    validate_prompt_lab_state,
)


@dataclass(frozen=True)
class PackagePublishResult:
    package: PublishedPromptLabPackage
    validation_snapshot_id: str
    promotion_record_id: str


class PackageService:
    """Admin-safe publish/activate operations for Prompt Lab."""

    def __init__(self, storage: PromptLabStorage, *, operation_log: PromptLabOperationLog | None = None):
        self.storage = storage
        self._operation_log = operation_log

    @staticmethod
    def _record_suffix() -> str:
        return (
            utc_iso()
            .replace(":", "")
            .replace("-", "")
            .replace("+", "_plus_")
            .replace(".", "")
        )

    def list_published_packages(self) -> list[dict[str, str]]:
        items = self.storage.list_design_objects("published_prompt_lab_package")
        if self._operation_log is not None:
            self._operation_log.record(
                channel="service",
                action="list_published_packages",
                status="ok",
                details={"count": len(items)},
            )
        return items

    def get_published_package(self, package_id: str) -> PublishedPromptLabPackage:
        package = self.storage.load_design_object("published_prompt_lab_package", package_id)
        if self._operation_log is not None:
            self._operation_log.record(
                channel="service",
                action="get_published_package",
                status="ok",
                details={"package_id": package_id},
            )
        return package

    def get_active_state(self) -> ActivePromptLabState | None:
        try:
            active_state = self.storage.load_design_object("active_prompt_lab_state", "active")
            if self._operation_log is not None:
                self._operation_log.record(
                    channel="service",
                    action="get_active_state",
                    status="ok",
                    details={"package_id": active_state.published_package_id},
                )
            return active_state
        except FileNotFoundError:
            if self._operation_log is not None:
                self._operation_log.record(
                    channel="service",
                    action="get_active_state",
                    status="empty",
                    details={},
                )
            return None

    def publish_package(
        self,
        *,
        package_id: str,
        package_name: str,
        execution_plan_id: str,
        prompt_profile_ids: list[str],
        binding_ids: list[str],
        published_by: str = "unknown",
        notes: str = "",
    ) -> PackagePublishResult:
        validation_snapshot = validate_prompt_lab_state(self.storage)
        self.storage.save_validation_snapshot(validation_snapshot)
        if validation_snapshot.status != "valid":
            raise ValueError(
                "Prompt Lab state is not publishable until structural validation passes."
            )

        findings = validate_package_selection(
            self.storage,
            execution_plan_id=execution_plan_id,
            prompt_profile_ids=prompt_profile_ids,
            binding_ids=binding_ids,
        )
        if findings:
            raise ValueError(
                "Selected package contents are not publishable: "
                + "; ".join(finding["message"] for finding in findings)
            )

        package = self.storage.save_published_package(
            PublishedPromptLabPackage(
                id=package_id,
                package_name=package_name,
                prompt_profile_ids=sorted(prompt_profile_ids),
                execution_plan_id=execution_plan_id,
                binding_ids=sorted(binding_ids),
                validation_snapshot_id=validation_snapshot.id,
                validation_status=validation_snapshot.status,
                source_fingerprint=validation_snapshot.source_fingerprint,
                prompt_fingerprint=validation_snapshot.prompt_fingerprint,
                execution_plan_fingerprint=validation_snapshot.execution_plan_fingerprint,
                binding_fingerprint=validation_snapshot.binding_fingerprint,
                published_by=published_by,
                notes=notes,
            )
        )
        promotion_record = self.storage.save_promotion_record(
            PromotionRecord(
                id=f"promotion-{package.id}-{self._record_suffix()}",
                target_project=str(self.storage.project_root),
                promoted_profiles=package.prompt_profile_ids,
                promoted_execution_plan_id=package.execution_plan_id,
                promoted_binding_ids=package.binding_ids,
                validation_snapshot_id=package.validation_snapshot_id,
                source_fingerprint=package.source_fingerprint,
                prompt_fingerprint=package.prompt_fingerprint,
                execution_plan_fingerprint=package.execution_plan_fingerprint,
                promoted_by=published_by,
                active=False,
            )
        )
        if self._operation_log is not None:
            self._operation_log.record(
                channel="service",
                action="publish_package",
                status="ok",
                details={
                    "package_id": package.id,
                    "execution_plan_id": package.execution_plan_id,
                    "profile_count": len(package.prompt_profile_ids),
                    "binding_count": len(package.binding_ids),
                },
            )
        return PackagePublishResult(
            package=package,
            validation_snapshot_id=validation_snapshot.id,
            promotion_record_id=promotion_record.id,
        )

    def activate_package(
        self,
        package_id: str,
        *,
        activated_by: str = "unknown",
        notes: str = "",
    ) -> ActivePromptLabState:
        package = self.get_published_package(package_id)
        active_state = self.storage.save_active_state(
            ActivePromptLabState(
                id="active",
                published_package_id=package.id,
                package_fingerprint=package.package_fingerprint,
                validation_snapshot_id=package.validation_snapshot_id,
                activated_by=activated_by,
                notes=notes,
            )
        )
        findings = validate_active_state(self.storage, active_state)
        if findings:
            raise ValueError(
                "Active Prompt Lab state failed validation: "
                + "; ".join(finding["message"] for finding in findings)
            )
        self.storage.save_promotion_record(
            PromotionRecord(
                id=f"promotion-{package.id}-active-{self._record_suffix()}",
                target_project=str(self.storage.project_root),
                promoted_profiles=package.prompt_profile_ids,
                promoted_execution_plan_id=package.execution_plan_id,
                promoted_binding_ids=package.binding_ids,
                validation_snapshot_id=package.validation_snapshot_id,
                source_fingerprint=package.source_fingerprint,
                prompt_fingerprint=package.prompt_fingerprint,
                execution_plan_fingerprint=package.execution_plan_fingerprint,
                promoted_by=activated_by,
                active=True,
            )
        )
        if self._operation_log is not None:
            self._operation_log.record(
                channel="service",
                action="activate_package",
                status="ok",
                details={
                    "package_id": package.id,
                    "package_fingerprint": package.package_fingerprint,
                },
            )
        return active_state

    def resolve_active_package(self) -> PublishedPromptLabPackage | None:
        active_state = self.get_active_state()
        if active_state is None or not active_state.published_package_id:
            return None
        package = self.get_published_package(active_state.published_package_id)
        if self._operation_log is not None:
            self._operation_log.record(
                channel="service",
                action="resolve_active_package",
                status="ok",
                details={"package_id": package.id},
            )
        return package
