from __future__ import annotations

import json
from pathlib import Path
import tempfile

from src.core.prompt_lab import build_prompt_lab_services
from src.core.prompt_lab.contracts import (
    BindingRecord,
    ExecutionNode,
    ExecutionPlan,
    PromptProfile,
    TrainingCase,
    TrainingSuite,
)
from src.core.prompt_lab.training_service import TrainingService
from src.prompt_lab.cli import main as prompt_lab_cli_main
from src.prompt_lab.entrypoints import build_prompt_lab_entrypoints
from src.prompt_lab.mcp_server import _dispatch as mcp_dispatch


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


def _save_direct_training_suite(services, suite_id: str = "suite-direct") -> TrainingSuite:
    return services.storage.save_training_suite(
        TrainingSuite(
            id=suite_id,
            name="Direct Training Suite",
            description="Small deterministic direct-probe suite for tests.",
            cases=[
                TrainingCase(
                    id="direct_case",
                    label="Direct Case",
                    probe_type="direct_model_probe",
                    prompt="Give a concise grounded answer.",
                    deterministic_checks=[{"type": "must_not_include_text", "value": "as an ai model", "critical": True}],
                    weight=1.0,
                )
            ],
        )
    )


def test_default_training_suite_is_seeded_into_prompt_lab_storage(tmp_path: Path) -> None:
    services = build_prompt_lab_services(tmp_path)

    suite = services.training_service.ensure_default_training_suite()

    assert suite.id == "default_training_suite"
    assert any(case.id == "existing_file_section_update" for case in suite.cases)
    assert any(case.id == "file_creation_readback" for case in suite.cases)
    suite_path = services.storage.paths.training_suites_dir / "default_training_suite.json"
    assert suite_path.exists()
    payload = json.loads(suite_path.read_text(encoding="utf-8"))
    assert payload["kind"] == "training_suite"
    assert payload["data"]["seeded_from"] == "_docs/benchmark_suite.json"


def test_training_run_persists_overlays_and_does_not_mutate_active_state(tmp_path: Path, monkeypatch) -> None:
    services = build_prompt_lab_services(tmp_path)
    _seed_prompt_lab(services, tmp_path)
    _publish_and_activate(services)
    _save_direct_training_suite(services)

    active_before = services.package_service.get_active_state()

    def fake_generate_overlay_text(**kwargs):
        return f"Overlay candidate {kwargs['candidate_index']}\nVERIFY_DISCIPLINE\n"

    def fake_evaluate_profile(*, profile_text: str, profile_label: str, **_: object):
        if "Candidate 1" in profile_label:
            score = 0.95
            criticals = 0
        elif "Candidate 2" in profile_label:
            score = 0.72
            criticals = 0
        else:
            score = 0.51
            criticals = 0
        return {
            "summary": {
                "profile_label": profile_label,
                "case_count": 1,
                "average_overall_score": score,
                "critical_failure_count": criticals,
                "passed_case_count": 1 if score >= 0.6 else 0,
                "total_weight": 1.0,
            },
            "cases": [{"case_id": "direct_case", "overall_score": score, "passed": score >= 0.6}],
        }

    monkeypatch.setattr(services.training_service, "_generate_overlay_text", fake_generate_overlay_text)
    monkeypatch.setattr(services.training_service, "_evaluate_profile", fake_evaluate_profile)

    result = services.training_service.run_training(
        package_id="pkg-default",
        profile_id="planner-default",
        suite_id="suite-direct",
        candidate_count=2,
    )

    assert result.training_run.id.startswith("training-planner-default-")
    assert result.recommended_profile_id.endswith("--cand-01")
    saved_run = services.training_service.get_training_run(result.training_run.id)
    assert saved_run.recommended_profile_id == result.recommended_profile_id
    assert len(saved_run.candidates) == 2

    candidate_profile = services.profile_service.get_profile(result.recommended_profile_id)
    overlay_ref = candidate_profile.source_refs[-1]
    overlay_path = tmp_path / overlay_ref
    assert overlay_path.exists()
    assert "VERIFY_DISCIPLINE" in overlay_path.read_text(encoding="utf-8")

    active_after = services.package_service.get_active_state()
    assert active_before is not None
    assert active_after is not None
    assert active_after.published_package_id == active_before.published_package_id
    assert services.package_service.resolve_active_package() is not None
    assert services.package_service.resolve_active_package().id == "pkg-default"


