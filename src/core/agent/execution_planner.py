"""Compact planner stage for agent execution turns."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable

from src.core.agent.model_roles import PLANNER_ROLE, resolve_model_for_role
from src.core.config.app_config import AppConfig
from src.core.ollama.ollama_client import chat_stream
from src.core.runtime.activity_stream import ActivityStream
from src.core.sandbox.tool_catalog import ToolCatalog

_PLANNER_SYSTEM = """You are the planning model for a local coding agent.

Your job is to produce a short execution plan for the worker model before it starts acting.

Rules:
- Keep the plan compact and practical.
- Prefer structured tools over CLI whenever possible.
- Use only tool names that appear in the Available tools list.
- For workspace exploration, prefer `list_files` and `read_file`.
- For file creation or edits, prefer `write_file`.
- For Python execution/tests, prefer `run_python_file`.
- Do not suggest IDE views, `tree`, `ls`, `dir`, `cat`, `type`, `pip`, `pytest`, `ruff`, or `mypy`
  unless the user explicitly asked for them or they are present in Available tools.
- If the request is mainly exploratory, focus on first reads and boundaries.
- If the request is an implementation task, focus on files, tests, and validation.
- Be terse: GOAL should be 1-2 lines, FIRST_STEPS at most 4 bullets, RISKS at most 3 bullets.
- Output only these sections:
  GOAL:
  FIRST_STEPS:
  RISKS:
  DONE_WHEN:
"""


@dataclass(frozen=True)
class PlannerStageResult:
    model_name: str
    plan_text: str
    wall_ms: float
    tokens_in: int
    tokens_out: int
    stopped: bool = False


_SECTION_ORDER = ("GOAL", "FIRST_STEPS", "RISKS", "DONE_WHEN")
_SECTION_LIMITS = {
    "GOAL": 2,
    "FIRST_STEPS": 4,
    "RISKS": 3,
    "DONE_WHEN": 3,
}


def should_plan_request(user_text: str) -> bool:
    text = (user_text or "").strip().lower()
    if len(text) >= 80 or "\n" in text:
        return True
    keywords = (
        "plan",
        "inspect",
        "analyze",
        "architecture",
        "refactor",
        "implement",
        "fix",
        "debug",
        "benchmark",
        "diagnose",
        "tune",
        "build",
    )
    return any(word in text for word in keywords)


def run_execution_planner(
    *,
    config: AppConfig,
    activity: ActivityStream,
    tool_catalog: ToolCatalog,
    user_text: str,
    sandbox_root: str,
    active_project: str = "",
    should_stop: Callable[[], bool] | None = None,
) -> PlannerStageResult | None:
    if not config.planning_enabled or not should_plan_request(user_text):
        return None

    model_name = resolve_model_for_role(config, PLANNER_ROLE)
    if not model_name:
        return None

    tool_names = ", ".join(tool.name for tool in tool_catalog.list_tools())
    workspace_label = active_project or "(sandbox root)"
    user_payload = (
        f"Sandbox root: {sandbox_root}\n"
        f"Active project: {workspace_label}\n"
        f"Available tools: {tool_names}\n\n"
        f"User request:\n{user_text}"
    )
    if "deepseek" in model_name.lower():
        messages = [{"role": "user", "content": f"{_PLANNER_SYSTEM}\n\n{user_payload}"}]
    else:
        messages = [
            {"role": "system", "content": _PLANNER_SYSTEM},
            {"role": "user", "content": user_payload},
        ]

    activity.info("planner", f"Planner stage started with {model_name}")
    result = chat_stream(
        base_url=config.ollama_base_url,
        model=model_name,
        messages=messages,
        should_stop=should_stop,
        temperature=min(config.temperature, 0.3),
        num_ctx=min(config.max_context_tokens, 4096),
    )
    plan_text = _sanitize_plan_text(result.get("content", ""))
    activity.info(
        "planner",
        f"Planner stage complete: model={model_name}, tokens_out={result.get('eval_count', 0)}, wall={result.get('wall_ms', 0):.0f}ms, chars={len(plan_text)}",
    )
    return PlannerStageResult(
        model_name=model_name,
        plan_text=plan_text,
        wall_ms=float(result.get("wall_ms", 0.0) or 0.0),
        tokens_in=int(result.get("prompt_eval_count", 0) or 0),
        tokens_out=int(result.get("eval_count", 0) or 0),
        stopped=bool(result.get("stopped", False)),
    )


def _sanitize_plan_text(text: str) -> str:
    cleaned = (text or "").replace("\r", "").strip()
    if not cleaned:
        return ""
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL | re.IGNORECASE).strip()
    if "</think>" in cleaned:
        cleaned = cleaned.split("</think>")[-1].strip()
    sections = _extract_sections(cleaned)
    if not sections:
        fallback_lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        fallback = "\n".join(fallback_lines[:8])
        return fallback[:1200]

    lines: list[str] = []
    for label in _SECTION_ORDER:
        lines.append(f"{label}:")
        values = sections.get(label, [])
        if values:
            lines.extend(f"- {value}" for value in values)
        else:
            lines.append("-")
        lines.append("")
    return "\n".join(lines).strip()


def _extract_sections(text: str) -> dict[str, list[str]]:
    matches = list(re.finditer(r"(?mi)^(GOAL|FIRST_STEPS|RISKS|DONE_WHEN)\s*:\s*", text))
    if not matches:
        return {}

    sections: dict[str, list[str]] = {}
    for index, match in enumerate(matches):
        label = match.group(1).upper()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        block = re.sub(r"<.*?>", "", block).strip()
        raw_lines = [line.strip(" \t-*") for line in block.splitlines() if line.strip()]
        limit = _SECTION_LIMITS.get(label, 3)
        sections[label] = raw_lines[:limit] or []
    return sections
