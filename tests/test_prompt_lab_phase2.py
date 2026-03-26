from __future__ import annotations

import json
from pathlib import Path

from src.core.prompt_lab import build_prompt_lab_services
from src.core.prompt_lab.contracts import BindingRecord, ExecutionNode, ExecutionPlan, PromptProfile
from src.prompt_lab.main import main as prompt_lab_main
from src.prompt_lab.workbench import build_workbench_state, launch_prompt_lab_workbench_process


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
    services.package_service.publish_package(
        package_id="pkg-default",
        package_name="Default Package",
        execution_plan_id="default-plan",
        prompt_profile_ids=["planner-default"],
        binding_ids=["bind-plan"],
        published_by="test",
    )
    services.package_service.activate_package("pkg-default", activated_by="test")


def test_build_workbench_state_reflects_prompt_lab_records(tmp_path: Path) -> None:
    services = build_prompt_lab_services(tmp_path)
    _seed_prompt_lab(services, tmp_path)

    state = build_workbench_state(tmp_path)

    assert state.project_root == tmp_path.resolve()
    assert state.counts["profiles"] == 1
    assert state.counts["plans"] == 1
    assert state.counts["bindings"] == 1
    assert state.counts["packages"] == 1
    assert state.active_package_id == "pkg-default"
    assert state.active_validation_status == "valid"
    assert state.active_validation_snapshot_id.startswith("validation-")
    assert state.latest_validation_status == "valid"
    assert state.latest_validation_id.startswith("validation-")
    assert "Active package: Default Package" in state.runtime_summary


def test_launch_prompt_lab_workbench_process_builds_subprocess_command(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakePopen:
        def __init__(self, command, cwd=None):
            captured["command"] = command
            captured["cwd"] = cwd

    monkeypatch.setattr("src.prompt_lab.workbench.subprocess.Popen", _FakePopen)
    err = launch_prompt_lab_workbench_process(tmp_path)

    assert err is None
    assert captured["cwd"] == str(tmp_path.resolve())
    command = captured["command"]
    assert isinstance(command, list)
    assert "--project-root" in command
    assert str(tmp_path.resolve()) in command
    assert any(str(part).endswith("src\\prompt_lab\\main.py") for part in command)


def test_prompt_lab_main_describe_reports_phase_2(tmp_path: Path, capsys) -> None:
    services = build_prompt_lab_services(tmp_path)
    _seed_prompt_lab(services, tmp_path)

    exit_code = prompt_lab_main(["--project-root", str(tmp_path), "--describe"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "phase_2"
    assert payload["entrypoint"] == "prompt_lab.main"
    assert payload["project_root"] == str(tmp_path.resolve())