def test_training_case_scoring_penalizes_false_success_and_rewards_verified_edits(tmp_path: Path, monkeypatch) -> None:
    services = build_prompt_lab_services(tmp_path)
    _seed_prompt_lab(services, tmp_path)
    services.package_service.publish_package(
        package_id="pkg-default",
        package_name="Default Package",
        execution_plan_id="default-plan",
        prompt_profile_ids=["planner-default"],
        binding_ids=["bind-plan"],
        published_by="test",
    )
    services.storage.save_training_suite(
        TrainingSuite(
            id="suite-engine",
            name="Engine Training Suite",
            cases=[
                TrainingCase(
                    id="edit_case",
                    label="Edit Case",
                    probe_type="engine_turn_probe",
                    prompt="Update BUILD_PLAN.md and read it back.",
                    deterministic_checks=[
                        {"type": "requires_file_mutation", "critical": True},
                        {"type": "requires_file_readback", "critical": True},
                        {"type": "path_exists", "path": "BUILD_PLAN.md", "critical": True},
                        {"type": "path_contains_text", "path": "BUILD_PLAN.md", "value": "src/app.py", "critical": True},
                        {"type": "no_filesystem_guardrail_failure", "critical": True},
                    ],
                    target_path="BUILD_PLAN.md",
                )
            ],
        )
    )

    def fake_generate_overlay_text(**kwargs):
        return "VERIFY_OVERLAY\n"

    def fake_engine_probe(*, profile_text: str, **_: object):
        sandbox_root = Path(tempfile.mkdtemp(prefix="prompt_lab_training_case_", dir=tmp_path))
        target = sandbox_root / "BUILD_PLAN.md"
        if "VERIFY_OVERLAY" in profile_text:
            target.write_text("# Build Plan\n\n## Files\n- src/app.py\n", encoding="utf-8")
            return {
                "content": "Updated BUILD_PLAN.md, then read it back and confirmed src/app.py.",
                "sandbox_root": str(sandbox_root),
                "metadata": {
                    "filesystem_guardrail_failed": False,
                    "filesystem_evidence_summary": {
                        "file_mutation_called": True,
                        "file_read_called": True,
                        "successful_write_paths": ["BUILD_PLAN.md"],
                        "successful_replace_paths": [],
                        "successful_read_paths": ["BUILD_PLAN.md"],
                        "successful_run_paths": [],
                        "successful_list_files": [],
                        "mutation_count": 1,
                        "read_count": 1,
                    },
                },
            }
        target.write_text("# Build Plan\n\n## Files\n- TBD\n", encoding="utf-8")
        return {
            "content": "Updated BUILD_PLAN.md successfully.",
            "sandbox_root": str(sandbox_root),
            "metadata": {
                "filesystem_guardrail_failed": True,
                "filesystem_evidence_summary": {
                    "file_mutation_called": False,
                    "file_read_called": False,
                    "successful_write_paths": [],
                    "successful_replace_paths": [],
                    "successful_read_paths": [],
                    "successful_run_paths": [],
                    "successful_list_files": [],
                    "mutation_count": 0,
                    "read_count": 0,
                },
            },
        }

    monkeypatch.setattr(services.training_service, "_generate_overlay_text", fake_generate_overlay_text)
    monkeypatch.setattr(services.training_service, "_run_engine_probe", fake_engine_probe)

    result = services.training_service.run_training(
        package_id="pkg-default",
        profile_id="planner-default",
        suite_id="suite-engine",
        candidate_count=1,
    )

    baseline_summary = result.training_run.baseline_score["summary"]
    candidate_summary = result.training_run.candidates[0]["score_summary"]
    assert baseline_summary["critical_failure_count"] > 0
    assert candidate_summary["critical_failure_count"] == 0
    assert candidate_summary["average_overall_score"] > baseline_summary["average_overall_score"]
    assert result.recommended_profile_id.endswith("--cand-01")


def test_tiny_judge_runs_only_for_cases_that_define_judge_prompts(tmp_path: Path, monkeypatch) -> None:
    services = build_prompt_lab_services(tmp_path)
    suite = TrainingSuite(
        id="suite-judge",
        name="Judge Suite",
        cases=[
            TrainingCase(
                id="no_judge",
                label="No Judge",
                probe_type="direct_model_probe",
                prompt="Say something grounded.",
                deterministic_checks=[],
            ),
            TrainingCase(
                id="with_judge",
                label="With Judge",
                probe_type="direct_model_probe",
                prompt="Critique this bug report.",
                deterministic_checks=[],
                judge_prompt="Pass only if the critique is concise and grounded.",
            ),
        ],
    )
    judge_calls: list[str] = []

    def fake_direct_probe(*, case: TrainingCase, **_: object):
        return {
            "content": f"response for {case.id}",
            "metadata": {
                "filesystem_guardrail_failed": False,
                "filesystem_evidence_summary": {},
            },
        }

    def fake_judge(*, case: TrainingCase, **_: object):
        judge_calls.append(case.id)
        return {"used": True, "passed": True, "rationale": "ok", "score": 1.0}

    monkeypatch.setattr(services.training_service, "_run_direct_probe", fake_direct_probe)
    monkeypatch.setattr(services.training_service, "_run_tiny_judge", fake_judge)

    evaluation = services.training_service._evaluate_profile(
        suite=suite,
        profile_text="profile text",
        profile_label="Judge Test",
        target_model="qwen3.5:4b",
        judge_model="qwen2.5:1.5b",
        target_num_ctx=4096,
        judge_num_ctx=2048,
    )

    assert evaluation["summary"]["case_count"] == 2
    assert judge_calls == ["with_judge"]


