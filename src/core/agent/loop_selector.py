"""Intent-driven selection for agent execution loops."""

from __future__ import annotations

from src.core.agent.execution_planner import should_plan_request
from src.core.agent.loop_types import (
    DIRECT_CHAT_LOOP,
    PLANNER_ONLY_LOOP,
    RECOVERY_AGENT_LOOP,
    REVIEW_JUDGE_LOOP,
    THOUGHT_CHAIN_LOOP,
    TOOL_AGENT_LOOP,
)


def select_loop_mode(
    user_text: str,
    mode_hint: str | None = None,
    has_tools: bool = True,
) -> str:
    """Choose the best loop mode for a user request.

    The selector is intentionally heuristic for now. It provides a single seam
    where future intent-analysis can route into richer loop families without
    bloating Engine or the loop implementations.

    When tools are available (default), most requests go through the tool-agent
    loop so the model can use tools and benefit from pre-gathered context.
    Direct chat is reserved for empty input or when no tools are configured.
    """

    if mode_hint:
        return mode_hint

    text = (user_text or "").strip().lower()
    if not text:
        return DIRECT_CHAT_LOOP

    if any(phrase in text for phrase in (
        "thought chain",
        "break this down into tasks",
        "decompose this",
        "task list",
        "step-by-step task list",
    )):
        return THOUGHT_CHAIN_LOOP

    if any(phrase in text for phrase in (
        "make a plan",
        "give me a plan",
        "plan this",
        "planning only",
        "just plan",
    )):
        return PLANNER_ONLY_LOOP

    if any(phrase in text for phrase in (
        "try a different approach",
        "that didn't work",
        "that failed",
        "try again differently",
        "recover from",
        "fix the previous attempt",
    )):
        return RECOVERY_AGENT_LOOP

    if any(phrase in text for phrase in (
        "review this",
        "critique this",
        "fact-check",
        "is this correct",
        "judge this",
        "review the response",
        "check for errors",
    )):
        return REVIEW_JUDGE_LOOP

    # When tools are available, always use the tool-agent loop so the model
    # can access tools and benefit from pre-gathered workspace context.
    if has_tools:
        return TOOL_AGENT_LOOP

    if should_plan_request(text):
        return TOOL_AGENT_LOOP

    return DIRECT_CHAT_LOOP
