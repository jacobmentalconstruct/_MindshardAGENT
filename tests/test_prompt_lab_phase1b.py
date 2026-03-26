from __future__ import annotations

import json
from pathlib import Path

from src.core.prompt_lab import build_prompt_lab_services
from src.core.prompt_lab.contracts import BindingRecord, ExecutionNode, ExecutionPlan, PromptProfile
from src.prompt_lab.cli import main as prompt_lab_cli_main


def _seed_prompt_lab(services, root: Path) -> None:
    (root / "prompts").mkdir(parents=True, exist_ok=True)
    (root / "prompts" / "planner.md").write_text("You are a planning agent.\n", encoding="utf-8")

    services.profile_service.save_profile(
        PromptProfile(
            id="planner-default",
            name="Planner Default",
            role_target="planner_only",
            source_refs=["prompts/planner.md"],
        )
    )
    services.execution_plan_service.save_plan(
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
    services.binding_service.save_binding(
        BindingRecord(
            id="bind-plan",
            execution_plan_id="default-plan",
            node_id="step-plan",
            prompt_profile_id="planner-default",
        )
    )


def test_prompt_lab_services_publish_and_activate(tmp_path: Path) -> None:
    services = build_prompt_lab_services(tmp_path)
    _seed_prompt_lab(services, tmp_path)

    source_refs = services.source_service.resolve_profile_sources(
        services.profile_service.get_profile("planner-default")
    )
    assert source_refs[0].metadata["exists"] is True
    assert "planning agent" in services.source_service.read_source_text("prompts/planner.md")

    publish_result = services.package_service.publish_package(
        package_id="pkg-default",
        package_name="Default Package",
        execution_plan_id="default-plan",
        prompt_profile_ids=["planner-default"],
        binding_ids=["bind-plan"],
        published_by="test",
    )

    assert publish_result.package.package_fingerprint
    assert publish_result.package.validation_status == "valid"

    active_state = services.package_service.activate_package("pkg-default", activated_by="test")
    resolved_package = services.package_service.resolve_active_package()

    assert active_state.published_package_id == "pkg-default"
    assert resolved_package is not None
    assert resolved_package.id == "pkg-default"


def test_prompt_lab_cli_publish_activate_and_active_view(tmp_path: Path, capsys) -> None:
    services = build_prompt_lab_services(tmp_path)
    _seed_prompt_lab(services, tmp_path)

    assert (
        prompt_lab_cli_main(
            [
                "--project-root",
                str(tmp_path),
                "publish",
                "pkg-default",
                "Default Package",
                "default-plan",
                "--profiles",
                "planner-default",
                "--bindings",
                "bind-plan",
                "--by",
                "cli-test",
            ]
        )
        == 0
    )
    publish_payload = json.loads(capsys.readouterr().out)
    assert publish_payload["status"] == "ok"
    assert publish_payload["package"]["kind"] == "published_prompt_lab_package"

    assert (
        prompt_lab_cli_main(
            [
                "--project-root",
                str(tmp_path),
                "activate",
                "pkg-default",
                "--by",
                "cli-test",
            ]
        )
        == 0
    )
    activate_payload = json.loads(capsys.readouterr().out)
    assert activate_payload["record"]["kind"] == "active_prompt_lab_state"

    assert prompt_lab_cli_main(["--project-root", str(tmp_path), "active"]) == 0
    active_payload = json.loads(capsys.readouterr().out)
    assert active_payload["status"] == "ok"
    assert active_payload["package"]["kind"] == "published_prompt_lab_package"
