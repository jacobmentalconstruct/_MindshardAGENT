"""
FILE: validate_model_slot.py
ROLE: Validate a candidate model against a role's eval fixture.
WHAT IT DOES: Loads the role-specific test cases from jobs/role_evals/<role>_slot.json,
runs the candidate model through ollama_prompt_lab, and returns a structured pass/fail report.
HOW TO USE:
  - Metadata: python _ollama-prompt-lab/tools/validate_model_slot.py metadata
  - Run: python _ollama-prompt-lab/tools/validate_model_slot.py run --input-json '{"model":"qwen3.5:0.5b","role":"fast_probe"}'
INPUT OBJECT:
  - model: string (required) — candidate Ollama model name
  - role: string (required) — one of: fast_probe, planner, primary_chat, coding, review
  - repeats: int (optional, default 2) — how many times to repeat each case
  - pull_missing: bool (optional, default false) — pull model if not installed
  - timeout_seconds: int (optional, default 90) — per-inference timeout
  - compare_model: string (optional) — run the same eval against this model for comparison
NOTES:
  - Fixture files live in jobs/role_evals/<role>_slot.json
  - The candidate model is injected into the fixture's "models" list
  - Returns pass rate, timing, and promote/reject recommendation
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result, tool_error
from tools.ollama_prompt_lab import run as run_eval


FILE_METADATA = {
    "tool_name": "validate_model_slot",
    "version": "1.0.0",
    "entrypoint": "tools/validate_model_slot.py",
    "category": "evaluation",
    "summary": "Validate a candidate Ollama model against a role's eval fixture before promoting it to a slot.",
    "mcp_name": "validate_model_slot",
    "input_schema": {
        "type": "object",
        "properties": {
            "model": {"type": "string", "description": "Candidate Ollama model name to test."},
            "role": {
                "type": "string",
                "enum": ["fast_probe", "planner", "primary_chat", "coding", "review"],
                "description": "The role slot to validate against.",
            },
            "repeats": {"type": "integer", "default": 2, "description": "Repeat count per case."},
            "pull_missing": {"type": "boolean", "default": False},
            "timeout_seconds": {"type": "integer", "default": 90},
            "compare_model": {
                "type": "string",
                "description": "Optional model to compare against (runs same eval).",
            },
        },
        "required": ["model", "role"],
        "additionalProperties": False,
    },
}

VALID_ROLES = {"fast_probe", "planner", "primary_chat", "coding", "review"}


def _fixture_path(role: str) -> Path:
    return Path(__file__).resolve().parents[1] / "jobs" / "role_evals" / f"{role}_slot.json"


def _load_fixture(role: str) -> dict[str, Any]:
    path = _fixture_path(role)
    if not path.exists():
        raise FileNotFoundError(f"No eval fixture for role '{role}' at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _run_candidate(fixture: dict[str, Any], model: str, repeats: int,
                   pull_missing: bool, timeout_seconds: int) -> dict[str, Any]:
    """Run the eval for a single candidate model."""
    eval_input = dict(fixture)
    eval_input["models"] = [model]
    eval_input["repeats"] = repeats
    eval_input["pull_missing"] = pull_missing
    eval_input["timeout_seconds"] = timeout_seconds
    return run_eval(eval_input)


def _extract_scores(eval_result: dict[str, Any]) -> dict[str, Any]:
    """Pull key metrics from an ollama_prompt_lab result."""
    inner = eval_result.get("result", eval_result)
    summary = inner.get("summary", {})
    leaderboard = summary.get("leaderboard", [])
    aggregate = summary.get("aggregate", {})

    total_runs = summary.get("run_count", 0)
    by_model = aggregate.get("by_model", {})

    # Flatten first model entry
    model_stats = {}
    if by_model:
        first_key = next(iter(by_model))
        model_stats = by_model[first_key]

    pass_rate = model_stats.get("deterministic_pass_rate_avg", 0.0)
    judge_avg = model_stats.get("judge_score_avg")
    success_runs = model_stats.get("success_runs", 0)

    # Timing from sample runs
    sample_runs = inner.get("sample_runs", [])
    durations = [r.get("duration_seconds", 0) for r in sample_runs if r.get("duration_seconds")]
    avg_duration = round(sum(durations) / len(durations), 3) if durations else None

    return {
        "total_runs": total_runs,
        "success_runs": success_runs,
        "deterministic_pass_rate": pass_rate,
        "judge_score_avg": judge_avg,
        "avg_duration_seconds": avg_duration,
        "leaderboard": leaderboard,
    }


def _recommend(scores: dict[str, Any]) -> str:
    """Simple recommendation based on pass rate."""
    rate = scores.get("deterministic_pass_rate", 0.0)
    if rate is None:
        return "unknown"
    if rate >= 0.9:
        return "promote"
    if rate >= 0.6:
        return "marginal"
    return "reject"


def run(arguments: dict[str, Any]) -> dict[str, Any]:
    model = arguments.get("model", "").strip()
    role = arguments.get("role", "").strip()
    repeats = max(1, int(arguments.get("repeats", 2)))
    pull_missing = bool(arguments.get("pull_missing", False))
    timeout_seconds = int(arguments.get("timeout_seconds", 90))
    compare_model = (arguments.get("compare_model") or "").strip()

    if not model:
        return tool_error(FILE_METADATA["tool_name"], arguments, "model is required")
    if role not in VALID_ROLES:
        return tool_error(FILE_METADATA["tool_name"], arguments,
                          f"Invalid role '{role}'. Valid: {sorted(VALID_ROLES)}")

    fixture = _load_fixture(role)

    t0 = time.perf_counter()
    candidate_result = _run_candidate(fixture, model, repeats, pull_missing, timeout_seconds)
    candidate_wall = round(time.perf_counter() - t0, 3)

    candidate_scores = _extract_scores(candidate_result)
    candidate_scores["wall_seconds"] = candidate_wall
    recommendation = _recommend(candidate_scores)

    result: dict[str, Any] = {
        "model": model,
        "role": role,
        "recommendation": recommendation,
        "candidate": candidate_scores,
    }

    if compare_model:
        t1 = time.perf_counter()
        compare_result = _run_candidate(fixture, compare_model, repeats, pull_missing, timeout_seconds)
        compare_wall = round(time.perf_counter() - t1, 3)
        compare_scores = _extract_scores(compare_result)
        compare_scores["wall_seconds"] = compare_wall
        result["compare_model"] = compare_model
        result["compare"] = compare_scores
        result["compare_recommendation"] = _recommend(compare_scores)

        # Delta
        c_rate = candidate_scores.get("deterministic_pass_rate", 0) or 0
        b_rate = compare_scores.get("deterministic_pass_rate", 0) or 0
        result["pass_rate_delta"] = round(c_rate - b_rate, 3)
        c_dur = candidate_scores.get("avg_duration_seconds") or 0
        b_dur = compare_scores.get("avg_duration_seconds") or 0
        if c_dur and b_dur:
            result["speed_ratio"] = round(b_dur / c_dur, 2) if c_dur > 0 else None

    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
