"""Scoring and findings for prompt and benchmark probes."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True)
class ProbeFinding:
    key: str
    value: str
    severity: str
    details: str


@dataclass(frozen=True)
class ProbeScores:
    tokens_in: int
    tokens_out: int
    total_tokens: int
    rounds: int
    duration_ms: float
    first_token_latency_ms: float
    accuracy_score: float
    efficiency_score: float
    overall_score: float


def parse_intish(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    match = re.search(r"-?\d+", text.replace(",", ""))
    return int(match.group(0)) if match else 0


def extract_probe_findings(
    *,
    response_text: str,
    events: list[Any],
    metadata: dict[str, Any],
) -> list[ProbeFinding]:
    findings: list[ProbeFinding] = []
    unknown_tool_count = 0
    blocked_attempts = 0
    for event in events:
        message = getattr(event, "message", "")
        if "Unknown tool:" in message:
            unknown_tool_count += 1
        if "blocked" in message.lower():
            blocked_attempts += 1
    if unknown_tool_count:
        findings.append(
            ProbeFinding(
                "unknown_tool_calls",
                str(unknown_tool_count),
                "high",
                "Probe emitted tool names not present in the tool catalog.",
            )
        )
    if blocked_attempts:
        findings.append(
            ProbeFinding(
                "blocked_attempts",
                str(blocked_attempts),
                "medium",
                "Probe hit blocked commands or policy rejections.",
            )
        )
    if "path:project/" in response_text or "project/src" in response_text:
        findings.append(
            ProbeFinding(
                "invented_project_prefix",
                "1",
                "medium",
                "Response used a fake 'project/' prefix instead of root-relative paths.",
            )
        )
    if "pip install tkinter" in response_text.lower():
        findings.append(
            ProbeFinding(
                "pip_install_tkinter",
                "1",
                "high",
                "Response suggested installing tkinter with pip.",
            )
        )
    rounds = parse_intish(metadata.get("rounds"))
    if rounds > 6:
        findings.append(
            ProbeFinding(
                "high_round_count",
                str(rounds),
                "medium",
                "Probe required more than 6 rounds, suggesting inefficient exploration.",
            )
        )
    if response_text.lstrip().startswith("I'll ") and "TOOL_CALLS:" in response_text:
        findings.append(
            ProbeFinding(
                "narrated_tool_preface",
                "1",
                "low",
                "Response still narrated intent before issuing obvious tool calls.",
            )
        )
    return findings


def compute_probe_scores(
    *,
    metadata: dict[str, Any],
    findings: list[ProbeFinding],
) -> ProbeScores:
    tokens_in = parse_intish(metadata.get("tokens_in"))
    tokens_out = parse_intish(metadata.get("tokens_out"))
    total_tokens = tokens_in + tokens_out
    rounds = parse_intish(metadata.get("rounds"))
    duration_ms = float(metadata.get("wall_ms") or metadata.get("time_ms") or metadata.get("duration_ms") or 0.0)
    first_token_latency_ms = float(metadata.get("first_token_latency_ms") or 0.0)

    accuracy = 1.0
    penalties = {
        "unknown_tool_calls": 0.35,
        "invented_project_prefix": 0.20,
        "pip_install_tkinter": 0.25,
        "blocked_attempts": 0.10,
        "high_round_count": 0.15,
        "narrated_tool_preface": 0.05,
    }
    for finding in findings:
        accuracy -= penalties.get(finding.key, 0.0)
    accuracy = max(0.0, round(accuracy, 3))

    token_penalty = min(total_tokens / 12000.0, 0.45)
    round_penalty = min(rounds / 20.0, 0.20)
    duration_penalty = min(duration_ms / 180000.0, 0.20)
    latency_penalty = min(first_token_latency_ms / 30000.0, 0.10)
    efficiency = max(0.0, round(1.0 - token_penalty - round_penalty - duration_penalty - latency_penalty, 3))
    overall = max(0.0, round((accuracy * 0.7) + (efficiency * 0.3), 3))

    return ProbeScores(
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        total_tokens=total_tokens,
        rounds=rounds,
        duration_ms=duration_ms,
        first_token_latency_ms=first_token_latency_ms,
        accuracy_score=accuracy,
        efficiency_score=efficiency,
        overall_score=overall,
    )
