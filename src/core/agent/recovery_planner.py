"""Recovery replanner — detects repeated failure patterns and replans.

Owns:
  - Failure pattern detection across tool rounds
  - Recovery prompt construction
  - Recovery plan generation via the planner model

Does NOT own:
  - Turn execution (that is TurnPipeline's job)
  - Stop-request state (caller passes should_stop)
  - Chat history management
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from src.core.agent.model_roles import RECOVERY_PLANNER_ROLE, resolve_model_for_role
from src.core.config.app_config import AppConfig
from src.core.ollama.ollama_client import chat_stream
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.runtime_logger import get_logger

log = get_logger("recovery_planner")

# How many identical consecutive rounds trigger loop detection
_LOOP_REPEAT_THRESHOLD = 2
# How many consecutive error rounds trigger failure detection
_ERROR_REPEAT_THRESHOLD = 2
# When rounds_used / max_rounds >= this fraction, warn of budget exhaustion
_BUDGET_EXHAUSTION_FRACTION = 0.80


@dataclass
class RoundRecord:
    """Summary of a single tool round for pattern analysis."""
    round_num: int
    tool_names: tuple[str, ...]
    had_error: bool
    output_hash: str  # SHA-256 of the full tool output (detects exact repeats)
    output_excerpt: str  # First 200 chars of formatted tool output


@dataclass
class FailurePattern:
    """Describes a detected failure pattern."""
    kind: str            # "tool_error_loop" | "output_loop" | "budget_exhaustion"
    description: str
    rounds_involved: tuple[int, ...]
    suggested_action: str


@dataclass
class RecoveryPlan:
    """Result of calling the recovery planner model."""
    guidance: str        # The model's recovery suggestions
    model_name: str
    tokens_in: int
    tokens_out: int
    wall_ms: float
    pattern: FailurePattern


def record_round(
    round_num: int,
    tool_results: list[dict[str, Any]],
    formatted_output: str,
) -> RoundRecord:
    """Build a RoundRecord from a completed tool round's results.

    Args:
        round_num: 1-based round counter
        tool_results: list of tool result dicts from ToolRouter.execute_all()
        formatted_output: the formatted string passed back into messages
    """
    tool_names = tuple(
        str(r.get("tool", "unknown"))
        for r in tool_results
    )
    had_error = any(
        r.get("error") or r.get("exit_code", 0) != 0
        for r in tool_results
    )
    output_hash = hashlib.sha256(formatted_output.encode()).hexdigest()[:16]
    output_excerpt = formatted_output[:200].replace("\n", " ").strip()
    return RoundRecord(
        round_num=round_num,
        tool_names=tool_names,
        had_error=had_error,
        output_hash=output_hash,
        output_excerpt=output_excerpt,
    )


def detect_failure_pattern(
    history: list[RoundRecord],
    max_tool_rounds: int,
) -> FailurePattern | None:
    """Scan the round history for actionable failure patterns.

    Returns a FailurePattern if a pattern is found, else None.
    Patterns are evaluated in priority order — only the highest-priority
    pattern is returned per call.

    Detection rules:
      1. tool_error_loop: Same tool names, with errors, in the last N consecutive rounds
      2. output_loop: Identical output_hash for the last N consecutive rounds
      3. budget_exhaustion: rounds_used / max_tool_rounds >= threshold, no clean exit yet
    """
    if len(history) < 2:
        return None

    # ── Rule 1: tool error loop ──────────────────────────────────────────────
    if len(history) >= _ERROR_REPEAT_THRESHOLD:
        recent = history[-_ERROR_REPEAT_THRESHOLD:]
        if all(r.had_error for r in recent):
            tool_sets = [r.tool_names for r in recent]
            if all(t == tool_sets[0] for t in tool_sets):
                return FailurePattern(
                    kind="tool_error_loop",
                    description=(
                        f"Tool(s) {list(tool_sets[0])} produced errors in the last "
                        f"{_ERROR_REPEAT_THRESHOLD} consecutive rounds."
                    ),
                    rounds_involved=tuple(r.round_num for r in recent),
                    suggested_action=(
                        "Try a different approach, different tool arguments, or a "
                        "different tool entirely. If the tool requires a file or path "
                        "that may not exist, verify existence first."
                    ),
                )

    # ── Rule 2: output loop (exact output repeat) ────────────────────────────
    if len(history) >= _LOOP_REPEAT_THRESHOLD:
        recent = history[-_LOOP_REPEAT_THRESHOLD:]
        hashes = [r.output_hash for r in recent]
        if all(h == hashes[0] for h in hashes):
            return FailurePattern(
                kind="output_loop",
                description=(
                    f"Tool output has been identical for {_LOOP_REPEAT_THRESHOLD} "
                    f"consecutive rounds (hash={hashes[0]}). The model appears to be "
                    "in an infinite tool-call loop."
                ),
                rounds_involved=tuple(r.round_num for r in recent),
                suggested_action=(
                    "Stop repeating the same tool call. Summarize what you have found "
                    "so far and either complete the task or explain why it cannot be done."
                ),
            )

    # ── Rule 3: budget exhaustion approaching ────────────────────────────────
    rounds_used = history[-1].round_num if history else 0
    fraction = rounds_used / max(max_tool_rounds, 1)
    if fraction >= _BUDGET_EXHAUSTION_FRACTION:
        return FailurePattern(
            kind="budget_exhaustion",
            description=(
                f"Used {rounds_used}/{max_tool_rounds} tool rounds "
                f"({fraction*100:.0f}% of budget). Risk of hitting round limit "
                "without producing a final answer."
            ),
            rounds_involved=(rounds_used,),
            suggested_action=(
                "Wrap up the current investigation and produce a final answer now. "
                "Do not start new tool chains unless absolutely required."
            ),
        )

    return None


def run_recovery_planner(
    config: AppConfig,
    activity: ActivityStream,
    user_text: str,
    pattern: FailurePattern,
    round_history: list[RoundRecord],
) -> RecoveryPlan | None:
    """Call the planner model with a recovery prompt and return guidance.

    Returns None if the planner call fails or if no planner model is configured.
    The guidance text is intended to be injected as a system message into the
    ongoing turn's message list.
    """
    model_name = resolve_model_for_role(config, RECOVERY_PLANNER_ROLE)
    if not model_name:
        log.warning("No recovery model configured; using pattern suggestion as-is")
        return None

    # Build a compact round summary
    round_summary_lines = []
    for rec in round_history[-4:]:  # last 4 rounds at most
        status = "ERROR" if rec.had_error else "ok"
        round_summary_lines.append(
            f"  Round {rec.round_num}: [{status}] tools={list(rec.tool_names)} "
            f"output='{rec.output_excerpt[:80]}'"
        )
    round_summary = "\n".join(round_summary_lines) or "  (no rounds recorded)"

    recovery_prompt = (
        "You are an execution recovery advisor. An AI agent has encountered a "
        "repeated failure pattern during a task. Your job is to suggest a concrete "
        "recovery approach in 2-4 sentences. Be specific and actionable.\n\n"
        f"ORIGINAL USER REQUEST:\n{user_text[:400]}\n\n"
        f"FAILURE PATTERN: {pattern.kind}\n"
        f"DESCRIPTION: {pattern.description}\n"
        f"ROUNDS INVOLVED: {list(pattern.rounds_involved)}\n\n"
        f"RECENT ROUND HISTORY:\n{round_summary}\n\n"
        f"SUGGESTED ACTION: {pattern.suggested_action}\n\n"
        "Provide a brief, direct recovery plan for the agent. Focus on what to do "
        "differently. Do not repeat the failure description."
    )

    messages = [{"role": "user", "content": recovery_prompt}]
    activity.info("recovery", f"Recovery planner triggered: {pattern.kind} ({model_name})")

    try:
        result = chat_stream(
            base_url=config.ollama_base_url,
            model=model_name,
            messages=messages,
            temperature=0.3,
            num_ctx=min(getattr(config, "max_context_tokens", 4096), 2048),
        )
    except Exception as exc:
        log.warning("Recovery planner call failed: %s", exc)
        activity.warn("recovery", f"Recovery planner call failed: {exc}")
        return None

    guidance = result.get("content", "").strip()
    if not guidance:
        guidance = pattern.suggested_action

    activity.info("recovery", f"Recovery plan generated ({len(guidance)} chars)")

    return RecoveryPlan(
        guidance=guidance,
        model_name=model_name,
        tokens_in=result.get("prompt_eval_count", 0),
        tokens_out=result.get("eval_count", 0),
        wall_ms=result.get("wall_ms", 0.0),
        pattern=pattern,
    )


def format_recovery_injection(plan: RecoveryPlan) -> str:
    """Format a recovery plan as a system message content string."""
    return (
        f"[RECOVERY GUIDANCE — {plan.pattern.kind}]\n"
        f"The previous approach produced a repeated failure pattern. "
        f"Recovery advisor says:\n\n{plan.guidance}\n\n"
        "Change your approach now. Do not repeat the same tool call that has been failing."
    )
