from __future__ import annotations

import json
from pathlib import Path

import src.app_prompt_lab as app_prompt_lab
from src.core.prompt_lab import build_prompt_lab_services
from src.core.prompt_lab.contracts import BindingRecord, ExecutionNode, ExecutionPlan, PromptProfile
from src.core.prompt_lab.runtime_loader import (
    describe_active_prompt_lab_runtime,
    load_active_prompt_lab_runtime,
)
from src.prompt_lab.cli import main as prompt_lab_cli_main
from src.prompt_lab.entrypoints import build_prompt_lab_entrypoints
from src.prompt_lab.mcp_server import _dispatch as mcp_dispatch
from src.prompt_lab.mcp_server import _handle_request as mcp_handle_request


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


def _publish_and_activate(services) -> None:
    services.package_service.publish_package(
        package_id="pkg-default",
        package_name="Default Package",
        execution_plan_id="default-plan",
        prompt_profile_ids=["planner-default"],
        binding_ids=["bind-plan"],
        published_by="test",
    )
    services.package_service.activate_package("pkg-default", activated_by="test")


def test_runtime_loader_resolves_only_active_published_state(tmp_path: Path) -> None:
    services = build_prompt_lab_services(tmp_path)
    _seed_prompt_lab(services, tmp_path)

    assert load_active_prompt_lab_runtime(tmp_path) is None
    assert "No active Prompt Lab package" in describe_active_prompt_lab_runtime(tmp_path)

    _publish_and_activate(services)
    bundle = load_active_prompt_lab_runtime(tmp_path)

    assert bundle is not None
    assert bundle.package.id == "pkg-default"
    assert bundle.execution_plan.id == "default-plan"
    assert [profile.id for profile in bundle.prompt_profiles] == ["planner-default"]
    assert [binding.id for binding in bundle.bindings] == ["bind-plan"]


def test_prompt_lab_cli_ops_reports_recent_operations(tmp_path: Path, capsys) -> None:
    services = build_prompt_lab_services(tmp_path)
    _seed_prompt_lab(services, tmp_path)
    _publish_and_activate(services)

    assert prompt_lab_cli_main(["--project-root", str(tmp_path), "ops", "--limit", "5"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "ok"
    assert payload["records"]
    assert any(record["action"] == "activate_package" for record in payload["records"])


def test_prompt_lab_mcp_dispatch_and_request_flow(tmp_path: Path) -> None:
    entrypoints = build_prompt_lab_entrypoints(tmp_path)
    _seed_prompt_lab(entrypoints.services, tmp_path)
    _publish_and_activate(entrypoints.services)

    active_result = mcp_dispatch(entrypoints, "prompt_lab_get_active", {})
    assert active_result["status"] == "ok"
    assert active_result["package"]["data"]["id"] == "pkg-default"

    request = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {
            "name": "prompt_lab_get_operations",
            "arguments": {"limit": 10},
        },
    }
    response = mcp_handle_request(entrypoints, request)
    assert response is not None
    assert response["id"] == 7
    assert response["result"]["isError"] is False
    structured = response["result"]["structuredContent"]
    assert structured["status"] == "ok"
    assert structured["records"]


def test_app_prompt_lab_summary_bridge_updates_ui_facade(tmp_path: Path) -> None:
    services = build_prompt_lab_services(tmp_path)
    _seed_prompt_lab(services, tmp_path)
    _publish_and_activate(services)

    captured: list[str] = []
    info_messages: list[tuple[str, str]] = []

    class _FakeUIFacade:
        def set_prompt_lab_summary(self, text: str) -> None:
            captured.append(text)

    class _FakeActivity:
        def info(self, source: str, message: str) -> None:
            info_messages.append((source, message))

    class _FakeState:
        ui_facade = _FakeUIFacade()
        activity = _FakeActivity()

    previous_root = app_prompt_lab._PROJECT_ROOT
    app_prompt_lab._PROJECT_ROOT = tmp_path
    try:
        summary = app_prompt_lab.refresh_prompt_lab_summary(_FakeState(), announce=True)
    finally:
        app_prompt_lab._PROJECT_ROOT = previous_root

    assert "Active package: Default Package" in summary
    assert captured and captured[-1] == summary
    assert info_messages == [("prompt_lab", "Prompt Lab active package summary reloaded")]


def test_app_prompt_lab_summary_bridge_prefers_attached_sandbox_root(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    attached_project = tmp_path / "attached_project"
    repo_root.mkdir(parents=True, exist_ok=True)
    attached_project.mkdir(parents=True, exist_ok=True)

    repo_services = build_prompt_lab_services(repo_root)
    _seed_prompt_lab(repo_services, repo_root)
    repo_services.package_service.publish_package(
        package_id="pkg-repo",
        package_name="Repo Package",
        execution_plan_id="default-plan",
        prompt_profile_ids=["planner-default"],
        binding_ids=["bind-plan"],
        published_by="test",
    )
    repo_services.package_service.activate_package("pkg-repo", activated_by="test")

    attached_services = build_prompt_lab_services(attached_project)
    _seed_prompt_lab(attached_services, attached_project)
    attached_services.package_service.publish_package(
        package_id="pkg-attached",
        package_name="Attached Package",
        execution_plan_id="default-plan",
        prompt_profile_ids=["planner-default"],
        binding_ids=["bind-plan"],
        published_by="test",
    )
    attached_services.package_service.activate_package("pkg-attached", activated_by="test")

    captured: list[str] = []

    class _FakeUIFacade:
        def set_prompt_lab_summary(self, text: str) -> None:
            captured.append(text)

    class _FakeConfig:
        sandbox_root = str(attached_project)

    class _FakeActivity:
        def info(self, source: str, message: str) -> None:
            return None

    class _FakeState:
        config = _FakeConfig()
        ui_facade = _FakeUIFacade()
        activity = _FakeActivity()

    previous_root = app_prompt_lab._PROJECT_ROOT
    app_prompt_lab._PROJECT_ROOT = repo_root
    try:
        summary = app_prompt_lab.refresh_prompt_lab_summary(_FakeState(), announce=False)
    finally:
        app_prompt_lab._PROJECT_ROOT = previous_root

    assert "Active package: Attached Package" in summary
    assert "Repo Package" not in summary
    assert captured and captured[-1] == summary
