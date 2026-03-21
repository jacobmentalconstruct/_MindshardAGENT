"""Load human-editable benchmark suite definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path


@dataclass(frozen=True)
class BenchmarkCase:
    id: str
    label: str
    probe_type: str
    prompt: str


@dataclass(frozen=True)
class BenchmarkSuite:
    name: str
    label: str
    description: str
    cases: tuple[BenchmarkCase, ...] = field(default_factory=tuple)


def load_benchmark_suites(workspace_root: str | Path) -> dict[str, BenchmarkSuite]:
    root = Path(workspace_root).resolve()
    path = root / "_docs" / "benchmark_suite.json"
    if not path.exists():
        return {}

    raw = json.loads(path.read_text(encoding="utf-8"))
    suites: dict[str, BenchmarkSuite] = {}
    for name, data in raw.items():
        cases = tuple(
            BenchmarkCase(
                id=str(case.get("id", "")).strip(),
                label=str(case.get("label", case.get("id", ""))).strip(),
                probe_type=str(case.get("probe_type", "direct_model_probe")).strip(),
                prompt=str(case.get("prompt", "")).strip(),
            )
            for case in data.get("cases", [])
            if str(case.get("id", "")).strip() and str(case.get("prompt", "")).strip()
        )
        suites[name] = BenchmarkSuite(
            name=name,
            label=str(data.get("label", name)).strip(),
            description=str(data.get("description", "")).strip(),
            cases=cases,
        )
    return suites
