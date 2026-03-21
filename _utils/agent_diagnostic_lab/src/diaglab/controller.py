from __future__ import annotations

import queue
import threading
import traceback
import tkinter as tk

from src.core.agent.benchmark_runner import BenchmarkSuiteResult

from diaglab.models import DiagnosticRunResult
from diaglab.services import DiagnosticService
from diaglab.view import DiagnosticView


class DiagnosticController:
    def __init__(self, *, root: tk.Tk, view: DiagnosticView, service: DiagnosticService):
        self.root = root
        self.view = view
        self.service = service
        self._queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._last_result: DiagnosticRunResult | None = None

    def start(self) -> None:
        self.view.bind_actions(
            refresh_models=self.refresh_models,
            refresh_benchmarks=self.refresh_benchmarks,
            refresh_history=self.refresh_history,
            refresh_resources=self.refresh_resources,
            run_prompt_probe=self.run_prompt_probe,
            run_direct_probe=self.run_direct_probe,
            run_engine_probe=self.run_engine_probe,
            run_benchmark_suite=self.run_benchmark_suite,
            restore_prompt_version=self.restore_prompt_version,
            compare_benchmark_runs=self.compare_benchmark_runs,
            stop_active_probe=self.stop_active_probe,
            export_last_result=self.export_last_result,
        )
        self.view.set_status("Ready")
        self.refresh_models()
        self.refresh_benchmarks()
        self.refresh_history()
        self.refresh_resources()
        self.root.after(150, self._drain_queue)
        self.root.after(5000, self._poll_resources)

    def refresh_models(self) -> None:
        inputs = self.view.get_inputs()
        self.view.set_status("Scanning models...")
        self._run_async("models", lambda: self.service.scan_models(inputs["base_url"]))

    def refresh_benchmarks(self) -> None:
        self._run_async("benchmark_suites", self.service.list_benchmark_suites)

    def refresh_history(self) -> None:
        self.view.set_status("Loading prompt history...")
        self._run_async(
            "history",
            lambda: {
                "versions": self.service.list_prompt_versions(),
                "benchmark_runs": self.service.list_benchmark_runs(),
            },
        )

    def refresh_resources(self) -> None:
        self._run_async("resources", self.service.poll_resources)

    def run_prompt_probe(self) -> None:
        inputs = self._probe_inputs()
        self.view.set_busy(True, "Building prompt...")
        self._run_async("probe", lambda: self.service.build_prompt_probe(**inputs))

    def run_direct_probe(self) -> None:
        inputs = self._probe_inputs()
        self.view.set_busy(True, "Running direct model probe...")
        self._run_async("probe", lambda: self.service.run_direct_model_probe(**inputs))

    def run_engine_probe(self) -> None:
        inputs = self._probe_inputs()
        self.view.set_busy(True, "Running engine probe...")
        self._run_async("probe", lambda: self.service.run_engine_probe(**inputs))

    def run_benchmark_suite(self) -> None:
        inputs = self.view.get_inputs()
        self.view.set_busy(True, "Running benchmark suite...")
        self._run_async("benchmark", lambda: self.service.run_benchmark_suite(**inputs))

    def restore_prompt_version(self) -> None:
        history_inputs = self.view.get_history_inputs()
        version_id = history_inputs["version_id"]
        if version_id <= 0:
            self.view.set_status("Enter a prompt version ID to restore")
            return
        if not self.view.confirm_restore_version(version_id):
            self.view.set_status("Restore cancelled")
            return
        self.view.set_busy(True, f"Restoring prompt version {version_id}...")
        self._run_async("history_restore", lambda: self.service.restore_prompt_version(version_id))

    def compare_benchmark_runs(self) -> None:
        history_inputs = self.view.get_history_inputs()
        left_run_id = history_inputs["left_run_id"]
        right_run_id = history_inputs["right_run_id"]
        if left_run_id <= 0 or right_run_id <= 0:
            self.view.set_status("Enter two benchmark run IDs to compare")
            return
        self.view.set_busy(True, f"Comparing benchmark runs {left_run_id} and {right_run_id}...")
        self._run_async(
            "history_compare",
            lambda: self.service.compare_benchmark_runs(left_run_id, right_run_id),
        )

    def stop_active_probe(self) -> None:
        stopped = self.service.stop_active_probe()
        self.view.set_status("Stop requested" if stopped else "No active probe to stop")

    def export_last_result(self) -> None:
        if not self._last_result:
            self.view.set_status("No probe result to export")
            return
        self.view.set_status("Exporting report...")
        self._run_async("export", lambda: self.service.export_result(self._last_result))

    def _run_async(self, kind: str, fn) -> None:
        def _worker():
            try:
                result = fn()
                self._queue.put((kind, result))
            except Exception as exc:
                detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
                self._queue.put(("error", detail))

        threading.Thread(target=_worker, daemon=True, name=f"diaglab-{kind}").start()

    def _drain_queue(self) -> None:
        while True:
            try:
                kind, payload = self._queue.get_nowait()
            except queue.Empty:
                break
            if kind == "models":
                models = list(payload)
                self.view.set_models(models)
                self.view.set_status(f"Found {len(models)} model(s)")
            elif kind == "benchmark_suites":
                self.view.set_benchmark_suites(list(payload))
                self.view.set_status("Benchmark suites refreshed")
            elif kind == "history":
                self.view.set_history_snapshot(payload["versions"], payload["benchmark_runs"])
                self.view.set_status(
                    f"Loaded {len(payload['versions'])} versions and {len(payload['benchmark_runs'])} benchmark runs"
                )
            elif kind == "resources":
                self.view.set_resources(payload)
            elif kind == "probe":
                self._last_result = payload
                self.view.set_busy(False, f"{payload.name} complete")
                self.view.show_probe_result(payload)
            elif kind == "benchmark":
                self._last_result = payload
                self.view.set_busy(False, f"{payload.suite_label} complete")
                self.view.show_benchmark_result(payload)
                self.refresh_history()
            elif kind == "history_restore":
                self.view.set_busy(False, f"Restored prompt version {payload['version_id']}")
                self.view.show_history_message(self._format_restore_result(payload))
                self.refresh_history()
            elif kind == "history_compare":
                self.view.set_busy(False, "Benchmark comparison ready")
                self.view.show_history_message(self._format_history_comparison(payload))
            elif kind == "export":
                self.view.set_status(f"Report exported to {payload}")
            elif kind == "error":
                self.view.set_busy(False, "Probe failed")
                self.view.show_error(str(payload))
        self.root.after(150, self._drain_queue)

    def _poll_resources(self) -> None:
        self.refresh_resources()
        self.root.after(5000, self._poll_resources)

    def _probe_inputs(self) -> dict[str, object]:
        inputs = self.view.get_inputs()
        inputs.pop("benchmark_suite", None)
        return inputs

    def _format_restore_result(self, payload: dict[str, object]) -> str:
        restored_files = list(payload.get("restored_files", []))
        lines = [
            f"Restored prompt version {payload.get('version_id')} ({str(payload.get('git_commit', ''))[:12]})",
            "",
            "Files restored:",
        ]
        if restored_files:
            lines.extend(f"- {path}" for path in restored_files)
        else:
            lines.append("- (no files restored)")
        return "\n".join(lines)

    def _format_history_comparison(self, payload: dict[str, object]) -> str:
        left = payload["left"]
        right = payload["right"]
        lines = [
            f"Benchmark Run Comparison: b{left['id']} -> b{right['id']}",
            "",
            f"Left:  {left.get('suite_name', '')} | score={left.get('average_overall_score', 0.0)} | tokens={left.get('total_tokens', 0)} | rounds={left.get('total_rounds', 0)}",
            f"Right: {right.get('suite_name', '')} | score={right.get('average_overall_score', 0.0)} | tokens={right.get('total_tokens', 0)} | rounds={right.get('total_rounds', 0)}",
            "",
            "Aggregate deltas:",
            f"- overall score: {payload.get('delta_average_overall_score', 0.0):+.3f}",
            f"- accuracy score: {payload.get('delta_average_accuracy_score', 0.0):+.3f}",
            f"- efficiency score: {payload.get('delta_average_efficiency_score', 0.0):+.3f}",
            f"- total tokens: {int(payload.get('delta_total_tokens', 0)):+d}",
            f"- total rounds: {int(payload.get('delta_total_rounds', 0)):+d}",
            "",
            "Case deltas:",
        ]
        case_deltas = payload.get("case_deltas", [])
        if case_deltas:
            for case in case_deltas:
                lines.append(
                    f"- {case.get('case_label', case.get('case_id', 'case'))}: "
                    f"score {float(case.get('delta_score', 0.0)):+.3f}, "
                    f"tokens {int(case.get('delta_tokens', 0)):+d}, "
                    f"rounds {int(case.get('delta_rounds', 0)):+d}, "
                    f"status {case.get('left_status', '')}->{case.get('right_status', '')}"
                )
        else:
            lines.append("- (no case deltas)")
        return "\n".join(lines)
