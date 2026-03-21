from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.core.agent.benchmark_runner import BenchmarkSuiteResult


@dataclass(frozen=True)
class DiagnosticEvent:
    timestamp: str
    source: str
    kind: str
    message: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProbeResult:
    name: str
    status: str
    summary: str
    started_at: str
    ended_at: str
    duration_ms: float
    events: list[DiagnosticEvent] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    prompt_text: str = ""
    response_text: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status.lower() == "ok"


DiagnosticRunResult = ProbeResult | BenchmarkSuiteResult
