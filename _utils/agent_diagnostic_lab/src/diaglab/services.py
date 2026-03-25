from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import threading
import time
from typing import Any

from src.core.agent.benchmark_loader import BenchmarkCase, load_benchmark_suites
from src.core.agent.benchmark_runner import BenchmarkSuiteResult, run_benchmark_suite
from src.core.agent.prompt_builder import PromptBuildResult, build_messages, build_system_prompt_bundle
from src.core.agent.prompt_tuning_store import PromptTuningStore, PromptVersionSnapshot
from src.core.config.app_config import AppConfig
from src.core.engine import Engine
from src.core.ollama.model_scanner import scan_models
from src.core.ollama.ollama_client import chat_stream
from src.core.runtime.activity_stream import ActivityEntry, ActivityStream
from src.core.runtime.event_bus import EventBus
from src.core.runtime.resource_monitor import poll_resources
from src.core.sandbox.command_policy import CommandPolicy
from src.core.sandbox.tool_catalog import ToolCatalog
from src.core.sandbox.tool_discovery import register_discovered_tools
from src.core.utils.clock import utc_iso

from diaglab.models import DiagnosticEvent, DiagnosticRunResult, ProbeResult
from diaglab.reporting import export_benchmark_suite, export_probe


class DiagnosticService:
    def __init__(self, toolbox_root: Path, utility_root: Path, output_root: Path):
        self.toolbox_root = Path(toolbox_root)
        self.utility_root = Path(utility_root)
        self.output_root = Path(output_root)
        self.prompt_tuning = PromptTuningStore(self.toolbox_root)
        self._active_stop: Callable[[], None] | None = None
        self._lock = threading.Lock()

    def scan_models(self, base_url: str) -> list[str]:
        return scan_models(base_url=base_url)

    def list_benchmark_suites(self) -> list[dict[str, str]]:
        suites = load_benchmark_suites(self.toolbox_root)
        return [
            {"name": suite.name, "label": suite.label, "description": suite.description}
            for suite in suites.values()
        ]

    def list_prompt_versions(self) -> list[dict[str, Any]]:
        return self.prompt_tuning.latest_versions(20)

    def list_benchmark_runs(self) -> list[dict[str, Any]]:
        return self.prompt_tuning.latest_benchmark_runs(20)

    def compare_benchmark_runs(self, left_run_id: int, right_run_id: int) -> dict[str, Any]:
        return self.prompt_tuning.compare_benchmark_runs(left_run_id, right_run_id)

    def diff_prompt_versions(self, left_version_id: int, right_version_id: int) -> dict[str, Any]:
        """Return a unified git diff between two prompt version snapshots."""
        return self.prompt_tuning.diff_prompt_versions(left_version_id, right_version_id)

    def restore_prompt_version(self, version_id: int) -> dict[str, Any]:
        return self.prompt_tuning.restore_prompt_version(version_id)

    def poll_resources(self):
        return poll_resources()

    def stop_active_probe(self) -> bool:
        with self._lock:
            stopper = self._active_stop
        if not stopper:
            return False
        stopper()
        return True

    def run_benchmark_suite(
        self,
        *,
        sandbox_root: str,
        model_name: str,
        base_url: str,
        user_text: str,
        docker_enabled: bool,
        temperature: float,
        num_ctx: int,
        benchmark_suite: str,
    ) -> BenchmarkSuiteResult:
        suites = load_benchmark_suites(self.toolbox_root)
        suite = suites.get(benchmark_suite)
        if not suite:
            raise ValueError(f"Unknown benchmark suite: {benchmark_suite}")

        def _run_case(case: BenchmarkCase) -> ProbeResult:
            payload = {
                "sandbox_root": sandbox_root,
                "model_name": model_name,
                "base_url": base_url,
                "user_text": case.prompt,
                "docker_enabled": docker_enabled,
                "temperature": temperature,
                "num_ctx": num_ctx,
            }
            if case.probe_type == "prompt_probe":
                return self.build_prompt_probe(**payload)
            if case.probe_type == "engine_turn_probe":
                return self.run_engine_probe(**payload)
            return self.run_direct_model_probe(**payload)

        suite_result = run_benchmark_suite(
            suite,
            run_case=_run_case,
        )
        latest_snapshot = None
        if suite_result.cases:
            version_id = suite_result.cases[0].result.metadata.get("prompt_version_id")
            if version_id:
                version = self.prompt_tuning.get_prompt_version(int(version_id))
                if version:
                    commit = str(version.get("git_commit", ""))
                else:
                    commit = ""
                latest_snapshot = PromptVersionSnapshot(
                    version_id=int(version_id),
                    git_commit=commit,
                    created_at=suite_result.started_at,
                )
        benchmark_run_id = self.prompt_tuning.record_benchmark_run(
            snapshot=latest_snapshot,
            suite_result=suite_result,
            model_name=model_name,
        )
        if benchmark_run_id is not None:
            suite_result.metadata["benchmark_run_id"] = benchmark_run_id
        return suite_result

    def build_prompt_probe(
        self,
        *,
        sandbox_root: str,
        model_name: str,
        base_url: str,
        user_text: str,
        docker_enabled: bool,
        temperature: float,
        num_ctx: int,
    ) -> ProbeResult:
        started = time.perf_counter()
        started_at = utc_iso()
        events = [self._event("service", "phase", "Starting prompt probe")]
        prompt_build = self._build_prompt_bundle(
            sandbox_root=sandbox_root,
            model_name=model_name,
            docker_enabled=docker_enabled,
            user_text=user_text,
        )
        events.append(self._event("prompt", "phase", "Prompt build complete", {
            "sections": len(prompt_build.sections),
            "source_fingerprint": prompt_build.source_fingerprint,
            "prompt_fingerprint": prompt_build.prompt_fingerprint,
        }))
        snapshot = self.prompt_tuning.snapshot_current_state(
            reason="diaglab prompt probe",
            sandbox_root=sandbox_root,
            prompt_build=prompt_build,
            notes="Prompt probe run",
        )
        duration_ms = (time.perf_counter() - started) * 1000.0
        result = ProbeResult(
            name="Prompt Probe",
            status="ok",
            summary=f"Built {len(prompt_build.sections)} prompt sections",
            started_at=started_at,
            ended_at=utc_iso(),
            duration_ms=duration_ms,
            events=events,
            metadata={
                "sandbox_root": sandbox_root,
                "model": model_name or "(none)",
                "ollama_base_url": base_url,
                "docker_enabled": docker_enabled,
                "temperature": temperature,
                "num_ctx": num_ctx,
                "sections": len(prompt_build.sections),
                "warnings": len(prompt_build.warnings),
                "source_fingerprint": prompt_build.source_fingerprint,
                "prompt_fingerprint": prompt_build.prompt_fingerprint,
            },
            prompt_text=prompt_build.prompt,
            warnings=list(prompt_build.warnings),
        )
        return self._record_probe(
            probe_type="prompt_probe",
            query_text=user_text,
            result=result,
            snapshot=snapshot,
        )

    def run_direct_model_probe(
        self,
        *,
        sandbox_root: str,
        model_name: str,
        base_url: str,
        user_text: str,
        docker_enabled: bool,
        temperature: float,
        num_ctx: int,
    ) -> ProbeResult:
        started = time.perf_counter()
        started_at = utc_iso()
        events = [self._event("service", "phase", "Starting direct model probe")]
        prompt_build = self._build_prompt_bundle(
            sandbox_root=sandbox_root,
            model_name=model_name,
            docker_enabled=docker_enabled,
            user_text=user_text,
        )
        messages = build_messages(prompt_build.prompt, [{"role": "user", "content": user_text}])
        tokens: list[str] = []
        first_token_latency_ms: float | None = None
        request_started = time.perf_counter()
        stop_flag = {"stop": False}

        def _stop() -> None:
            stop_flag["stop"] = True

        with self._lock:
            self._active_stop = _stop

        def _on_token(token: str) -> None:
            nonlocal first_token_latency_ms
            if first_token_latency_ms is None:
                first_token_latency_ms = (time.perf_counter() - request_started) * 1000.0
            tokens.append(token)

        try:
            result = chat_stream(
                base_url=base_url,
                model=model_name,
                messages=messages,
                on_token=_on_token,
                should_stop=lambda: stop_flag["stop"],
                temperature=temperature,
                num_ctx=num_ctx,
            )
        finally:
            with self._lock:
                self._active_stop = None

        response_text = result.get("content", "".join(tokens))
        events.append(self._event("model", "phase", "Direct model probe complete", {
            "tokens_out": result.get("eval_count", 0),
            "prompt_tokens": result.get("prompt_eval_count", 0),
            "wall_ms": result.get("wall_ms", 0.0),
            "first_token_latency_ms": round(first_token_latency_ms or 0.0, 1),
        }))
        snapshot = self.prompt_tuning.snapshot_current_state(
            reason="diaglab direct model probe",
            sandbox_root=sandbox_root,
            prompt_build=prompt_build,
            notes="Direct model probe run",
        )
        duration_ms = (time.perf_counter() - started) * 1000.0
        probe_result = ProbeResult(
            name="Direct Model Probe",
            status="ok" if not result.get("stopped") else "stopped",
            summary="Streamed a model response without the full engine loop",
            started_at=started_at,
            ended_at=utc_iso(),
            duration_ms=duration_ms,
            events=events,
            metadata={
                "sandbox_root": sandbox_root,
                "model": model_name,
                "ollama_base_url": base_url,
                "docker_enabled": docker_enabled,
                "temperature": temperature,
                "num_ctx": num_ctx,
                "sections": len(prompt_build.sections),
                "source_fingerprint": prompt_build.source_fingerprint,
                "prompt_fingerprint": prompt_build.prompt_fingerprint,
                "first_token_latency_ms": round(first_token_latency_ms or 0.0, 1),
                "wall_ms": result.get("wall_ms", 0.0),
                "tokens_out": result.get("eval_count", 0),
                "tokens_in": result.get("prompt_eval_count", 0),
                "done_reason": result.get("done_reason", ""),
            },
            prompt_text=prompt_build.prompt,
            response_text=response_text,
            warnings=list(prompt_build.warnings),
        )
        return self._record_probe(
            probe_type="direct_model_probe",
            query_text=user_text,
            result=probe_result,
            snapshot=snapshot,
        )

    def run_engine_probe(
        self,
        *,
        sandbox_root: str,
        model_name: str,
        base_url: str,
        user_text: str,
        docker_enabled: bool,
        temperature: float,
        num_ctx: int,
    ) -> ProbeResult:
        started = time.perf_counter()
        started_at = utc_iso()
        activity = ActivityStream()
        bus = EventBus()
        captured_events: list[DiagnosticEvent] = []
        token_chunks: list[str] = []
        first_token_latency_ms: float | None = None
        request_started = time.perf_counter()

        def _capture(entry: ActivityEntry) -> None:
            captured_events.append(self._activity_to_event(entry))

        activity.subscribe(_capture)
        probe_config = self._build_config(
            sandbox_root=sandbox_root,
            model_name=model_name,
            base_url=base_url,
            docker_enabled=docker_enabled,
            temperature=temperature,
            num_ctx=num_ctx,
        )
        # Snapshot the model role assignments before the probe runs
        model_roles_snapshot = {
            "chat_model": probe_config.selected_model,
            "planner_model": probe_config.planner_model,
            "fast_probe_model": probe_config.fast_probe_model,
            "coding_model": probe_config.coding_model,
            "review_model": probe_config.review_model,
        }
        engine = Engine(
            config=probe_config,
            activity=activity,
            bus=bus,
        )
        activity.info("diagnostic_lab", "Starting engine probe")
        engine.start()
        engine.set_sandbox(sandbox_root)

        finished = threading.Event()
        completion: dict[str, Any] = {}
        error_box: dict[str, str] = {}

        def _stop() -> None:
            engine.request_stop()

        with self._lock:
            self._active_stop = _stop

        def _on_token(token: str) -> None:
            nonlocal first_token_latency_ms
            if first_token_latency_ms is None:
                first_token_latency_ms = (time.perf_counter() - request_started) * 1000.0
            token_chunks.append(token)

        def _on_complete(result: dict[str, Any]) -> None:
            completion.update(result)
            finished.set()

        def _on_error(message: str) -> None:
            error_box["message"] = message
            finished.set()

        try:
            engine.submit_prompt(
                user_text,
                on_token=_on_token,
                on_complete=_on_complete,
                on_error=_on_error,
            )
            finished.wait(timeout=600)
        finally:
            with self._lock:
                self._active_stop = None
            engine.stop()

        duration_ms = (time.perf_counter() - started) * 1000.0
        prompt_build = completion.get("prompt_build")
        snapshot = self.prompt_tuning.snapshot_current_state(
            reason="diaglab engine probe",
            sandbox_root=sandbox_root,
            prompt_build=prompt_build,
            notes="Engine turn probe run",
        )

        if not finished.is_set():
            engine.request_stop()
            captured_events.append(self._event("diagnostic_lab", "warn", "Engine probe timed out after 600s"))
            probe_result = ProbeResult(
                name="Engine Turn Probe",
                status="timeout",
                summary="Engine probe timed out waiting for completion",
                started_at=started_at,
                ended_at=utc_iso(),
                duration_ms=duration_ms,
                events=captured_events,
                metadata={
                    "sandbox_root": sandbox_root,
                    "model": model_name,
                    "timed_out": True,
                    "first_token_latency_ms": round(first_token_latency_ms or 0.0, 1),
                },
                response_text="".join(token_chunks),
            )
            return self._record_probe(
                probe_type="engine_turn_probe",
                query_text=user_text,
                result=probe_result,
                snapshot=snapshot,
            )
        if error_box:
            probe_result = ProbeResult(
                name="Engine Turn Probe",
                status="error",
                summary=error_box["message"],
                started_at=started_at,
                ended_at=utc_iso(),
                duration_ms=duration_ms,
                events=captured_events,
                metadata={
                    "sandbox_root": sandbox_root,
                    "model": model_name,
                    "error": error_box["message"],
                    "first_token_latency_ms": round(first_token_latency_ms or 0.0, 1),
                },
                response_text="".join(token_chunks),
            )
            return self._record_probe(
                probe_type="engine_turn_probe",
                query_text=user_text,
                result=probe_result,
                snapshot=snapshot,
            )

        result_meta = completion.get("metadata", {})
        probe_result = ProbeResult(
            name="Engine Turn Probe",
            status="ok" if not result_meta.get("stopped") else "stopped",
            summary=(completion.get("content", "").splitlines() or ["Engine turn complete"])[0][:220],
            started_at=started_at,
            ended_at=utc_iso(),
            duration_ms=duration_ms,
            events=captured_events,
            metadata={
                "sandbox_root": sandbox_root,
                "model": model_name,
                "docker_enabled": docker_enabled,
                "temperature": temperature,
                "num_ctx": num_ctx,
                "first_token_latency_ms": round(first_token_latency_ms or 0.0, 1),
                # Model role assignments active during this probe
                **model_roles_snapshot,
                # Full turn metadata from TurnPipeline (loop_mode, budget, stm, etc.)
                **result_meta,
            },
            prompt_text=prompt_build.prompt if prompt_build else "",
            response_text=completion.get("content", "".join(token_chunks)),
            warnings=list(prompt_build.warnings) if prompt_build else [],
        )
        return self._record_probe(
            probe_type="engine_turn_probe",
            query_text=user_text,
            result=probe_result,
            snapshot=snapshot,
        )

    def export_result(self, result: DiagnosticRunResult) -> Path:
        self.output_root.mkdir(parents=True, exist_ok=True)
        if isinstance(result, BenchmarkSuiteResult):
            target = export_benchmark_suite(self.output_root, result)
        else:
            target = export_probe(self.output_root, result)
            probe_run_id = result.metadata.get("probe_run_id")
            if probe_run_id:
                self.prompt_tuning.attach_probe_export(int(probe_run_id), target)
        return target

    def _build_prompt_bundle(
        self,
        *,
        sandbox_root: str,
        model_name: str,
        docker_enabled: bool,
        user_text: str,
    ) -> PromptBuildResult:
        tool_catalog = ToolCatalog()
        register_discovered_tools(tool_catalog, sandbox_root)
        command_policy = None if docker_enabled else CommandPolicy(mode="allowlist")
        return build_system_prompt_bundle(
            sandbox_root=sandbox_root,
            tools=tool_catalog,
            command_policy=command_policy,
            session_title="Diagnostic Lab",
            model_name=model_name,
            docker_mode=docker_enabled,
            active_project="",
        )

    def _build_config(
        self,
        *,
        sandbox_root: str,
        model_name: str,
        base_url: str,
        docker_enabled: bool,
        temperature: float,
        num_ctx: int,
    ) -> AppConfig:
        return AppConfig(
            sandbox_root=sandbox_root,
            toolbox_root=str(self.toolbox_root),
            ollama_base_url=base_url,
            selected_model=model_name,
            temperature=temperature,
            max_context_tokens=num_ctx,
            docker_enabled=docker_enabled,
            gui_launch_policy="deny",
        )

    def _activity_to_event(self, entry: ActivityEntry) -> DiagnosticEvent:
        return DiagnosticEvent(
            timestamp=entry.timestamp,
            source=entry.source,
            kind=entry.level.lower(),
            message=entry.message,
        )

    def _event(
        self,
        source: str,
        kind: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> DiagnosticEvent:
        return DiagnosticEvent(
            timestamp=utc_iso(),
            source=source,
            kind=kind,
            message=message,
            payload=payload or {},
        )

    def _record_probe(
        self,
        *,
        probe_type: str,
        query_text: str,
        result: ProbeResult,
        snapshot: PromptVersionSnapshot | None,
    ) -> ProbeResult:
        run_id, scores = self.prompt_tuning.record_probe_run(
            snapshot=snapshot,
            probe_name=result.name,
            probe_type=probe_type,
            model_name=str(result.metadata.get("model", "")),
            query_text=query_text,
            status=result.status,
            summary=result.summary,
            duration_ms=result.duration_ms,
            metadata=result.metadata,
            response_text=result.response_text,
            events=result.events,
            warnings=result.warnings,
        )
        if snapshot:
            result.metadata["prompt_version_id"] = snapshot.version_id
            result.metadata["prompt_version_commit"] = snapshot.git_commit[:12]
        if run_id is not None:
            result.metadata["probe_run_id"] = run_id
        result.metadata["tokens_in_num"] = scores.tokens_in
        result.metadata["tokens_out_num"] = scores.tokens_out
        result.metadata["total_tokens"] = scores.total_tokens
        result.metadata["rounds"] = scores.rounds or int(result.metadata.get("rounds", 0) or 0)
        result.metadata["accuracy_score"] = scores.accuracy_score
        result.metadata["efficiency_score"] = scores.efficiency_score
        result.metadata["overall_score"] = scores.overall_score
        result.metadata["score"] = scores.overall_score
        return result
