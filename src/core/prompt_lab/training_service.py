"""Manual batch prompt training over Prompt Lab packages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
import tempfile
from typing import Any, Callable

from src.core.agent.benchmark_loader import load_benchmark_suites
from src.core.agent.prompt_builder import build_system_prompt
from src.core.agent.tool_agent_turn_runner import run_tool_agent_turn
from src.core.config.app_config import AppConfig
from src.core.ollama.ollama_client import chat_stream
from src.core.runtime.activity_stream import ActivityStream
from src.core.sandbox.cli_runner import CLIRunner
from src.core.sandbox.command_policy import CommandPolicy
from src.core.sandbox.file_writer import FileWriter
from src.core.sandbox.path_guard import PathGuard
from src.core.sandbox.tool_catalog import ToolCatalog
from src.core.agent.tool_router import ToolRouter
from src.core.utils.clock import utc_iso

from .contracts import PromptProfile, TrainingCase, TrainingRun, TrainingSuite
from .operation_log import PromptLabOperationLog
from .package_service import PackageService
from .profile_service import ProfileService
from .source_service import SourceService
from .storage import PromptLabStorage


DEFAULT_TRAINING_SUITE_ID = "default_training_suite"
DEFAULT_TARGET_MODEL = "qwen3.5:4b"
DEFAULT_GENERATOR_MODEL = "qwen3.5:9b"
DEFAULT_JUDGE_MODEL = "qwen2.5:1.5b"
DEFAULT_TARGET_NUM_CTX = 4096
DEFAULT_GENERATOR_NUM_CTX = 4096
DEFAULT_JUDGE_NUM_CTX = 2048


@dataclass(frozen=True)
class TrainingRunResult:
    training_run: TrainingRun
    baseline_profile_id: str
    recommended_profile_id: str


class TrainingService:
    """Manual batch training service for one prompt profile at a time."""

    def __init__(
        self,
        storage: PromptLabStorage,
        *,
        package_service: PackageService,
        profile_service: ProfileService,
        source_service: SourceService,
        operation_log: PromptLabOperationLog | None = None,
        chat_runner: Callable[..., dict[str, Any]] = chat_stream,
    ):
        self.storage = storage
        self.package_service = package_service
        self.profile_service = profile_service
        self.source_service = source_service
        self._operation_log = operation_log
        self._chat_runner = chat_runner

    def ensure_default_training_suite(self) -> TrainingSuite:
        try:
            return self.get_training_suite(DEFAULT_TRAINING_SUITE_ID)
        except FileNotFoundError:
            suite = self._seed_default_training_suite()
            if self._operation_log is not None:
                self._operation_log.record(
                    channel="service",
                    action="seed_default_training_suite",
                    status="ok",
                    details={"suite_id": suite.id, "case_count": len(suite.cases)},
                )
            return suite

    def list_training_suites(self) -> list[dict[str, Any]]:
        items = self.storage.list_design_objects("training_suite")
        if self._operation_log is not None:
            self._operation_log.record(
                channel="service",
                action="list_training_suites",
                status="ok",
                details={"count": len(items)},
            )
        return items

    def get_training_suite(self, suite_id: str) -> TrainingSuite:
        suite = self.storage.load_design_object("training_suite", suite_id)
        if self._operation_log is not None:
            self._operation_log.record(
                channel="service",
                action="get_training_suite",
                status="ok",
                details={"suite_id": suite_id},
            )
        return suite

    def list_training_runs(self) -> list[dict[str, Any]]:
        items = self.storage.list_history_records("training_run")
        if self._operation_log is not None:
            self._operation_log.record(
                channel="service",
                action="list_training_runs",
                status="ok",
                details={"count": len(items)},
            )
        return items

    def get_training_run(self, run_id: str) -> TrainingRun:
        run = self.storage.load_history_record("training_run", run_id)
        if self._operation_log is not None:
            self._operation_log.record(
                channel="service",
                action="get_training_run",
                status="ok",
                details={"run_id": run_id},
            )
        return run

    def run_training(
        self,
        *,
        package_id: str,
        profile_id: str,
        suite_id: str = DEFAULT_TRAINING_SUITE_ID,
        target_model: str = DEFAULT_TARGET_MODEL,
        generator_model: str = DEFAULT_GENERATOR_MODEL,
        judge_model: str = DEFAULT_JUDGE_MODEL,
        candidate_count: int = 3,
        target_num_ctx: int | None = None,
        generator_num_ctx: int | None = None,
        judge_num_ctx: int | None = None,
    ) -> TrainingRunResult:
        if candidate_count < 1:
            raise ValueError("candidate_count must be at least 1")

        suite = self.ensure_default_training_suite() if suite_id == DEFAULT_TRAINING_SUITE_ID else self.get_training_suite(suite_id)
        package = self.package_service.get_published_package(package_id)
        if profile_id not in package.prompt_profile_ids:
            raise ValueError(f"Profile {profile_id!r} is not part of package {package_id!r}")

        baseline_profile = self.profile_service.get_profile(profile_id)
        run_id = f"training-{profile_id}-{_timestamp_suffix()}"
        context_limits = self._resolve_training_context_limits(
            target_num_ctx=target_num_ctx,
            generator_num_ctx=generator_num_ctx,
            judge_num_ctx=judge_num_ctx,
        )

        baseline_profile_text = self._compose_profile_text(baseline_profile)
        baseline_eval = self._evaluate_profile(
            suite=suite,
            profile_text=baseline_profile_text,
            profile_label=baseline_profile.name,
            target_model=target_model,
            judge_model=judge_model,
            target_num_ctx=context_limits["target_num_ctx"],
            judge_num_ctx=context_limits["judge_num_ctx"],
        )

        candidate_records: list[dict[str, Any]] = []
        for index in range(1, candidate_count + 1):
            overlay_text = self._generate_overlay_text(
                baseline_profile=baseline_profile,
                baseline_profile_text=baseline_profile_text,
                suite=suite,
                generator_model=generator_model,
                generator_num_ctx=context_limits["generator_num_ctx"],
                candidate_index=index,
                candidate_count=candidate_count,
            )
            overlay_ref = self._write_overlay_file(
                run_id=run_id,
                baseline_profile_id=baseline_profile.id,
                candidate_index=index,
                overlay_text=overlay_text,
            )
            candidate_profile = self.profile_service.save_profile(
                PromptProfile(
                    id=f"{baseline_profile.id}--{run_id}--cand-{index:02d}",
                    name=f"{baseline_profile.name} Candidate {index}",
                    role_target=baseline_profile.role_target,
                    description=f"Training candidate {index} from {baseline_profile.id}",
                    source_refs=[*baseline_profile.source_refs, overlay_ref],
                    compile_options=dict(baseline_profile.compile_options),
                    override_metadata={
                        **dict(baseline_profile.override_metadata),
                        "training_run_id": run_id,
                        "candidate_index": index,
                        "overlay_source_ref": overlay_ref,
                    },
                    notes=f"Generated during training run {run_id}.",
                )
            )
            candidate_text = self._compose_profile_text(candidate_profile)
            candidate_eval = self._evaluate_profile(
                suite=suite,
                profile_text=candidate_text,
                profile_label=candidate_profile.name,
                target_model=target_model,
                judge_model=judge_model,
                target_num_ctx=context_limits["target_num_ctx"],
                judge_num_ctx=context_limits["judge_num_ctx"],
            )
            candidate_records.append(
                {
                    "candidate_id": f"{run_id}-cand-{index:02d}",
                    "prompt_profile_id": candidate_profile.id,
                    "overlay_source_ref": overlay_ref,
                    "overlay_preview": overlay_text[:800],
                    "score_summary": candidate_eval["summary"],
                    "case_results": candidate_eval["cases"],
                }
            )

        baseline_summary = baseline_eval["summary"]
        winner = self._select_winner(baseline_summary, candidate_records)
        delta_summary = self._build_delta_summary(baseline_summary, winner)
        recommended_profile_id = winner.get("prompt_profile_id", "") if winner else ""

        training_run = self.storage.save_training_run(
            TrainingRun(
                id=run_id,
                package_id=package.id,
                profile_id=profile_id,
                suite_id=suite.id,
                target_model=target_model,
                generator_model=generator_model,
                judge_model=judge_model,
                candidate_count=candidate_count,
                status="completed",
                baseline_score={
                    "profile_id": baseline_profile.id,
                    "summary": baseline_summary,
                    "case_results": baseline_eval["cases"],
                },
                candidates=candidate_records,
                winner_candidate_id=winner.get("candidate_id", "") if winner else "",
                recommended_profile_id=recommended_profile_id,
                delta_summary=delta_summary,
            )
        )
        if self._operation_log is not None:
            self._operation_log.record(
                channel="service",
                action="run_training",
                status="ok",
                details={
                    "run_id": training_run.id,
                    "package_id": package.id,
                    "profile_id": profile_id,
                    "suite_id": suite.id,
                    "candidate_count": candidate_count,
                    "target_num_ctx": context_limits["target_num_ctx"],
                    "generator_num_ctx": context_limits["generator_num_ctx"],
                    "judge_num_ctx": context_limits["judge_num_ctx"],
                    "winner_candidate_id": training_run.winner_candidate_id,
                    "recommended_profile_id": training_run.recommended_profile_id,
                },
            )
        return TrainingRunResult(
            training_run=training_run,
            baseline_profile_id=baseline_profile.id,
            recommended_profile_id=recommended_profile_id,
        )

    def _seed_default_training_suite(self) -> TrainingSuite:
        imported_cases: list[TrainingCase] = []
        loaded = load_benchmark_suites(self.storage.project_root)
        for suite_name in ("default", "planning"):
            suite = loaded.get(suite_name)
            if not suite:
                continue
            for case in suite.cases:
                imported_cases.append(
                    TrainingCase(
                        id=f"imported_{suite_name}_{case.id}",
                        label=case.label,
                        probe_type=case.probe_type,
                        prompt=case.prompt,
                        judge_prompt=(
                            "Return JSON with keys pass (boolean) and rationale (short string). "
                            "Pass only if the response is accurate, grounded, and directly answers the prompt."
                        ),
                        metadata={"imported_suite": suite_name},
                    )
                )

        training_cases = [
            TrainingCase(
                id="existing_file_section_update",
                label="Existing File Section Update",
                probe_type="engine_turn_probe",
                prompt=(
                    "Update the `Files` section in BUILD_PLAN.md so it lists `src/app.py` and "
                    "`tests/test_app.py`, then read the file back and confirm the update."
                ),
                deterministic_checks=[
                    {"type": "requires_file_mutation", "critical": True},
                    {"type": "requires_file_readback", "critical": True},
                    {"type": "path_exists", "path": "BUILD_PLAN.md", "critical": True},
                    {"type": "path_contains_text", "path": "BUILD_PLAN.md", "value": "src/app.py", "critical": True},
                    {"type": "path_contains_text", "path": "BUILD_PLAN.md", "value": "tests/test_app.py", "critical": True},
                    {"type": "no_filesystem_guardrail_failure", "critical": True},
                ],
                weight=2.0,
                target_path="BUILD_PLAN.md",
                metadata={
                    "workspace_files": {
                        "BUILD_PLAN.md": (
                            "# Build Plan\n\n## Goal\n- Create the app skeleton.\n\n"
                            "## Files\n- TBD\n\n## Steps\n- Placeholder step\n"
                        )
                    }
                },
            ),
            TrainingCase(
                id="file_creation_readback",
                label="File Creation With Readback",
                probe_type="engine_turn_probe",
                prompt="Create `todo_cli/src/app.py` with a small `hello()` function, then read the file back and confirm the created content.",
                deterministic_checks=[
                    {"type": "requires_file_mutation", "critical": True},
                    {"type": "requires_file_readback", "critical": True},
                    {"type": "path_exists", "path": "todo_cli/src/app.py", "critical": True},
                    {"type": "path_contains_text", "path": "todo_cli/src/app.py", "value": "def hello(", "critical": True},
                    {"type": "no_filesystem_guardrail_failure", "critical": True},
                ],
                weight=2.0,
                target_path="todo_cli/src/app.py",
            ),
            TrainingCase(
                id="false_success_avoidance",
                label="Avoid Unsupported File Claims",
                probe_type="engine_turn_probe",
                prompt="Create `notes/output.txt`, read it back, and confirm the exact path you changed. Do not claim success unless the file tools confirm it.",
                deterministic_checks=[
                    {"type": "requires_file_mutation", "critical": True},
                    {"type": "requires_file_readback", "critical": True},
                    {"type": "path_exists", "path": "notes/output.txt", "critical": True},
                    {"type": "named_path_matches_evidence", "path": "notes/output.txt", "critical": True},
                    {"type": "no_filesystem_guardrail_failure", "critical": True},
                ],
                weight=2.0,
                target_path="notes/output.txt",
            ),
            TrainingCase(
                id="concise_critique_quality",
                label="Concise Critique Quality",
                probe_type="direct_model_probe",
                prompt="Review this change request: 'A Python function catches every exception and silently returns None even when file writes fail.' Give a concise critique focused on the most important risks.",
                deterministic_checks=[
                    {"type": "must_include_text", "value": "risk", "critical": False},
                    {"type": "must_not_include_text", "value": "as an ai model", "critical": True},
                ],
                judge_prompt="Return JSON with keys pass (boolean) and rationale (short string). Pass only if the response is concise, technically grounded, and identifies the main bug risks.",
                weight=1.5,
            ),
        ]

        return self.storage.save_training_suite(
            TrainingSuite(
                id=DEFAULT_TRAINING_SUITE_ID,
                name="Default Training Suite",
                description="Seeded from the benchmark spine plus Prompt Lab training cases for file edits, grounded planning, and concise critique quality.",
                cases=[*imported_cases, *training_cases],
                seeded_from="_docs/benchmark_suite.json",
                notes="Prompt Lab-owned runtime training suite copy.",
            )
        )

    def _compose_profile_text(self, profile: PromptProfile) -> str:
        parts: list[str] = []
        for source_ref in profile.source_refs:
            source_text = self.source_service.read_source_text(source_ref)
            parts.append(f"[SOURCE: {source_ref}]\n{source_text.strip()}")
        return "\n\n".join(part for part in parts if part.strip())

    def _generate_overlay_text(
        self,
        *,
        baseline_profile: PromptProfile,
        baseline_profile_text: str,
        suite: TrainingSuite,
        generator_model: str,
        generator_num_ctx: int,
        candidate_index: int,
        candidate_count: int,
    ) -> str:
        suite_digest = "\n".join(
            f"- {case.id}: {case.label} [{case.probe_type}]"
            for case in suite.cases[:12]
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are generating a compact prompt overlay for a smaller target model. "
                    "Return only the overlay text. Do not include explanations, fences, or JSON."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Target profile: {baseline_profile.id} ({baseline_profile.role_target})\n"
                    f"Candidate {candidate_index} of {candidate_count}\n\n"
                    "Base profile text:\n"
                    f"{baseline_profile_text}\n\n"
                    "Training suite digest:\n"
                    f"{suite_digest}\n\n"
                    "Write a concise overlay that could improve the target model's grounding, "
                    "file-edit reliability, and verification discipline."
                ),
            },
        ]
        result = self._chat_runner(
            base_url="http://localhost:11434",
            model=generator_model,
            messages=messages,
            temperature=0.7,
            num_ctx=generator_num_ctx,
        )
        overlay = str(result.get("content", "")).strip()
        if not overlay:
            overlay = (
                "Verify file edits through tool evidence before claiming success.\n"
                "Prefer numbered reads before editing existing files.\n"
                "When uncertain, inspect the file directly instead of guessing."
            )
        return overlay + ("\n" if not overlay.endswith("\n") else "")

    def _write_overlay_file(
        self,
        *,
        run_id: str,
        baseline_profile_id: str,
        candidate_index: int,
        overlay_text: str,
    ) -> str:
        overlay_dir = self.storage.paths.source_overlays_dir / run_id
        overlay_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{baseline_profile_id}--cand-{candidate_index:02d}.md"
        overlay_path = overlay_dir / filename
        overlay_path.write_text(overlay_text, encoding="utf-8", newline="\n")
        return str(overlay_path.relative_to(self.storage.project_root)).replace("\\", "/")

    def _evaluate_profile(
        self,
        *,
        suite: TrainingSuite,
        profile_text: str,
        profile_label: str,
        target_model: str,
        judge_model: str,
        target_num_ctx: int,
        judge_num_ctx: int,
    ) -> dict[str, Any]:
        case_results = [
            self._run_training_case(
                case=case,
                profile_text=profile_text,
                profile_label=profile_label,
                target_model=target_model,
                judge_model=judge_model,
                target_num_ctx=target_num_ctx,
                judge_num_ctx=judge_num_ctx,
            )
            for case in suite.cases
        ]
        total_weight = sum(float(case.get("weight", 1.0)) for case in case_results) or 1.0
        weighted_score = sum(float(case["overall_score"]) * float(case.get("weight", 1.0)) for case in case_results)
        critical_failures = sum(1 for case in case_results if case.get("critical_failure"))
        return {
            "summary": {
                "profile_label": profile_label,
                "case_count": len(case_results),
                "average_overall_score": round(weighted_score / total_weight, 3),
                "critical_failure_count": critical_failures,
                "passed_case_count": sum(1 for case in case_results if case.get("passed")),
                "total_weight": round(total_weight, 3),
            },
            "cases": case_results,
        }

    def _run_training_case(
        self,
        *,
        case: TrainingCase,
        profile_text: str,
        profile_label: str,
        target_model: str,
        judge_model: str,
        target_num_ctx: int,
        judge_num_ctx: int,
    ) -> dict[str, Any]:
        if case.probe_type == "engine_turn_probe":
            runtime = self._run_engine_probe(
                case=case,
                profile_text=profile_text,
                target_model=target_model,
                target_num_ctx=target_num_ctx,
            )
        else:
            runtime = self._run_direct_probe(
                case=case,
                profile_text=profile_text,
                target_model=target_model,
                target_num_ctx=target_num_ctx,
            )

        deterministic = _evaluate_deterministic_checks(
            case=case,
            response_text=runtime["content"],
            metadata=runtime["metadata"],
            sandbox_root=runtime.get("sandbox_root", ""),
        )
        judge = {"used": False, "passed": None, "rationale": "", "score": None}
        if case.judge_prompt and not deterministic["critical_failure"]:
            judge = self._run_tiny_judge(
                case=case,
                response_text=runtime["content"],
                judge_model=judge_model,
                judge_num_ctx=judge_num_ctx,
            )

        deterministic_score = float(deterministic["score"])
        overall_score = (
            round((deterministic_score * 0.8) + (float(judge["score"]) * 0.2), 3)
            if judge["used"]
            else deterministic_score
        )
        passed = overall_score >= 0.6 and not deterministic["critical_failure"]
        return {
            "case_id": case.id,
            "label": case.label,
            "probe_type": case.probe_type,
            "weight": case.weight,
            "status": "passed" if passed else "failed",
            "passed": passed,
            "critical_failure": deterministic["critical_failure"],
            "deterministic_score": deterministic_score,
            "judge_score": judge["score"],
            "overall_score": overall_score,
            "deterministic": deterministic,
            "judge": judge,
            "response_excerpt": runtime["content"][:1200],
            "metadata": runtime["metadata"],
        }

    def _run_direct_probe(
        self,
        *,
        case: TrainingCase,
        profile_text: str,
        target_model: str,
        target_num_ctx: int,
    ) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": self._compose_direct_probe_system_prompt(profile_text)},
            {"role": "user", "content": case.prompt},
        ]
        result = self._chat_runner(
            base_url="http://localhost:11434",
            model=target_model,
            messages=messages,
            temperature=0.7,
            num_ctx=target_num_ctx,
        )
        return {
            "content": str(result.get("content", "")).strip(),
            "metadata": {
                "model": result.get("model", target_model),
                "tokens_in": result.get("prompt_eval_count", 0),
                "tokens_out": result.get("eval_count", 0),
                "wall_ms": result.get("wall_ms", 0),
                "rounds": 1,
                "filesystem_guardrail_failed": False,
                "filesystem_evidence_summary": {},
            },
        }

    def _run_engine_probe(
        self,
        *,
        case: TrainingCase,
        profile_text: str,
        target_model: str,
        target_num_ctx: int,
    ) -> dict[str, Any]:
        sandbox_root = Path(tempfile.mkdtemp(prefix=f"prompt_lab_training_{case.id}_"))
        self._seed_case_workspace(sandbox_root, case)

        activity = ActivityStream()
        guard = PathGuard(str(sandbox_root))
        policy = CommandPolicy(mode="allowlist")
        cli = CLIRunner(guard, activity, policy=policy)
        writer = FileWriter(guard, activity)
        catalog = ToolCatalog()
        router = ToolRouter(catalog, cli, activity, file_writer=writer, sandbox_root=str(sandbox_root))
        config = AppConfig(
            selected_model=target_model,
            planner_model=target_model,
            sandbox_root=str(sandbox_root),
            max_tool_rounds=4,
            max_context_tokens=target_num_ctx,
        )
        messages = [
            {
                "role": "system",
                "content": self._compose_engine_probe_system_prompt(
                    profile_text,
                    str(sandbox_root),
                    catalog,
                    policy,
                    target_model,
                ),
            },
            {"role": "user", "content": case.prompt},
        ]
        outcome = run_tool_agent_turn(
            config=config,
            tool_router=router,
            activity=activity,
            user_text=case.prompt,
            messages=messages,
            should_stop=lambda: False,
        )
        return {
            "content": "\n".join(outcome.total_content).strip(),
            "sandbox_root": str(sandbox_root),
            "metadata": {
                "model": outcome.result.get("model", target_model),
                "tokens_in": outcome.result.get("prompt_eval_count", 0),
                "tokens_out": outcome.result.get("eval_count", 0),
                "wall_ms": outcome.result.get("wall_ms", 0),
                "rounds": outcome.rounds,
                "filesystem_guardrail_triggered": outcome.filesystem_guardrail_triggered,
                "filesystem_guardrail_repaired": outcome.filesystem_guardrail_repaired,
                "filesystem_guardrail_failed": outcome.filesystem_guardrail_failed,
                "filesystem_evidence_summary": outcome.filesystem_evidence_summary,
            },
        }

    def _compose_direct_probe_system_prompt(self, profile_text: str) -> str:
        return (
            "You are being evaluated for instruction quality, grounding, and concise technical reasoning.\n\n"
            "[TRAINING PROFILE]\n"
            f"{profile_text.strip()}\n"
        )

    def _compose_engine_probe_system_prompt(
        self,
        profile_text: str,
        sandbox_root: str,
        catalog: ToolCatalog,
        policy: CommandPolicy,
        target_model: str,
    ) -> str:
        base = build_system_prompt(
            sandbox_root=sandbox_root,
            tools=catalog,
            command_policy=policy,
            model_name=target_model,
        )
        return f"{base}\n\n[TRAINING PROFILE]\n{profile_text.strip()}\n"

    def _run_tiny_judge(
        self,
        *,
        case: TrainingCase,
        response_text: str,
        judge_model: str,
        judge_num_ctx: int,
    ) -> dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": "You are a strict binary judge. Return JSON only with keys `pass` (boolean) and `rationale` (short string).",
            },
            {
                "role": "user",
                "content": f"{case.judge_prompt}\n\nPrompt:\n{case.prompt}\n\nResponse:\n{response_text}",
            },
        ]
        result = self._chat_runner(
            base_url="http://localhost:11434",
            model=judge_model,
            messages=messages,
            temperature=0.1,
            num_ctx=judge_num_ctx,
        )
        parsed = _parse_binary_judge_json(str(result.get("content", "")))
        return {
            "used": True,
            "passed": parsed["pass"],
            "rationale": parsed["rationale"],
            "score": 1.0 if parsed["pass"] else 0.0,
        }

    def _seed_case_workspace(self, sandbox_root: Path, case: TrainingCase) -> None:
        for relative_path, content in dict(case.metadata.get("workspace_files", {})).items():
            file_path = sandbox_root / str(relative_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(str(content), encoding="utf-8", newline="\n")

    def _resolve_training_context_limits(
        self,
        *,
        target_num_ctx: int | None,
        generator_num_ctx: int | None,
        judge_num_ctx: int | None,
    ) -> dict[str, int]:
        config = AppConfig.load(self.storage.project_root)
        config_limit = max(256, int(config.max_context_tokens or 8192))
        return {
            "target_num_ctx": min(config_limit, max(256, int(target_num_ctx or DEFAULT_TARGET_NUM_CTX))),
            "generator_num_ctx": min(config_limit, max(256, int(generator_num_ctx or DEFAULT_GENERATOR_NUM_CTX))),
            "judge_num_ctx": min(config_limit, max(256, int(judge_num_ctx or DEFAULT_JUDGE_NUM_CTX))),
        }

    def _select_winner(self, baseline_summary: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        baseline_score = float(baseline_summary.get("average_overall_score", 0.0))
        winning: dict[str, Any] | None = None
        for candidate in candidates:
            summary = candidate["score_summary"]
            if int(summary.get("critical_failure_count", 0)) > 0:
                continue
            candidate_score = float(summary.get("average_overall_score", 0.0))
            if candidate_score <= baseline_score:
                continue
            if winning is None or candidate_score > float(winning["score_summary"].get("average_overall_score", 0.0)):
                winning = candidate
        return winning

    def _build_delta_summary(self, baseline_summary: dict[str, Any], winner: dict[str, Any] | None) -> dict[str, Any]:
        if winner is None:
            return {"winner_selected": False, "delta_average_overall_score": 0.0}
        winner_summary = winner["score_summary"]
        return {
            "winner_selected": True,
            "winner_candidate_id": winner["candidate_id"],
            "delta_average_overall_score": round(
                float(winner_summary.get("average_overall_score", 0.0))
                - float(baseline_summary.get("average_overall_score", 0.0)),
                3,
            ),
            "baseline_average_overall_score": float(baseline_summary.get("average_overall_score", 0.0)),
            "winner_average_overall_score": float(winner_summary.get("average_overall_score", 0.0)),
        }


def _timestamp_suffix() -> str:
    return (
        utc_iso()
        .replace(":", "")
        .replace("-", "")
        .replace("+", "_plus_")
        .replace(".", "")
    )


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _resolve_case_path(case: TrainingCase, check: dict[str, Any], sandbox_root: str) -> Path:
    return (Path(sandbox_root) / str(check.get("path") or case.target_path).strip()).resolve()


def _normalize_rel_path(path: str) -> str:
    text = str(path).replace("\\", "/").strip()
    lower = text.lower()
    marker = "/.mindshard/"
    if marker in lower:
        return text[text.lower().index(marker) + 1 :].replace("\\", "/").lower()
    if ":/" in lower:
        parts = text.split("/", 1)
        if len(parts) == 2:
            text = parts[1]
    return text.lstrip("./").lower()


def _evaluate_deterministic_checks(
    *,
    case: TrainingCase,
    response_text: str,
    metadata: dict[str, Any],
    sandbox_root: str,
) -> dict[str, Any]:
    checks = list(case.deterministic_checks)
    if not checks:
        return {"score": 1.0, "findings": [], "critical_failure": False}

    evidence = metadata.get("filesystem_evidence_summary", {}) or {}
    findings: list[dict[str, Any]] = []
    passed = 0
    critical_failure = False
    for check in checks:
        check_type = str(check.get("type", "")).strip()
        required = bool(check.get("critical", False))
        result = False
        detail = ""
        if check_type == "requires_file_mutation":
            result = bool(evidence.get("file_mutation_called"))
            detail = "file_mutation_called"
        elif check_type == "requires_file_readback":
            result = bool(evidence.get("file_read_called"))
            detail = "file_read_called"
        elif check_type == "path_exists":
            target = _resolve_case_path(case, check, sandbox_root)
            result = target.exists()
            detail = str(target)
        elif check_type == "path_contains_text":
            target = _resolve_case_path(case, check, sandbox_root)
            expected = str(check.get("value", ""))
            result = expected in _read_text(target)
            detail = f"{target} contains {expected!r}"
        elif check_type == "must_include_text":
            expected = str(check.get("value", ""))
            result = expected.lower() in response_text.lower()
            detail = expected
        elif check_type == "must_not_include_text":
            expected = str(check.get("value", ""))
            result = expected.lower() not in response_text.lower()
            detail = expected
        elif check_type == "no_filesystem_guardrail_failure":
            result = not bool(metadata.get("filesystem_guardrail_failed"))
            detail = "filesystem_guardrail_failed"
        elif check_type == "named_path_matches_evidence":
            expected = _normalize_rel_path(str(check.get("path") or case.target_path))
            successful_paths = set()
            for key in ("successful_write_paths", "successful_replace_paths", "successful_read_paths", "successful_list_files"):
                successful_paths.update(_normalize_rel_path(item) for item in evidence.get(key, []))
            result = expected in successful_paths
            detail = expected

        if result:
            passed += 1
        elif required:
            critical_failure = True
        findings.append({"type": check_type, "passed": result, "critical": required, "detail": detail})

    return {"score": round(passed / len(checks), 3), "findings": findings, "critical_failure": critical_failure}


def _parse_binary_judge_json(text: str) -> dict[str, Any]:
    raw = text.strip()
    try:
        return _normalize_binary_judge(json.loads(raw))
    except Exception:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return _normalize_binary_judge(json.loads(match.group(0)))
            except Exception:
                pass
    lowered = raw.lower()
    return {"pass": '"pass": true' in lowered or lowered.startswith("pass"), "rationale": raw[:200]}


def _normalize_binary_judge(data: dict[str, Any]) -> dict[str, Any]:
    return {"pass": bool(data.get("pass", False)), "rationale": str(data.get("rationale", "")).strip()}
