"""Streaming/tool-loop executor for the tool-agent turn pipeline.

Owns only the iterative model-response/tool-execution loop plus recovery
replanning. It does not own prompt building, evidence pass-2, or RAG storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from src.core.agent.loop_types import STOPPED_BY_USER_MESSAGE
from src.core.agent.model_roles import PRIMARY_CHAT_ROLE, resolve_model_for_role
from src.core.agent.recovery_planner import (
    detect_failure_pattern,
    format_recovery_injection,
    record_round,
    run_recovery_planner,
)
from src.core.agent.tool_router import ToolRouter
from src.core.agent.transcript_formatter import format_all_results, strip_tool_call_markup
from src.core.config.app_config import AppConfig
from src.core.ollama.ollama_client import chat_stream
from src.core.runtime.activity_stream import ActivityStream


@dataclass(frozen=True)
class ToolAgentTurnOutcome:
    total_content: list[str]
    result: dict[str, Any]
    assistant_text: str
    rounds: int
    recovery_triggered: bool


def run_tool_agent_turn(
    *,
    config: AppConfig,
    tool_router: ToolRouter,
    activity: ActivityStream,
    user_text: str,
    messages: list[dict[str, str]],
    on_token: Callable[[str], None] | None = None,
    on_tool_start: Callable[[str], None] | None = None,
    on_tool_result: Callable[[dict], None] | None = None,
    should_stop: Callable[[], bool],
) -> ToolAgentTurnOutcome:
    total_content: list[str] = []
    rounds = 0
    result: dict[str, Any] = {}
    assistant_text = ""
    round_history = []
    recovery_used = False

    while rounds < config.max_tool_rounds and not should_stop():
        rounds += 1
        round_tokens: list[str] = []
        model_name = resolve_model_for_role(config, PRIMARY_CHAT_ROLE)

        activity.model("agent", f"Round {rounds}: requesting model response from {model_name}")
        result = chat_stream(
            base_url=config.ollama_base_url,
            model=model_name,
            messages=messages,
            on_token=lambda t: (round_tokens.append(t), on_token(t) if on_token else None),
            should_stop=should_stop,
            temperature=config.temperature,
            num_ctx=config.max_context_tokens,
        )

        assistant_text = result.get("content", "".join(round_tokens))
        visible_assistant_text = strip_tool_call_markup(assistant_text)
        if visible_assistant_text:
            total_content.append(visible_assistant_text)

        if result.get("stopped"):
            activity.info("agent", "Response loop interrupted by user request")
            break

        if not tool_router.has_tool_calls(assistant_text):
            break

        activity.tool("agent", "Tool call detected in response")
        if on_tool_start:
            on_tool_start(assistant_text)

        tool_results = tool_router.execute_all(assistant_text)
        tool_output = format_all_results(tool_results)

        if on_tool_result:
            on_tool_result({"results": tool_results, "formatted": tool_output})

        messages.append({"role": "assistant", "content": assistant_text})
        tool_results_body = tool_output or "[No tool output returned. Check your tool call format and retry.]"
        messages.append({"role": "user", "content": f"[Tool Results]\n{tool_results_body}"})

        round_history.append(record_round(rounds, tool_results, tool_output))
        if not recovery_used:
            pattern = detect_failure_pattern(round_history, config.max_tool_rounds)
            if pattern:
                recovery_used = True
                plan = run_recovery_planner(
                    config=config,
                    activity=activity,
                    user_text=user_text,
                    pattern=pattern,
                    round_history=round_history,
                )
                injection = (
                    format_recovery_injection(plan)
                    if plan
                    else (
                        f"[RECOVERY HINT — {pattern.kind}]\n"
                        f"{pattern.suggested_action}"
                    )
                )
                messages.append({"role": "system", "content": injection})
                activity.warn(
                    "recovery",
                    f"Pattern '{pattern.kind}' detected at round {rounds}; "
                    "recovery guidance injected",
                )

        activity.tool("agent", f"Tool round {rounds} complete, continuing...")

    if (
        not should_stop()
        and rounds >= config.max_tool_rounds
        and assistant_text
        and tool_router.has_tool_calls(assistant_text)
    ):
        total_content.append(
            f"[Stopped after {config.max_tool_rounds} tool rounds. "
            "Increase Tools > Max Tool Rounds to allow deeper exploration.]"
        )
    elif should_stop() or result.get("stopped"):
        total_content.append(STOPPED_BY_USER_MESSAGE)

    return ToolAgentTurnOutcome(
        total_content=total_content,
        result=result,
        assistant_text=assistant_text,
        rounds=rounds,
        recovery_triggered=recovery_used,
    )
