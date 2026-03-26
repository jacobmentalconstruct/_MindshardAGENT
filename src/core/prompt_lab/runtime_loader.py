"""Runtime-facing Prompt Lab loader.

Consumes only explicit active published state.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .contracts import ActivePromptLabState, BindingRecord, ExecutionPlan, PromptProfile, PublishedPromptLabPackage
from .storage import PromptLabStorage, build_prompt_lab_storage


@dataclass(frozen=True)
class PromptLabRuntimeBundle:
    active_state: ActivePromptLabState
    package: PublishedPromptLabPackage
    execution_plan: ExecutionPlan
    prompt_profiles: list[PromptProfile]
    bindings: list[BindingRecord]


def load_active_prompt_lab_runtime(
    project_root: str | Path | PromptLabStorage,
) -> PromptLabRuntimeBundle | None:
    storage = (
        project_root
        if isinstance(project_root, PromptLabStorage)
        else build_prompt_lab_storage(project_root)
    )
    try:
        active_state = storage.load_design_object("active_prompt_lab_state", "active")
    except FileNotFoundError:
        return None
    if not active_state.published_package_id:
        return None
    package = storage.load_design_object(
        "published_prompt_lab_package",
        active_state.published_package_id,
    )
    execution_plan = storage.load_design_object("execution_plan", package.execution_plan_id)
    prompt_profiles = [
        storage.load_design_object("prompt_profile", profile_id)
        for profile_id in package.prompt_profile_ids
    ]
    bindings = [
        storage.load_design_object("binding_record", binding_id)
        for binding_id in package.binding_ids
    ]
    return PromptLabRuntimeBundle(
        active_state=active_state,
        package=package,
        execution_plan=execution_plan,
        prompt_profiles=prompt_profiles,
        bindings=bindings,
    )


def describe_active_prompt_lab_runtime(
    project_root: str | Path | PromptLabStorage,
) -> str:
    bundle = load_active_prompt_lab_runtime(project_root)
    if bundle is None:
        return "No active Prompt Lab package.\nOnly explicit active published state is runtime-consumable."
    package = bundle.package
    return (
        f"Active package: {package.package_name or package.id}\n"
        f"Package id: {package.id}\n"
        f"Plan: {bundle.execution_plan.name or bundle.execution_plan.id}\n"
        f"Profiles: {len(bundle.prompt_profiles)}\n"
        f"Bindings: {len(bundle.bindings)}\n"
        f"Validation: {package.validation_status} ({package.validation_snapshot_id or 'n/a'})\n"
        f"Package fp: {package.package_fingerprint[:12] if package.package_fingerprint else 'n/a'}"
    )
