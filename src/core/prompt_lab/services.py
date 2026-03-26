"""Prompt Lab service registry for Phase 1C."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .binding_service import BindingService
from .execution_plan_service import ExecutionPlanService
from .operation_log import PromptLabOperationLog
from .package_service import PackageService
from .profile_service import ProfileService
from .source_service import SourceService
from .storage import PromptLabStorage, build_prompt_lab_storage
from .validation import validate_active_state, validate_package_selection, validate_prompt_lab_state


@dataclass
class PromptLabServiceBundle:
    """Service-first Prompt Lab registry."""

    storage: PromptLabStorage
    operation_log: PromptLabOperationLog
    source_service: SourceService
    profile_service: ProfileService
    execution_plan_service: ExecutionPlanService
    binding_service: BindingService
    package_service: PackageService
    validate_state: Callable[[str | Path | PromptLabStorage], Any]
    validate_package_selection: Callable[..., list[dict[str, Any]]]
    validate_active_state: Callable[..., list[dict[str, Any]]]
    metadata: dict[str, Any] = field(default_factory=dict)


def build_prompt_lab_services(project_root: str | Path) -> PromptLabServiceBundle:
    root = Path(project_root).resolve()
    storage = build_prompt_lab_storage(root)
    operation_log = PromptLabOperationLog(storage.paths.operations_log_path)
    return PromptLabServiceBundle(
        storage=storage,
        operation_log=operation_log,
        source_service=SourceService(root, operation_log=operation_log),
        profile_service=ProfileService(storage, operation_log=operation_log),
        execution_plan_service=ExecutionPlanService(storage, operation_log=operation_log),
        binding_service=BindingService(storage, operation_log=operation_log),
        package_service=PackageService(storage, operation_log=operation_log),
        validate_state=validate_prompt_lab_state,
        validate_package_selection=validate_package_selection,
        validate_active_state=validate_active_state,
        metadata={
            "status": "phase_2",
            "persistence": {
                "design_objects": "json_canonical",
                "history": "sqlite_canonical",
            },
            "cli_mode": "inspection_admin_safe",
            "workbench_mode": "minimal_dedicated",
            "main_app_bridge": "inspect_reload_open_status_only",
            "runtime_rule": "main_app_consumes_active_published_only",
            "architecture_style": "service_first_manager_optional",
            "monitoring": {
                "operation_log": str(storage.paths.operations_log_path),
            },
            "package_contract": {
                "published_state": "json_canonical",
                "active_state": "json_canonical",
                "activation_requires_published_package": True,
            },
        },
    )
