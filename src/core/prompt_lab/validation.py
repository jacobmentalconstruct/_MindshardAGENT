"""Validation rules for Prompt Lab Phase 1A."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.core.utils.clock import utc_iso

from .contracts import (
    ActivePromptLabState,
    PublishedPromptLabPackage,
    ValidationSnapshot,
    compute_fingerprint,
)
from .storage import PromptLabStorage, build_prompt_lab_storage


def _finding(code: str, message: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "severity": "error",
        "code": code,
        "message": message,
        "context": context or {},
    }


def validate_prompt_lab_state(project_root: str | Path | PromptLabStorage) -> ValidationSnapshot:
    storage = (
        project_root
        if isinstance(project_root, PromptLabStorage)
        else build_prompt_lab_storage(project_root)
    )

    profiles = [storage.load_design_object("prompt_profile", item["id"]) for item in storage.list_design_objects("prompt_profile")]
    plans = [storage.load_design_object("execution_plan", item["id"]) for item in storage.list_design_objects("execution_plan")]
    bindings = [storage.load_design_object("binding_record", item["id"]) for item in storage.list_design_objects("binding_record")]

    findings: list[dict[str, Any]] = []

    profile_ids = set()
    for profile in profiles:
        if not profile.id.strip():
            findings.append(_finding("profile.missing_id", "Prompt profile is missing an id."))
        if profile.id in profile_ids:
            findings.append(_finding("profile.duplicate_id", f"Duplicate prompt profile id '{profile.id}'."))
        profile_ids.add(profile.id)
        if not profile.name.strip():
            findings.append(_finding("profile.missing_name", f"Prompt profile '{profile.id}' is missing a name."))
        if not profile.role_target.strip():
            findings.append(_finding("profile.missing_role_target", f"Prompt profile '{profile.id}' is missing a role target."))
        for ref in profile.source_refs:
            if not str(ref).strip():
                findings.append(_finding("profile.blank_source_ref", f"Prompt profile '{profile.id}' contains a blank source ref."))

    plan_ids = set()
    plan_nodes: dict[tuple[str, str], Any] = {}
    for plan in plans:
        if not plan.id.strip():
            findings.append(_finding("plan.missing_id", "Execution plan is missing an id."))
        if plan.id in plan_ids:
            findings.append(_finding("plan.duplicate_id", f"Duplicate execution plan id '{plan.id}'."))
        plan_ids.add(plan.id)
        if not plan.name.strip():
            findings.append(_finding("plan.missing_name", f"Execution plan '{plan.id}' is missing a name."))

        seen_node_ids: set[str] = set()
        seen_order_indexes: set[int] = set()
        for node in plan.nodes:
            if not node.id.strip():
                findings.append(_finding("node.missing_id", f"Execution plan '{plan.id}' contains a node with no id."))
            if node.id in seen_node_ids:
                findings.append(_finding("node.duplicate_id", f"Execution plan '{plan.id}' contains duplicate node id '{node.id}'."))
            seen_node_ids.add(node.id)
            if node.order_index in seen_order_indexes:
                findings.append(
                    _finding(
                        "node.duplicate_order",
                        f"Execution plan '{plan.id}' contains duplicate order index '{node.order_index}'.",
                        {"plan_id": plan.id, "node_id": node.id},
                    )
                )
            seen_order_indexes.add(node.order_index)
            if not node.label.strip():
                findings.append(_finding("node.missing_label", f"Execution node '{node.id}' in plan '{plan.id}' is missing a label."))
            if not node.loop_type.strip():
                findings.append(_finding("node.missing_loop_type", f"Execution node '{node.id}' in plan '{plan.id}' is missing a loop type."))
            plan_nodes[(plan.id, node.id)] = node

    binding_ids = set()
    enabled_node_keys = {
        (plan.id, node.id)
        for plan in plans
        for node in plan.nodes
        if node.enabled
    }
    bound_enabled_node_keys: set[tuple[str, str]] = set()
    bindings_by_node: set[tuple[str, str]] = set()

    for binding in bindings:
        if not binding.id.strip():
            findings.append(_finding("binding.missing_id", "Binding record is missing an id."))
        if binding.id in binding_ids:
            findings.append(_finding("binding.duplicate_id", f"Duplicate binding id '{binding.id}'."))
        binding_ids.add(binding.id)
        if binding.execution_plan_id not in plan_ids:
            findings.append(
                _finding(
                    "binding.unknown_plan",
                    f"Binding '{binding.id}' references unknown execution plan '{binding.execution_plan_id}'.",
                )
            )
        if binding.prompt_profile_id not in profile_ids:
            findings.append(
                _finding(
                    "binding.unknown_profile",
                    f"Binding '{binding.id}' references unknown prompt profile '{binding.prompt_profile_id}'.",
                )
            )
        if binding.fallback_profile_id and binding.fallback_profile_id not in profile_ids:
            findings.append(
                _finding(
                    "binding.unknown_fallback_profile",
                    f"Binding '{binding.id}' references unknown fallback prompt profile '{binding.fallback_profile_id}'.",
                )
            )
        node_key = (binding.execution_plan_id, binding.node_id)
        if node_key in bindings_by_node:
            findings.append(
                _finding(
                    "binding.duplicate_node_binding",
                    f"Multiple bindings target node '{binding.node_id}' in plan '{binding.execution_plan_id}'.",
                    {"plan_id": binding.execution_plan_id, "node_id": binding.node_id},
                )
            )
        bindings_by_node.add(node_key)
        if node_key not in plan_nodes:
            findings.append(
                _finding(
                    "binding.unknown_node",
                    f"Binding '{binding.id}' references unknown node '{binding.node_id}' in plan '{binding.execution_plan_id}'.",
                )
            )
        else:
            bound_enabled_node_keys.add(node_key)

    for plan_id, node_id in sorted(enabled_node_keys - bound_enabled_node_keys):
        findings.append(
            _finding(
                "binding.missing_enabled_node_binding",
                f"Enabled node '{node_id}' in execution plan '{plan_id}' has no binding record.",
                {"plan_id": plan_id, "node_id": node_id},
            )
        )

    source_fingerprint = compute_fingerprint([profile.source_refs for profile in profiles])
    prompt_fingerprint = compute_fingerprint([getattr(profile, "version_fingerprint", "") for profile in profiles])
    execution_plan_fingerprint = compute_fingerprint(
        [
            {
                "id": plan.id,
                "version_fingerprint": plan.version_fingerprint,
                "nodes": [asdict(node) for node in plan.nodes],
            }
            for plan in plans
        ]
    )
    binding_fingerprint = compute_fingerprint(
        [
            {
                "id": binding.id,
                "binding_fingerprint": binding.binding_fingerprint,
                "execution_plan_id": binding.execution_plan_id,
                "node_id": binding.node_id,
                "prompt_profile_id": binding.prompt_profile_id,
                "fallback_profile_id": binding.fallback_profile_id,
            }
            for binding in bindings
        ]
    )
    snapshot_basis = {
        "findings": findings,
        "source_fingerprint": source_fingerprint,
        "prompt_fingerprint": prompt_fingerprint,
        "execution_plan_fingerprint": execution_plan_fingerprint,
        "binding_fingerprint": binding_fingerprint,
    }
    snapshot_id = f"validation-{compute_fingerprint(snapshot_basis)[:12]}"
    return ValidationSnapshot(
        id=snapshot_id,
        status="valid" if not findings else "invalid",
        findings=findings,
        source_fingerprint=source_fingerprint,
        prompt_fingerprint=prompt_fingerprint,
        execution_plan_fingerprint=execution_plan_fingerprint,
        binding_fingerprint=binding_fingerprint,
        created_at=utc_iso(),
    )


def validate_package_selection(
    storage: PromptLabStorage,
    execution_plan_id: str,
    prompt_profile_ids: list[str],
    binding_ids: list[str],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    try:
        plan = storage.load_design_object("execution_plan", execution_plan_id)
    except FileNotFoundError:
        return [
            _finding(
                "package.unknown_plan",
                f"Package references unknown execution plan '{execution_plan_id}'.",
            )
        ]

    requested_profiles = set(prompt_profile_ids)
    for profile_id in prompt_profile_ids:
        try:
            storage.load_design_object("prompt_profile", profile_id)
        except FileNotFoundError:
            findings.append(
                _finding(
                    "package.unknown_profile",
                    f"Package references unknown prompt profile '{profile_id}'.",
                )
            )

    bindings = []
    for binding_id in binding_ids:
        try:
            bindings.append(storage.load_design_object("binding_record", binding_id))
        except FileNotFoundError:
            findings.append(
                _finding(
                    "package.unknown_binding",
                    f"Package references unknown binding '{binding_id}'.",
                )
            )

    enabled_nodes = {node.id for node in plan.nodes if node.enabled}
    seen_nodes: set[str] = set()
    for binding in bindings:
        if binding.execution_plan_id != execution_plan_id:
            findings.append(
                _finding(
                    "package.binding_plan_mismatch",
                    f"Binding '{binding.id}' belongs to plan '{binding.execution_plan_id}', not '{execution_plan_id}'.",
                )
            )
        if binding.node_id not in {node.id for node in plan.nodes}:
            findings.append(
                _finding(
                    "package.binding_unknown_node",
                    f"Binding '{binding.id}' references node '{binding.node_id}' which is not in plan '{execution_plan_id}'.",
                )
            )
        if binding.prompt_profile_id not in requested_profiles:
            findings.append(
                _finding(
                    "package.binding_profile_not_in_package",
                    f"Binding '{binding.id}' uses prompt profile '{binding.prompt_profile_id}' which is not included in the package.",
                )
            )
        if binding.fallback_profile_id and binding.fallback_profile_id not in requested_profiles:
            findings.append(
                _finding(
                    "package.binding_fallback_not_in_package",
                    f"Binding '{binding.id}' uses fallback prompt profile '{binding.fallback_profile_id}' which is not included in the package.",
                )
            )
        if binding.node_id in seen_nodes:
            findings.append(
                _finding(
                    "package.duplicate_node_binding",
                    f"Package contains multiple bindings for node '{binding.node_id}'.",
                )
            )
        seen_nodes.add(binding.node_id)

    missing_nodes = enabled_nodes - seen_nodes
    for node_id in sorted(missing_nodes):
        findings.append(
            _finding(
                "package.missing_enabled_node_binding",
                f"Enabled node '{node_id}' is not covered by the selected package bindings.",
            )
        )

    return findings


def validate_active_state(
    storage: PromptLabStorage,
    active_state: ActivePromptLabState,
) -> list[dict[str, Any]]:
    if not active_state.published_package_id.strip():
        return [_finding("active.missing_package", "Active Prompt Lab state does not reference a published package.")]
    try:
        package = storage.load_design_object("published_prompt_lab_package", active_state.published_package_id)
    except FileNotFoundError:
        return [
            _finding(
                "active.unknown_package",
                f"Active Prompt Lab state references unknown package '{active_state.published_package_id}'.",
            )
        ]
    findings: list[dict[str, Any]] = []
    if active_state.package_fingerprint != package.package_fingerprint:
        findings.append(
            _finding(
                "active.fingerprint_mismatch",
                f"Active Prompt Lab state fingerprint does not match published package '{package.id}'.",
            )
        )
    if active_state.validation_snapshot_id and active_state.validation_snapshot_id != package.validation_snapshot_id:
        findings.append(
            _finding(
                "active.validation_snapshot_mismatch",
                f"Active Prompt Lab state validation snapshot does not match published package '{package.id}'.",
            )
        )
    return findings
