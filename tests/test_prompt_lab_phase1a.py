from __future__ import annotations

import json
from pathlib import Path

from src.core.prompt_lab.contracts import (
    BindingRecord,
    EvalRun,
    ExecutionNode,
    ExecutionPlan,
    PromptBuildArtifact,
    PromptProfile,
    PromotionRecord,
)
from src.core.prompt_lab.storage import build_prompt_lab_storage
from src.core.prompt_lab.validation import validate_prompt_lab_state
from src.prompt_lab.cli import main as prompt_lab_cli_main


def test_prompt_lab_storage_save_load_and_history(tmp_path: Path) -> None:
    storage = build_prompt_lab_storage(tmp_path)

    profile = storage.save_prompt_profile(
        PromptProfile(
            id="planner-default",
            name="Planner Default",
            role_target="planner_only",
            source_refs=["project_brief", "global_system"],
        )
    )
    plan = storage.save_execution_plan(
        ExecutionPlan(
            id="default-plan",
            name="Default Plan",
            nodes=[
                ExecutionNode(
                    id="step-plan",
                    label="Plan",
                    loop_type="planner_only",
                    order_index=0,
                )
            ],
        )
    )
    binding = storage.save_binding_record(
        BindingRecord(
            id="bind-plan",
            execution_plan_id=plan.id,
            node_id="step-plan",
            prompt_profile_id=profile.id,
        )
    )
    artifact = storage.save_build_artifact(
        PromptBuildArtifact(
            id="artifact-001",
            prompt_profile_id=profile.id,
            node_id="step-plan",
            compiled_text="You are a planner.",
        )
    )
    eval_run = storage.save_eval_run(
        EvalRun(
            id="eval-001",
            execution_plan_id=plan.id,
            suite_name="smoke",
            status="complete",
        )
    )
    promotion = storage.save_promotion_record(
        PromotionRecord(
            id="promotion-001",
            target_project=str(tmp_path),
            promoted_profiles=[profile.id],
            promoted_execution_plan_id=plan.id,
            promoted_binding_ids=[binding.id],
            validation_snapshot_id="validation-001",
            promoted_by="test",
        )
    )

    loaded_profile = storage.load_design_object("prompt_profile", profile.id)
    loaded_plan = storage.load_design_object("execution_plan", plan.id)
    loaded_binding = storage.load_design_object("binding_record", binding.id)
    loaded_artifact = storage.load_design_object("prompt_build_artifact", artifact.id)
    loaded_eval_run = storage.load_history_record("eval_run", eval_run.id)
    loaded_promotion = storage.load_history_record("promotion_record", promotion.id)

    assert loaded_profile.version_fingerprint
    assert loaded_plan.version_fingerprint
    assert loaded_binding.binding_fingerprint
    assert loaded_artifact.prompt_fingerprint
    assert loaded_eval_run.created_at
    assert loaded_promotion.promoted_at

    assert storage.list_design_objects("prompt_profile")[0]["id"] == profile.id
    assert storage.list_history_records("eval_run")[0]["id"] == eval_run.id


def test_prompt_lab_validation_catches_missing_binding(tmp_path: Path) -> None:
    storage = build_prompt_lab_storage(tmp_path)
    storage.save_prompt_profile(
        PromptProfile(
            id="planner-default",
            name="Planner Default",
            role_target="planner_only",
        )
    )
    storage.save_execution_plan(
        ExecutionPlan(
            id="default-plan",
            name="Default Plan",
            nodes=[
                ExecutionNode(
                    id="step-plan",
                    label="Plan",
                    loop_type="planner_only",
                    order_index=0,
                )
            ],
        )
    )

    snapshot = validate_prompt_lab_state(storage)

    assert snapshot.status == "invalid"
    assert any(
        finding["code"] == "binding.missing_enabled_node_binding"
        for finding in snapshot.findings
    )


def test_prompt_lab_cli_inspection_commands(tmp_path: Path, capsys) -> None:
    storage = build_prompt_lab_storage(tmp_path)
    storage.save_prompt_profile(
        PromptProfile(
            id="planner-default",
            name="Planner Default",
            role_target="planner_only",
        )
    )
    storage.save_execution_plan(
        ExecutionPlan(
            id="default-plan",
            name="Default Plan",
            nodes=[
                ExecutionNode(
                    id="step-plan",
                    label="Plan",
                    loop_type="planner_only",
                    order_index=0,
                )
            ],
        )
    )
    storage.save_binding_record(
        BindingRecord(
            id="bind-plan",
            execution_plan_id="default-plan",
            node_id="step-plan",
            prompt_profile_id="planner-default",
        )
    )

    assert prompt_lab_cli_main(["--project-root", str(tmp_path), "paths"]) == 0
    paths_payload = json.loads(capsys.readouterr().out)
    assert paths_payload["status"] == "ok"

    assert prompt_lab_cli_main(["--project-root", str(tmp_path), "list", "profiles"]) == 0
    list_payload = json.loads(capsys.readouterr().out)
    assert list_payload["count"] == 1

    assert (
        prompt_lab_cli_main(
            ["--project-root", str(tmp_path), "show", "plans", "default-plan"]
        )
        == 0
    )
    show_payload = json.loads(capsys.readouterr().out)
    assert show_payload["record"]["kind"] == "execution_plan"

    assert prompt_lab_cli_main(["--project-root", str(tmp_path), "validate"]) == 0
    validate_payload = json.loads(capsys.readouterr().out)
    assert validate_payload["status"] == "valid"
