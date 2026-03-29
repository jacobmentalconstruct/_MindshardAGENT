"""Canonical Prompt Lab data objects and JSON serialization helpers.

Phase 1A rules:
- JSON design objects are canonical for Prompt Lab design state.
- The stored model must stay graph-capable even while Phase 1 editing remains
  ordered-plan based.
- The CLI is an inspection/admin surface, not a freeform editing plane.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import hashlib
import json
from typing import Any, TypeAlias

from src.core.utils.clock import utc_iso

PROMPT_LAB_SCHEMA_VERSION = 1

PROMPT_PROFILE_KIND = "prompt_profile"
EXECUTION_PLAN_KIND = "execution_plan"
BINDING_RECORD_KIND = "binding_record"
PROMPT_BUILD_ARTIFACT_KIND = "prompt_build_artifact"
TRAINING_SUITE_KIND = "training_suite"
PUBLISHED_PROMPT_LAB_PACKAGE_KIND = "published_prompt_lab_package"
ACTIVE_PROMPT_LAB_STATE_KIND = "active_prompt_lab_state"
EVAL_RUN_KIND = "eval_run"
TRAINING_RUN_KIND = "training_run"
PROMOTION_RECORD_KIND = "promotion_record"
VALIDATION_SNAPSHOT_KIND = "validation_snapshot"


@dataclass(frozen=True)
class PromptSourceRef:
    id: str
    path: str
    source_type: str = "file"
    scope: str = "project"
    layer: str = "local"
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PromptProfile:
    id: str
    name: str
    role_target: str
    description: str = ""
    source_refs: list[str] = field(default_factory=list)
    compile_options: dict[str, Any] = field(default_factory=dict)
    override_metadata: dict[str, Any] = field(default_factory=dict)
    version_fingerprint: str = ""
    notes: str = ""


@dataclass(frozen=True)
class ExecutionNode:
    id: str
    label: str
    loop_type: str
    enabled: bool = True
    order_index: int = 0
    condition: dict[str, Any] = field(default_factory=dict)
    wrapper: dict[str, Any] = field(default_factory=dict)
    edges: list[dict[str, Any]] = field(default_factory=list)
    runtime_policy: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    notes: str = ""


@dataclass(frozen=True)
class ExecutionPlan:
    id: str
    name: str
    description: str = ""
    nodes: list[ExecutionNode] = field(default_factory=list)
    version_fingerprint: str = ""
    graph_capabilities: dict[str, Any] = field(
        default_factory=lambda: {
            "ordered_phase": True,
            "stable_node_identity": True,
            "wrapper_relationships": True,
            "conditional_edges_reserved": True,
        }
    )
    notes: str = ""


@dataclass(frozen=True)
class BindingRecord:
    id: str
    execution_plan_id: str
    node_id: str
    prompt_profile_id: str
    fallback_profile_id: str = ""
    binding_fingerprint: str = ""
    notes: str = ""


@dataclass(frozen=True)
class PromptBuildArtifact:
    id: str
    prompt_profile_id: str
    node_id: str = ""
    compiled_text: str = ""
    sections: list[dict[str, Any]] = field(default_factory=list)
    provenance: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_fingerprint: str = ""
    prompt_fingerprint: str = ""
    token_stats: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""


@dataclass(frozen=True)
class TrainingCase:
    id: str
    label: str
    probe_type: str
    prompt: str
    deterministic_checks: list[dict[str, Any]] = field(default_factory=list)
    judge_prompt: str = ""
    weight: float = 1.0
    target_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrainingSuite:
    id: str
    name: str
    description: str = ""
    cases: list[TrainingCase] = field(default_factory=list)
    seeded_from: str = ""
    version_fingerprint: str = ""
    notes: str = ""


@dataclass(frozen=True)
class PublishedPromptLabPackage:
    id: str
    package_name: str
    prompt_profile_ids: list[str] = field(default_factory=list)
    execution_plan_id: str = ""
    binding_ids: list[str] = field(default_factory=list)
    validation_snapshot_id: str = ""
    validation_status: str = "unknown"
    source_fingerprint: str = ""
    prompt_fingerprint: str = ""
    execution_plan_fingerprint: str = ""
    binding_fingerprint: str = ""
    package_fingerprint: str = ""
    created_at: str = ""
    published_at: str = ""
    published_by: str = ""
    notes: str = ""


@dataclass(frozen=True)
class ActivePromptLabState:
    id: str = "active"
    published_package_id: str = ""
    package_fingerprint: str = ""
    validation_snapshot_id: str = ""
    activated_at: str = ""
    activated_by: str = ""
    notes: str = ""


@dataclass(frozen=True)
class EvalRun:
    id: str
    execution_plan_id: str
    prompt_profile_versions: list[str] = field(default_factory=list)
    binding_versions: list[str] = field(default_factory=list)
    model_set: list[str] = field(default_factory=list)
    suite_name: str = ""
    status: str = "draft"
    findings: list[dict[str, Any]] = field(default_factory=list)
    scores: dict[str, Any] = field(default_factory=dict)
    artifact_refs: list[str] = field(default_factory=list)
    created_at: str = ""


@dataclass(frozen=True)
class TrainingRun:
    id: str
    package_id: str
    profile_id: str
    suite_id: str
    target_model: str
    generator_model: str
    judge_model: str = ""
    candidate_count: int = 0
    status: str = "draft"
    baseline_score: dict[str, Any] = field(default_factory=dict)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    winner_candidate_id: str = ""
    recommended_profile_id: str = ""
    delta_summary: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""


@dataclass(frozen=True)
class ValidationSnapshot:
    id: str
    status: str = "unknown"
    findings: list[dict[str, Any]] = field(default_factory=list)
    source_fingerprint: str = ""
    prompt_fingerprint: str = ""
    execution_plan_fingerprint: str = ""
    binding_fingerprint: str = ""
    created_at: str = ""


@dataclass(frozen=True)
class PromotionRecord:
    id: str
    target_project: str
    promoted_profiles: list[str] = field(default_factory=list)
    promoted_execution_plan_id: str = ""
    promoted_binding_ids: list[str] = field(default_factory=list)
    validation_snapshot_id: str = ""
    source_fingerprint: str = ""
    prompt_fingerprint: str = ""
    execution_plan_fingerprint: str = ""
    promoted_at: str = ""
    promoted_by: str = ""
    active: bool = False


DesignObject: TypeAlias = (
    PromptProfile
    | ExecutionPlan
    | BindingRecord
    | PromptBuildArtifact
    | TrainingSuite
    | PublishedPromptLabPackage
    | ActivePromptLabState
)
PromptLabRecord: TypeAlias = (
    PromptProfile
    | ExecutionPlan
    | BindingRecord
    | PromptBuildArtifact
    | TrainingSuite
    | PublishedPromptLabPackage
    | ActivePromptLabState
    | EvalRun
    | TrainingRun
    | PromotionRecord
    | ValidationSnapshot
)


RECORD_KIND_TO_TYPE: dict[str, type[PromptLabRecord]] = {
    PROMPT_PROFILE_KIND: PromptProfile,
    EXECUTION_PLAN_KIND: ExecutionPlan,
    BINDING_RECORD_KIND: BindingRecord,
    PROMPT_BUILD_ARTIFACT_KIND: PromptBuildArtifact,
    TRAINING_SUITE_KIND: TrainingSuite,
    PUBLISHED_PROMPT_LAB_PACKAGE_KIND: PublishedPromptLabPackage,
    ACTIVE_PROMPT_LAB_STATE_KIND: ActivePromptLabState,
    EVAL_RUN_KIND: EvalRun,
    TRAINING_RUN_KIND: TrainingRun,
    PROMOTION_RECORD_KIND: PromotionRecord,
    VALIDATION_SNAPSHOT_KIND: ValidationSnapshot,
}

TYPE_TO_RECORD_KIND: dict[type[PromptLabRecord], str] = {
    record_type: kind for kind, record_type in RECORD_KIND_TO_TYPE.items()
}

JSON_DESIGN_KINDS = {
    PROMPT_PROFILE_KIND,
    EXECUTION_PLAN_KIND,
    BINDING_RECORD_KIND,
    PROMPT_BUILD_ARTIFACT_KIND,
    TRAINING_SUITE_KIND,
    PUBLISHED_PROMPT_LAB_PACKAGE_KIND,
    ACTIVE_PROMPT_LAB_STATE_KIND,
}
SQLITE_HISTORY_KINDS = {
    EVAL_RUN_KIND,
    TRAINING_RUN_KIND,
    PROMOTION_RECORD_KIND,
    VALIDATION_SNAPSHOT_KIND,
}


def stable_json_dumps(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, separators=(",", ": "))


def compute_fingerprint(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_record_kind(record: PromptLabRecord) -> str:
    record_type = type(record)
    try:
        return TYPE_TO_RECORD_KIND[record_type]
    except KeyError as exc:
        raise TypeError(f"Unsupported Prompt Lab record type: {record_type!r}") from exc


def _execution_node_from_dict(data: dict[str, Any]) -> ExecutionNode:
    return ExecutionNode(
        id=str(data.get("id", "")),
        label=str(data.get("label", "")),
        loop_type=str(data.get("loop_type", "")),
        enabled=bool(data.get("enabled", True)),
        order_index=int(data.get("order_index", 0)),
        condition=dict(data.get("condition", {})),
        wrapper=dict(data.get("wrapper", {})),
        edges=list(data.get("edges", [])),
        runtime_policy=dict(data.get("runtime_policy", {})),
        metadata=dict(data.get("metadata", {})),
        notes=str(data.get("notes", "")),
    )


def _training_case_from_dict(data: dict[str, Any]) -> TrainingCase:
    return TrainingCase(
        id=str(data.get("id", "")),
        label=str(data.get("label", "")),
        probe_type=str(data.get("probe_type", "")),
        prompt=str(data.get("prompt", "")),
        deterministic_checks=list(data.get("deterministic_checks", [])),
        judge_prompt=str(data.get("judge_prompt", "")),
        weight=float(data.get("weight", 1.0)),
        target_path=str(data.get("target_path", "")),
        metadata=dict(data.get("metadata", {})),
    )


def _record_from_dict(kind: str, data: dict[str, Any]) -> PromptLabRecord:
    if kind == EXECUTION_PLAN_KIND:
        return ExecutionPlan(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            nodes=[_execution_node_from_dict(node) for node in data.get("nodes", [])],
            version_fingerprint=str(data.get("version_fingerprint", "")),
            graph_capabilities=dict(data.get("graph_capabilities", {})),
            notes=str(data.get("notes", "")),
        )
    if kind == TRAINING_SUITE_KIND:
        return TrainingSuite(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            cases=[_training_case_from_dict(case) for case in data.get("cases", [])],
            seeded_from=str(data.get("seeded_from", "")),
            version_fingerprint=str(data.get("version_fingerprint", "")),
            notes=str(data.get("notes", "")),
        )
    record_type = RECORD_KIND_TO_TYPE[kind]
    return record_type(**data)


def canonicalize_record(record: PromptLabRecord) -> PromptLabRecord:
    if isinstance(record, PromptProfile):
        fingerprint = compute_fingerprint(
            {
                "id": record.id,
                "name": record.name,
                "role_target": record.role_target,
                "description": record.description,
                "source_refs": record.source_refs,
                "compile_options": record.compile_options,
                "override_metadata": record.override_metadata,
                "notes": record.notes,
            }
        )
        return replace(record, version_fingerprint=fingerprint)
    if isinstance(record, ExecutionPlan):
        fingerprint = compute_fingerprint(
            {
                "id": record.id,
                "name": record.name,
                "description": record.description,
                "nodes": [asdict(node) for node in record.nodes],
                "graph_capabilities": record.graph_capabilities,
                "notes": record.notes,
            }
        )
        return replace(record, version_fingerprint=fingerprint)
    if isinstance(record, BindingRecord):
        fingerprint = compute_fingerprint(
            {
                "id": record.id,
                "execution_plan_id": record.execution_plan_id,
                "node_id": record.node_id,
                "prompt_profile_id": record.prompt_profile_id,
                "fallback_profile_id": record.fallback_profile_id,
                "notes": record.notes,
            }
        )
        return replace(record, binding_fingerprint=fingerprint)
    if isinstance(record, PromptBuildArtifact):
        created_at = record.created_at or utc_iso()
        source_fingerprint = record.source_fingerprint or compute_fingerprint(record.provenance)
        prompt_fingerprint = record.prompt_fingerprint or compute_fingerprint(
            {
                "compiled_text": record.compiled_text,
                "sections": record.sections,
                "warnings": record.warnings,
                "token_stats": record.token_stats,
                "source_fingerprint": source_fingerprint,
            }
        )
        return replace(
            record,
            created_at=created_at,
            source_fingerprint=source_fingerprint,
            prompt_fingerprint=prompt_fingerprint,
        )
    if isinstance(record, TrainingSuite):
        fingerprint = compute_fingerprint(
            {
                "id": record.id,
                "name": record.name,
                "description": record.description,
                "cases": [asdict(case) for case in record.cases],
                "seeded_from": record.seeded_from,
                "notes": record.notes,
            }
        )
        return replace(record, version_fingerprint=fingerprint)
    if isinstance(record, PublishedPromptLabPackage):
        created_at = record.created_at or utc_iso()
        published_at = record.published_at or created_at
        package_fingerprint = record.package_fingerprint or compute_fingerprint(
            {
                "id": record.id,
                "package_name": record.package_name,
                "prompt_profile_ids": record.prompt_profile_ids,
                "execution_plan_id": record.execution_plan_id,
                "binding_ids": record.binding_ids,
                "validation_snapshot_id": record.validation_snapshot_id,
                "validation_status": record.validation_status,
                "source_fingerprint": record.source_fingerprint,
                "prompt_fingerprint": record.prompt_fingerprint,
                "execution_plan_fingerprint": record.execution_plan_fingerprint,
                "binding_fingerprint": record.binding_fingerprint,
                "notes": record.notes,
            }
        )
        return replace(
            record,
            created_at=created_at,
            published_at=published_at,
            package_fingerprint=package_fingerprint,
        )
    if isinstance(record, ActivePromptLabState):
        return replace(record, activated_at=record.activated_at or utc_iso())
    if isinstance(record, EvalRun):
        return replace(record, created_at=record.created_at or utc_iso())
    if isinstance(record, TrainingRun):
        return replace(record, created_at=record.created_at or utc_iso())
    if isinstance(record, ValidationSnapshot):
        created_at = record.created_at or utc_iso()
        snapshot_id = record.id or f"validation-{compute_fingerprint({'created_at': created_at, 'findings': record.findings})[:12]}"
        return replace(record, id=snapshot_id, created_at=created_at)
    if isinstance(record, PromotionRecord):
        return replace(record, promoted_at=record.promoted_at or utc_iso())
    return record


def serialize_record(record: PromptLabRecord) -> dict[str, Any]:
    canonical = canonicalize_record(record)
    return {
        "schema_version": PROMPT_LAB_SCHEMA_VERSION,
        "kind": get_record_kind(canonical),
        "data": asdict(canonical),
    }


def deserialize_record(payload: dict[str, Any]) -> PromptLabRecord:
    kind = str(payload.get("kind", ""))
    if kind not in RECORD_KIND_TO_TYPE:
        raise ValueError(f"Unknown Prompt Lab record kind: {kind!r}")
    data = payload.get("data", {})
    if not isinstance(data, dict):
        raise ValueError("Prompt Lab record payload must contain an object under 'data'")
    return canonicalize_record(_record_from_dict(kind, data))
