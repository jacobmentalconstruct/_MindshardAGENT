"""
FILE: ollama_prompt_lab.py
ROLE: Agent-facing local prompt-evaluation workbench for Ollama models.
WHAT IT DOES: Runs prompt variants against one or more local Ollama models, applies deterministic checks, optionally asks a judge model for rubric scoring, and writes reusable artifacts.
HOW TO USE:
  - Metadata: python _ollama-prompt-lab/tools/ollama_prompt_lab.py metadata
  - Run: python _ollama-prompt-lab/tools/ollama_prompt_lab.py run --input-file _ollama-prompt-lab/jobs/examples/quick_eval.json
INPUT OBJECT:
  - models: list of model names to run
  - pull_missing: optional bool to pull missing models before running
  - prompt_variants: list of prompt variant objects with `id` and `template`
  - cases: list of case objects with `id`, case fields, and optional deterministic `checks`
  - rubric: optional judge rubric object
  - keepalive: optional Ollama keepalive duration
  - hidethinking: optional bool, defaults true
  - timeout_seconds: optional per-run timeout
  - output_dir: optional artifact directory; defaults to artifacts/runs/<timestamp>
  - dry_run: optional bool to render prompts without calling models
NOTES:
  - Prompt templates use Python `{field_name}` formatting against each case object.
  - Deterministic checks are the most trusted signals in v1.
  - Judge scoring is heuristic and should be reviewed, not treated as ground truth.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from common import ensure_dir, now_stamp, standard_main, tool_result, write_json, write_text


FILE_METADATA = {
    "tool_name": "ollama_prompt_lab",
    "version": "1.0.0",
    "entrypoint": "tools/ollama_prompt_lab.py",
    "category": "evaluation",
    "summary": "Run local prompt evals against Ollama models with deterministic checks, optional rubric judging, and saved artifacts.",
    "mcp_name": "ollama_prompt_lab",
    "input_schema": {
        "type": "object",
        "properties": {
            "models": {"type": "array", "items": {"type": "string"}},
            "pull_missing": {"type": "boolean", "default": False},
            "prompt_variants": {
                "type": "array",
                "items": {"type": "object"}
            },
            "cases": {
                "type": "array",
                "items": {"type": "object"}
            },
            "rubric": {"type": "object"},
            "keepalive": {"type": "string"},
            "hidethinking": {"type": "boolean", "default": True},
            "timeout_seconds": {"type": "integer", "default": 120},
            "repeats": {"type": "integer", "default": 1},
            "output_dir": {"type": "string"},
            "dry_run": {"type": "boolean", "default": False}
        },
        "required": ["models", "prompt_variants", "cases"],
        "additionalProperties": False
    }
}


ANSI_PATTERN = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
SPINNER_PATTERN = re.compile(r"[\u2800-\u28ff]+")


class SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return ""


def _strip_ansi(text: str) -> str:
    return ANSI_PATTERN.sub("", text)


def _clean_stderr(text: str) -> str:
    cleaned = _strip_ansi(text)
    cleaned = SPINNER_PATTERN.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _lab_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_subprocess(args: list[str], *, timeout_seconds: int) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        check=False,
    )
    duration_seconds = round(time.perf_counter() - started, 3)
    return {
        "command": args,
        "returncode": completed.returncode,
        "duration_seconds": duration_seconds,
        "stdout": completed.stdout,
        "stderr": _clean_stderr(completed.stderr),
    }


def _installed_models(timeout_seconds: int) -> set[str]:
    command_result = _run_subprocess(["ollama", "list"], timeout_seconds=timeout_seconds)
    if command_result["returncode"] != 0:
        raise RuntimeError(f"Unable to list Ollama models: {command_result['stderr'] or command_result['stdout']}")
    models = set()
    for line in command_result["stdout"].splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("NAME"):
            continue
        models.add(stripped.split()[0])
    return models


def _pull_model(model: str, timeout_seconds: int) -> dict[str, Any]:
    result = _run_subprocess(["ollama", "pull", model], timeout_seconds=timeout_seconds)
    result["model"] = model
    return result


def _render_prompt(template: str, case: dict[str, Any]) -> str:
    values: dict[str, Any] = {}
    for key, value in case.items():
        if isinstance(value, (dict, list)):
            values[key] = json.dumps(value, indent=2, sort_keys=True)
        elif value is None:
            values[key] = ""
        else:
            values[key] = str(value)
    return template.format_map(SafeDict(values)).strip()


def _case_checks(case: dict[str, Any]) -> dict[str, Any]:
    return dict(case.get("checks", {}))


def _check_result(name: str, passed: bool, **details: Any) -> dict[str, Any]:
    payload = {"check": name, "passed": passed}
    payload.update(details)
    return payload


def _evaluate_checks(case: dict[str, Any], response_text: str) -> dict[str, Any]:
    checks = _case_checks(case)
    results = []
    normalized = response_text.strip()

    exact_match = checks.get("exact_match")
    if exact_match is not None:
        results.append(_check_result("exact_match", normalized == str(exact_match).strip(), expected=exact_match))

    contains_all = list(checks.get("contains_all", []))
    for needle in contains_all:
        results.append(_check_result("contains_all", needle in response_text, needle=needle))

    contains_any = list(checks.get("contains_any", []))
    if contains_any:
        matched = [needle for needle in contains_any if needle in response_text]
        results.append(_check_result("contains_any", bool(matched), needles=contains_any, matched=matched))

    not_contains_any = list(checks.get("not_contains_any", []))
    for needle in not_contains_any:
        results.append(_check_result("not_contains_any", needle not in response_text, needle=needle))

    regex_all = list(checks.get("regex_all", []))
    for pattern in regex_all:
        results.append(_check_result("regex_all", bool(re.search(pattern, response_text, re.MULTILINE)), pattern=pattern))

    min_length = checks.get("min_length")
    if min_length is not None:
        results.append(_check_result("min_length", len(normalized) >= int(min_length), expected=min_length, actual=len(normalized)))

    max_length = checks.get("max_length")
    if max_length is not None:
        results.append(_check_result("max_length", len(normalized) <= int(max_length), expected=max_length, actual=len(normalized)))

    json_parse = checks.get("json_parse")
    if json_parse:
        try:
            parsed = json.loads(normalized)
            results.append(_check_result("json_parse", True, parsed_type=type(parsed).__name__))
        except json.JSONDecodeError as exc:
            results.append(_check_result("json_parse", False, error=str(exc)))

    passed_count = sum(1 for item in results if item["passed"])
    return {
        "check_count": len(results),
        "passed_count": passed_count,
        "failed_count": len(results) - passed_count,
        "pass_rate": round((passed_count / len(results)), 3) if results else None,
        "results": results,
    }


def _extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    for candidate in (stripped, stripped.strip("`")):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    start = stripped.find("{")
    while start != -1:
        depth = 0
        for index in range(start, len(stripped)):
            char = stripped[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = stripped[start:index + 1]
                    try:
                        parsed = json.loads(candidate)
                        if isinstance(parsed, dict):
                            return parsed
                    except json.JSONDecodeError:
                        break
        start = stripped.find("{", start + 1)
    return None


def _judge_prompt(case: dict[str, Any], response_text: str, rubric: dict[str, Any]) -> str:
    criteria_lines = []
    for criterion in rubric.get("criteria", []):
        criteria_lines.append(
            f"- id: {criterion.get('id', '')}; label: {criterion.get('label', '')}; "
            f"weight: {criterion.get('weight', 1)}; guidance: {criterion.get('guidance', '')}"
        )
    criteria_text = "\n".join(criteria_lines) or "- id: overall; label: overall quality; weight: 1; guidance: general usefulness"
    case_json = json.dumps(case, indent=2, sort_keys=True)
    return (
        "You are a strict prompt-eval judge.\n"
        "Score the candidate response against the provided case and criteria.\n"
        "Use integer scores from 0 to 100, where 100 is excellent.\n"
        "Return only one JSON object with these keys:\n"
        "{"
        "\"overall_score\": integer, "
        "\"recommendation\": \"keep|revise|reject\", "
        "\"summary\": string, "
        "\"criteria\": [{\"id\": string, \"score\": integer, \"notes\": string}]"
        "}\n\n"
        f"Criteria:\n{criteria_text}\n\n"
        f"Case:\n{case_json}\n\n"
        f"Candidate response:\n{response_text}\n"
    )


def _judge_output(
    case: dict[str, Any],
    response_text: str,
    rubric: dict[str, Any],
    *,
    timeout_seconds: int,
    keepalive: str | None,
    hidethinking: bool,
) -> dict[str, Any]:
    judge_model = rubric.get("judge_model")
    if not judge_model:
        return {"status": "skipped", "reason": "No judge_model provided in rubric."}

    args = ["ollama", "run", judge_model, _judge_prompt(case, response_text, rubric)]
    if hidethinking:
        args.append("--hidethinking")
    if keepalive:
        args.extend(["--keepalive", keepalive])

    command_result = _run_subprocess(args, timeout_seconds=timeout_seconds)
    stdout = command_result["stdout"].strip()
    parsed = _extract_json_object(stdout)
    if command_result["returncode"] != 0:
        return {
            "status": "error",
            "model": judge_model,
            "message": command_result["stderr"] or stdout,
            "command": command_result["command"],
            "duration_seconds": command_result["duration_seconds"],
        }
    if parsed is None:
        return {
            "status": "unparsed",
            "model": judge_model,
            "raw_output": stdout,
            "duration_seconds": command_result["duration_seconds"],
        }
    return {
        "status": "ok",
        "model": judge_model,
        "duration_seconds": command_result["duration_seconds"],
        "parsed": parsed,
    }


def _aggregate_runs(run_rows: list[dict[str, Any]]) -> dict[str, Any]:
    def bucket_factory() -> dict[str, Any]:
        return {
            "runs": 0,
            "success_runs": 0,
            "deterministic_pass_rate_avg": 0.0,
            "judge_score_avg": 0.0,
            "judge_scored_runs": 0,
            "recommended_keep": 0,
            "recommended_revise": 0,
            "recommended_reject": 0,
        }

    by_model: dict[str, dict[str, Any]] = defaultdict(bucket_factory)
    by_variant: dict[str, dict[str, Any]] = defaultdict(bucket_factory)
    by_model_variant: dict[str, dict[str, Any]] = defaultdict(bucket_factory)

    for row in run_rows:
        pass_rate = row["deterministic_checks"].get("pass_rate")
        pass_rate_value = float(pass_rate) if pass_rate is not None else 0.0
        judge_score = row["evaluation"].get("judge_score")
        recommendation = row["evaluation"].get("recommendation", "revise")
        model_bucket = by_model[row["model"]]
        variant_bucket = by_variant[row["prompt_variant_id"]]
        pair_bucket = by_model_variant[f"{row['model']}::{row['prompt_variant_id']}"]

        for bucket in (model_bucket, variant_bucket, pair_bucket):
            bucket["runs"] += 1
            if row.get("status") == "ok":
                bucket["success_runs"] += 1
            bucket["deterministic_pass_rate_avg"] += pass_rate_value
            bucket[f"recommended_{recommendation}"] += 1
            if isinstance(judge_score, (int, float)):
                bucket["judge_score_avg"] += float(judge_score)
                bucket["judge_scored_runs"] += 1

    for bucket in (by_model, by_variant, by_model_variant):
        for data in bucket.values():
            if data["runs"]:
                data["deterministic_pass_rate_avg"] = round(data["deterministic_pass_rate_avg"] / data["runs"], 3)
            if data["judge_scored_runs"]:
                data["judge_score_avg"] = round(data["judge_score_avg"] / data["judge_scored_runs"], 3)
            else:
                data["judge_score_avg"] = None

    return {
        "by_model": dict(sorted(by_model.items())),
        "by_prompt_variant": dict(sorted(by_variant.items())),
        "by_model_prompt_variant": dict(sorted(by_model_variant.items())),
    }


def _judge_score(judge_payload: dict[str, Any]) -> int | float | None:
    if judge_payload.get("status") != "ok":
        return None
    parsed = judge_payload.get("parsed")
    if not isinstance(parsed, dict):
        return None
    score = parsed.get("overall_score")
    if isinstance(score, (int, float)):
        return score
    return None


def _judge_recommendation(judge_payload: dict[str, Any]) -> str | None:
    if judge_payload.get("status") != "ok":
        return None
    parsed = judge_payload.get("parsed")
    if not isinstance(parsed, dict):
        return None
    recommendation = parsed.get("recommendation")
    if recommendation in {"keep", "revise", "reject"}:
        return recommendation
    return None


def _row_evaluation(row: dict[str, Any]) -> dict[str, Any]:
    deterministic = row["deterministic_checks"]
    pass_rate = deterministic.get("pass_rate")
    failed_count = deterministic.get("failed_count")
    judge_score = _judge_score(row["judge"])
    judge_recommendation = _judge_recommendation(row["judge"])
    reasons = []

    if row.get("status") != "ok":
        reasons.append("model_run_failed")
        return {
            "deterministic_pass_rate": pass_rate,
            "judge_score": judge_score,
            "judge_recommendation": judge_recommendation,
            "recommendation": "reject",
            "reasons": reasons,
        }

    if failed_count:
        reasons.append("deterministic_checks_failed")
        recommendation = "revise"
    else:
        recommendation = "keep"

    if judge_recommendation == "reject":
        reasons.append("judge_recommended_reject")
        recommendation = "reject"
    elif judge_recommendation == "revise" and recommendation != "reject":
        reasons.append("judge_recommended_revise")
        recommendation = "revise"
    elif judge_recommendation == "keep" and recommendation == "keep":
        reasons.append("judge_recommended_keep")

    if judge_score is not None and judge_score < 60:
        reasons.append("judge_score_below_60")
        recommendation = "reject"
    elif judge_score is not None and judge_score < 80 and recommendation == "keep":
        reasons.append("judge_score_below_80")
        recommendation = "revise"

    return {
        "deterministic_pass_rate": pass_rate,
        "judge_score": judge_score,
        "judge_recommendation": judge_recommendation,
        "recommendation": recommendation,
        "reasons": reasons,
    }


def _leaderboard_entries(run_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in run_rows:
        grouped[(row["model"], row["prompt_variant_id"])].append(row)

    for (model, prompt_variant_id), rows in grouped.items():
        deterministic_values = [row["evaluation"]["deterministic_pass_rate"] for row in rows if row["evaluation"]["deterministic_pass_rate"] is not None]
        judge_values = [row["evaluation"]["judge_score"] for row in rows if isinstance(row["evaluation"]["judge_score"], (int, float))]
        recommendations = Counter(row["evaluation"]["recommendation"] for row in rows)
        entries.append({
            "model": model,
            "prompt_variant_id": prompt_variant_id,
            "runs": len(rows),
            "deterministic_pass_rate_avg": round(sum(deterministic_values) / len(deterministic_values), 3) if deterministic_values else None,
            "judge_score_avg": round(sum(judge_values) / len(judge_values), 3) if judge_values else None,
            "keep_count": recommendations.get("keep", 0),
            "revise_count": recommendations.get("revise", 0),
            "reject_count": recommendations.get("reject", 0),
        })

    def sort_key(item: dict[str, Any]) -> tuple:
        return (
            -(item["deterministic_pass_rate_avg"] if item["deterministic_pass_rate_avg"] is not None else -1),
            -(item["judge_score_avg"] if item["judge_score_avg"] is not None else -1),
            item["prompt_variant_id"],
            item["model"],
        )

    return sorted(entries, key=sort_key)


def run(arguments: dict) -> dict:
    models = list(arguments["models"])
    prompt_variants = list(arguments["prompt_variants"])
    cases = list(arguments["cases"])
    rubric = arguments.get("rubric")
    pull_missing = bool(arguments.get("pull_missing", False))
    hidethinking = bool(arguments.get("hidethinking", True))
    timeout_seconds = int(arguments.get("timeout_seconds", 120))
    keepalive = arguments.get("keepalive")
    dry_run = bool(arguments.get("dry_run", False))
    repeats = max(1, int(arguments.get("repeats", 1)))

    if not models:
        raise ValueError("At least one model is required.")
    if not prompt_variants:
        raise ValueError("At least one prompt variant is required.")
    if not cases:
        raise ValueError("At least one case is required.")

    lab_root = _lab_root()
    run_id = now_stamp()
    output_dir = Path(arguments.get("output_dir") or (lab_root / "artifacts" / "runs" / run_id)).resolve()
    ensure_dir(output_dir)

    installed_before = _installed_models(timeout_seconds)
    required_models = list(dict.fromkeys(models + ([rubric["judge_model"]] if rubric and rubric.get("judge_model") else [])))
    missing_models = [model for model in required_models if model not in installed_before]
    pull_results = []
    if missing_models and pull_missing:
        for model in missing_models:
            pull_results.append(_pull_model(model, timeout_seconds))
        installed_after = _installed_models(timeout_seconds)
        missing_models = [model for model in required_models if model not in installed_after]

    warnings = []
    if missing_models and not dry_run:
        raise RuntimeError(f"Missing models: {missing_models}. Set pull_missing=true or install them first.")
    installed_after_pull = installed_before | {item.get("model") for item in pull_results if item.get("returncode") == 0}
    if rubric and rubric.get("judge_model") and rubric["judge_model"] not in installed_after_pull:
        warnings.append(f"Judge model {rubric['judge_model']!r} was not present before runs; judge step may fail unless it is installed.")

    run_rows = []
    prompt_records = []

    for variant in prompt_variants:
        variant_id = str(variant["id"])
        template = str(variant["template"])
        for case in cases:
            case_id = str(case["id"])
            prompt_text = _render_prompt(template, case)
            prompt_records.append({
                "prompt_variant_id": variant_id,
                "case_id": case_id,
                "prompt_text": prompt_text,
            })
            for model in models:
                for repeat_index in range(1, repeats + 1):
                    row = {
                        "model": model,
                        "prompt_variant_id": variant_id,
                        "case_id": case_id,
                        "repeat_index": repeat_index,
                        "prompt_text": prompt_text,
                    }
                    if dry_run:
                        row["response_text"] = ""
                        row["stdout"] = ""
                        row["stderr"] = ""
                        row["duration_seconds"] = 0.0
                        row["deterministic_checks"] = _evaluate_checks(case, "")
                        row["judge"] = {"status": "skipped", "reason": "dry_run=true"}
                        row["status"] = "dry-run"
                        row["evaluation"] = _row_evaluation(row)
                        run_rows.append(row)
                        continue

                    args = ["ollama", "run", model, prompt_text]
                    if hidethinking:
                        args.append("--hidethinking")
                    if keepalive:
                        args.extend(["--keepalive", keepalive])

                    command_result = _run_subprocess(args, timeout_seconds=timeout_seconds)
                    response_text = command_result["stdout"].strip()
                    row["stdout"] = command_result["stdout"]
                    row["stderr"] = command_result["stderr"]
                    row["response_text"] = response_text
                    row["duration_seconds"] = command_result["duration_seconds"]
                    row["status"] = "ok" if command_result["returncode"] == 0 else "error"
                    row["deterministic_checks"] = _evaluate_checks(case, response_text)
                    row["judge"] = (
                        _judge_output(
                            case,
                            response_text,
                            rubric,
                            timeout_seconds=timeout_seconds,
                            keepalive=keepalive,
                            hidethinking=hidethinking,
                        )
                        if rubric
                        else {"status": "skipped", "reason": "No rubric provided."}
                    )
                    row["evaluation"] = _row_evaluation(row)
                    run_rows.append(row)

    summary = {
        "run_id": run_id,
        "dry_run": dry_run,
        "models": models,
        "prompt_variant_count": len(prompt_variants),
        "case_count": len(cases),
        "repeats": repeats,
        "run_count": len(run_rows),
        "missing_models_after_pull": missing_models,
        "pull_count": len(pull_results),
        "aggregate": _aggregate_runs(run_rows),
        "leaderboard": _leaderboard_entries(run_rows),
    }

    write_json(output_dir / "run_input.json", arguments)
    write_json(output_dir / "summary.json", summary)
    write_json(output_dir / "results.json", {"runs": run_rows})
    write_json(output_dir / "prompts.json", {"prompts": prompt_records})
    write_json(output_dir / "leaderboard.json", {"leaderboard": summary["leaderboard"]})
    write_text(output_dir / "README.txt", "Prompt-lab artifact folder containing input, prompts, summary, and results.")

    result = {
        "run_id": run_id,
        "output_dir": str(output_dir),
        "warnings": warnings,
        "models": models,
        "missing_models_after_pull": missing_models,
        "pull_results": pull_results,
        "summary": summary,
        "artifacts": {
            "run_input": str(output_dir / "run_input.json"),
            "summary": str(output_dir / "summary.json"),
            "results": str(output_dir / "results.json"),
            "prompts": str(output_dir / "prompts.json"),
            "leaderboard": str(output_dir / "leaderboard.json"),
        },
        "sample_runs": run_rows[: min(10, len(run_rows))],
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
