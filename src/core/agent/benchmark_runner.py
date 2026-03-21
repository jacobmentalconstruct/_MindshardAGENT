"""Run benchmark suites against a probe executor."""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Callable

from src.core.agent.benchmark_loader import BenchmarkCase, BenchmarkSuite
from src.core.utils.clock import utc_iso


@dataclass
class BenchmarkCaseResult:
    case_id: str
    label: str
    probe_type: str
    prompt: str
    result: Any


@dataclass
class BenchmarkSuiteResult:
    suite_name: str
    suite_label: str
    suite_description: str
    started_at: str
    ended_at: str
    duration_ms: float
    cases: list[BenchmarkCaseResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def run_benchmark_suite(
    suite: BenchmarkSuite,
    *,
    run_case: Callable[[BenchmarkCase], Any],
) -> BenchmarkSuiteResult:
    started_at = utc_iso()
    started = time.perf_counter()
    cases: list[BenchmarkCaseResult] = []
    for case in suite.cases:
        result = run_case(case)
        cases.append(
            BenchmarkCaseResult(
                case_id=case.id,
                label=case.label,
                probe_type=case.probe_type,
                prompt=case.prompt,
                result=result,
            )
        )

    duration_ms = (time.perf_counter() - started) * 1000.0
    scores = [float(case.result.metadata.get("overall_score", 0.0)) for case in cases]
    acc_scores = [float(case.result.metadata.get("accuracy_score", 0.0)) for case in cases]
    eff_scores = [float(case.result.metadata.get("efficiency_score", 0.0)) for case in cases]
    total_tokens = sum(int(case.result.metadata.get("total_tokens", 0)) for case in cases)
    total_rounds = sum(int(case.result.metadata.get("rounds", 0)) for case in cases)
    status_counts: dict[str, int] = {}
    for case in cases:
        status_counts[case.result.status] = status_counts.get(case.result.status, 0) + 1

    return BenchmarkSuiteResult(
        suite_name=suite.name,
        suite_label=suite.label,
        suite_description=suite.description,
        started_at=started_at,
        ended_at=utc_iso(),
        duration_ms=duration_ms,
        cases=cases,
        metadata={
            "case_count": len(cases),
            "average_overall_score": round(sum(scores) / len(scores), 3) if scores else 0.0,
            "average_accuracy_score": round(sum(acc_scores) / len(acc_scores), 3) if acc_scores else 0.0,
            "average_efficiency_score": round(sum(eff_scores) / len(eff_scores), 3) if eff_scores else 0.0,
            "total_tokens": total_tokens,
            "total_rounds": total_rounds,
            "status_counts": status_counts,
        },
    )
