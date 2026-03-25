from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.core.agent.benchmark_runner import BenchmarkSuiteResult


# Schema contract for DiagnosticEvent — see event_schema.json for the full
# JSON Schema. Import EVENT_SCHEMA_VERSION in other apps that consume probe exports.
EVENT_SCHEMA_VERSION = "1.0"
_SCHEMA_PATH = Path(__file__).with_name("event_schema.json")


def load_event_schema() -> dict[str, Any]:
    """Load the canonical DiagnosticEvent JSON Schema from disk.

    Use this to validate probe export files in any app that consumes them.
    Returns the raw schema dict, compatible with jsonschema.validate().
    """
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class DiagnosticEvent:
    """Structured event emitted during a probe run.

    Schema contract: see event_schema.json (version 1.0).
    kind must be one of: info | warn | error | model | tool | phase | debug
    """
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