def test_training_chat_context_defaults_are_gpu_safer(tmp_path: Path) -> None:
    services = build_prompt_lab_services(tmp_path)
    observed_calls: list[tuple[str, int]] = []

    def fake_chat_runner(*, model: str, num_ctx: int, **_: object):
        observed_calls.append((model, num_ctx))
        if model == "judge-model":
            return {"content": "{\"pass\": true, \"rationale\": \"ok\"}"}
        return {"content": "overlay or response"}

    training = TrainingService(
        services.storage,
        package_service=services.package_service,
        profile_service=services.profile_service,
        source_service=services.source_service,
        operation_log=None,
        chat_runner=fake_chat_runner,
    )

    training._generate_overlay_text(
        baseline_profile=PromptProfile(id="p", name="P", role_target="tool_agent", source_refs=[]),
        baseline_profile_text="baseline",
        suite=TrainingSuite(id="s", name="S", cases=[]),
        generator_model="generator-model",
        generator_num_ctx=4096,
        candidate_index=1,
        candidate_count=1,
    )
    training._run_direct_probe(
        case=TrainingCase(id="c1", label="Direct", probe_type="direct_model_probe", prompt="Hello"),
        profile_text="profile",
        target_model="target-model",
        target_num_ctx=4096,
    )
    training._run_tiny_judge(
        case=TrainingCase(
            id="c2",
            label="Judge",
            probe_type="direct_model_probe",
            prompt="Hello",
            judge_prompt="Pass if concise.",
        ),
        response_text="ok",
        judge_model="judge-model",
        judge_num_ctx=2048,
    )

    assert ("generator-model", 4096) in observed_calls
    assert ("target-model", 4096) in observed_calls
    assert ("judge-model", 2048) in observed_calls


def test_training_cli_and_mcp_commands_operate_on_persisted_runs(tmp_path: Path, capsys, monkeypatch) -> None:
    services = build_prompt_lab_services(tmp_path)
    _seed_prompt_lab(services, tmp_path)
    _publish_and_activate(services)
    _save_direct_training_suite(services)

    def fake_generate_overlay_text(self, **kwargs):
        return f"CLI overlay {kwargs['candidate_index']}\n"

    def fake_evaluate_profile(self, *, profile_text: str, profile_label: str, **_: object):
        score = 0.9 if "Candidate 1" in profile_label else 0.55
        return {
            "summary": {
                "profile_label": profile_label,
                "case_count": 1,
                "average_overall_score": score,
                "critical_failure_count": 0,
                "passed_case_count": 1 if score >= 0.6 else 0,
                "total_weight": 1.0,
            },
            "cases": [{"case_id": "direct_case", "overall_score": score, "passed": score >= 0.6}],
        }

    monkeypatch.setattr(TrainingService, "_generate_overlay_text", fake_generate_overlay_text)
    monkeypatch.setattr(TrainingService, "_evaluate_profile", fake_evaluate_profile)

    assert (
        prompt_lab_cli_main(
            [
                "--project-root",
                str(tmp_path),
                "train",
                "run",
                "--package",
                "pkg-default",
                "--profile",
                "planner-default",
                "--suite",
                "suite-direct",
                "--candidates",
                "1",
            ]
        )
        == 0
    )
    train_run_payload = json.loads(capsys.readouterr().out)
    run_id = train_run_payload["training_run"]["data"]["id"]
    assert train_run_payload["status"] == "ok"
    assert train_run_payload["recommended_profile_id"].endswith("--cand-01")

    assert prompt_lab_cli_main(["--project-root", str(tmp_path), "train", "list"]) == 0
    train_list_payload = json.loads(capsys.readouterr().out)
    assert train_list_payload["status"] == "ok"
    assert train_list_payload["records"]

    assert prompt_lab_cli_main(["--project-root", str(tmp_path), "train", "show", run_id]) == 0
    train_show_payload = json.loads(capsys.readouterr().out)
    assert train_show_payload["record"]["kind"] == "training_run"

    entrypoints = build_prompt_lab_entrypoints(tmp_path)

    mcp_run = mcp_dispatch(
        entrypoints,
        "prompt_lab_train_run",
        {
            "package_id": "pkg-default",
            "profile_id": "planner-default",
            "suite_id": "suite-direct",
            "candidate_count": 1,
        },
    )
    assert mcp_run["status"] == "ok"
    mcp_run_id = mcp_run["training_run"]["data"]["id"]

    mcp_list = mcp_dispatch(entrypoints, "prompt_lab_train_list", {})
    assert mcp_list["status"] == "ok"
    assert any(record["id"] == mcp_run_id for record in mcp_list["records"])

    mcp_show = mcp_dispatch(entrypoints, "prompt_lab_train_show", {"run_id": mcp_run_id})
    assert mcp_show["status"] == "ok"
    assert mcp_show["record"]["kind"] == "training_run"
