from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import re

from src.core.agent.benchmark_runner import BenchmarkSuiteResult
from diaglab.models import ProbeResult


def export_probe(output_root: Path, result: ProbeResult) -> Path:
    stamp = result.started_at.replace(":", "").replace("-", "").replace("T", "_").replace("Z", "")
    slug = _slugify(result.name)
    target = output_root / f"{stamp}_{slug}"
    target.mkdir(parents=True, exist_ok=True)

    (target / "report.json").write_text(
        json.dumps(asdict(result), indent=2),
        encoding="utf-8",
    )
    (target / "report.md").write_text(_render_markdown(result), encoding="utf-8")
    if result.prompt_text.strip():
        (target / "prompt.txt").write_text(result.prompt_text, encoding="utf-8")
    if result.response_text.strip():
        (target / "response.txt").write_text(result.response_text, encoding="utf-8")
    if result.events:
        lines = [json.dumps(asdict(event)) for event in result.events]
        (target / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def export_benchmark_suite(output_root: Path, result: BenchmarkSuiteResult) -> Path:
    stamp = result.started_at.replace(":", "").replace("-", "").replace("T", "_").replace("Z", "")
    slug = _slugify(result.suite_name)
    target = output_root / f"{stamp}_{slug}"
    target.mkdir(parents=True, exist_ok=True)
    (target / "suite.json").write_text(
        json.dumps(asdict(result), indent=2),
        encoding="utf-8",
    )
    (target / "suite.md").write_text(_render_benchmark_markdown(result), encoding="utf-8")
    return target


def _render_markdown(result: ProbeResult) -> str:
    lines = [
        f"# {result.name}",
        "",
        f"- Status: {result.status}",
        f"- Summary: {result.summary}",
        f"- Started: {result.started_at}",
        f"- Ended: {result.ended_at}",
        f"- Duration: {result.duration_ms:.1f} ms",
        f"- Event count: {len(result.events)}",
        "",
        "## Metadata",
        "",
    ]
    for key, value in sorted(result.metadata.items()):
        lines.append(f"- {key}: {value}")
    if result.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend([f"- {warning}" for warning in result.warnings])
    if result.prompt_text.strip():
        lines.extend(["", "## Prompt", "", "```text", result.prompt_text.rstrip(), "```"])
    if result.response_text.strip():
        lines.extend(["", "## Response", "", "```text", result.response_text.rstrip(), "```"])
    return "\n".join(lines) + "\n"


def _slugify(text: str) -> str:
    lowered = text.strip().lower()
    cleaned = re.sub(r"[^a-z0-9]+", "_", lowered)
    return cleaned.strip("_") or "probe"


def _render_benchmark_markdown(result: BenchmarkSuiteResult) -> str:
    lines = [
        f"# {result.suite_label}",
        "",
        f"- Suite: {result.suite_name}",
        f"- Description: {result.suite_description}",
        f"- Started: {result.started_at}",
        f"- Ended: {result.ended_at}",
        f"- Duration: {result.duration_ms:.1f} ms",
        "",
        "## Aggregate Metrics",
        "",
    ]
    for key, value in sorted(result.metadata.items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Cases", ""])
    for case in result.cases:
        probe = case.result
        lines.append(f"### {case.label}")
        lines.append(f"- Probe type: {case.probe_type}")
        lines.append(f"- Status: {probe.status}")
        lines.append(f"- Overall score: {probe.metadata.get('overall_score', 0.0)}")
        lines.append(f"- Accuracy score: {probe.metadata.get('accuracy_score', 0.0)}")
        lines.append(f"- Efficiency score: {probe.metadata.get('efficiency_score', 0.0)}")
        lines.append(f"- Tokens: {probe.metadata.get('total_tokens', 0)}")
        lines.append(f"- Rounds: {probe.metadata.get('rounds', 0)}")
        lines.append(f"- Summary: {probe.summary}")
        lines.append("")
    return "\n".join(lines) + "\n"
