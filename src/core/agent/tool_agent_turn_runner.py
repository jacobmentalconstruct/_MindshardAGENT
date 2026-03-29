"""Streaming/tool-loop executor for the tool-agent turn pipeline.

Owns only the iterative model-response/tool-execution loop plus recovery
replanning. It does not own prompt building, evidence pass-2, or RAG storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from src.core.agent.filesystem_claim_guardrail import (
    FilesystemEvidence,
    FilesystemGuardrailEvaluation,
    evaluate_filesystem_guardrail,
    summarize_guardrail_violations,
)
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
    filesystem_guardrail_triggered: bool
    filesystem_guardrail_repaired: bool
    filesystem_guardrail_failed: bool
    filesystem_evidence_summary: dict[str, Any]


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
    fs_evidence = FilesystemEvidence()
    fs_guardrail_triggered = False
    fs_guardrail_repaired = False
    fs_guardrail_failed = False

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
        for tool_result in tool_results:
            fs_evidence.record_tool_result(tool_result, config.sandbox_root)
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

    if not should_stop() and not result.get("stopped"):
        evaluation = evaluate_filesystem_guardrail(
            user_text=user_text,
            assistant_text=assistant_text,
            evidence=fs_evidence,
            sandbox_root=config.sandbox_root,
        )
        if evaluation.triggered:
            fs_guardrail_triggered = True
            _remove_final_visible_claim(total_content, assistant_text)
            activity.warn(
                "filesystem_guardrail",
                "Filesystem claim was not backed by matching tool evidence; "
                "starting one bounded repair pass",
            )
            repair = _run_filesystem_guardrail_repair(
                config=config,
                tool_router=tool_router,
                activity=activity,
                user_text=user_text,
                messages=messages,
                assistant_text=assistant_text,
                evaluation=evaluation,
                evidence=fs_evidence,
                on_token=on_token,
                on_tool_start=on_tool_start,
                on_tool_result=on_tool_result,
                should_stop=should_stop,
            )
            rounds += repair["rounds_used"]
            assistant_text = repair["assistant_text"]
            result = repair["result"]
            if repair["content"]:
                total_content.append(repair["content"])
            fs_guardrail_repaired = repair["repaired"]
            fs_guardrail_failed = repair["failed"]

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
        filesystem_guardrail_triggered=fs_guardrail_triggered,
        filesystem_guardrail_repaired=fs_guardrail_repaired,
        filesystem_guardrail_failed=fs_guardrail_failed,
        filesystem_evidence_summary=fs_evidence.to_summary(),
    )


def _remove_final_visible_claim(total_content: list[str], assistant_text: str) -> None:
    visible = strip_tool_call_markup(assistant_text).strip()
    if not visible or not total_content:
        return
    if total_content[-1].strip() == visible:
        total_content.pop()


def _chat_once(
    *,
    config: AppConfig,
    messages: list[dict[str, str]],
    on_token: Callable[[str], None] | None,
    should_stop: Callable[[], bool],
) -> tuple[dict[str, Any], str]:
    round_tokens: list[str] = []
    model_name = resolve_model_for_role(config, PRIMARY_CHAT_ROLE)
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
    return result, assistant_text


def _build_guardrail_repair_message(
    *,
    evaluation: FilesystemGuardrailEvaluation,
    evidence: FilesystemEvidence,
) -> str:
    return (
        "Filesystem claim guardrail triggered.\n\n"
        "The previous assistant claim is not supported by matching file-tool evidence.\n"
        f"Problem summary: {summarize_guardrail_violations(evaluation)}.\n"
        f"Observed filesystem evidence: {evidence.to_summary()}.\n\n"
        "Use the correct file tools now if you can still complete the request.\n"
        "If you cannot verify success with file tools, say so plainly instead of claiming success."
    )


def _deterministic_guardrail_failure_message(
    *,
    evaluation: FilesystemGuardrailEvaluation,
) -> str:
    return (
        "[Filesystem guardrail] I can't confirm the requested file change from tool evidence. "
        f"Reason: {summarize_guardrail_violations(evaluation)}. "
        "Please ask me to inspect the target file directly or retry the step."
    )


def _run_filesystem_guardrail_repair(
    *,
    config: AppConfig,
    tool_router: ToolRouter,
    activity: ActivityStream,
    user_text: str,
    messages: list[dict[str, str]],
    assistant_text: str,
    evaluation: FilesystemGuardrailEvaluation,
    evidence: FilesystemEvidence,
    on_token: Callable[[str], None] | None,
    on_tool_start: Callable[[str], None] | None,
    on_tool_result: Callable[[dict], None] | None,
    should_stop: Callable[[], bool],
) -> dict[str, Any]:
    repair_messages = list(messages)
    if assistant_text:
        repair_messages.append({"role": "assistant", "content": assistant_text})
    repair_messages.append({
        "role": "system",
        "content": _build_guardrail_repair_message(evaluation=evaluation, evidence=evidence),
    })

    rounds_used = 0
    repair_result: dict[str, Any] = {}
    repair_text = ""

    if should_stop():
        return {
            "assistant_text": assistant_text,
            "result": repair_result,
            "content": _deterministic_guardrail_failure_message(evaluation=evaluation),
            "repaired": False,
            "failed": True,
            "rounds_used": rounds_used,
        }

    rounds_used += 1
    activity.info("filesystem_guardrail", "Running bounded repair pass")
    repair_result, repair_text = _chat_once(
        config=config,
        messages=repair_messages,
        on_token=on_token,
        should_stop=should_stop,
    )

    if repair_result.get("stopped") or should_stop():
        return {
            "assistant_text": repair_text,
            "result": repair_result,
            "content": _deterministic_guardrail_failure_message(evaluation=evaluation),
            "repaired": False,
            "failed": True,
            "rounds_used": rounds_used,
        }

    if tool_router.has_tool_calls(repair_text):
        if on_tool_start:
            on_tool_start(repair_text)
        tool_results = tool_router.execute_all(repair_text)
        for tool_result in tool_results:
            evidence.record_tool_result(tool_result, config.sandbox_root)
        tool_output = format_all_results(tool_results)
        if on_tool_result:
            on_tool_result({"results": tool_results, "formatted": tool_output})
        repair_messages.append({"role": "assistant", "content": repair_text})
        repair_messages.append({
            "role": "user",
            "content": f"[Tool Results]\n{tool_output or '[No tool output returned. Check your tool call format and retry.]'}",
        })
        repair_messages.append({
            "role": "system",
            "content": (
                "Give a final grounded answer using only confirmed tool results. "
                "Do not claim filesystem success unless it is supported by those results."
            ),
        })
        rounds_used += 1
        repair_result, repair_text = _chat_once(
            config=config,
            messages=repair_messages,
            on_token=on_token,
            should_stop=should_stop,
        )

    repaired_evaluation = evaluate_filesystem_guardrail(
        user_text=user_text,
        assistant_text=repair_text,
        evidence=evidence,
        sandbox_root=config.sandbox_root,
    )
    if repaired_evaluation.triggered:
        return {
            "assistant_text": repair_text,
            "result": repair_result,
            "content": _deterministic_guardrail_failure_message(evaluation=repaired_evaluation),
            "repaired": False,
            "failed": True,
            "rounds_used": rounds_used,
        }

    visible = strip_tool_call_markup(repair_text).strip()
    if not visible:
        visible = "Filesystem step repaired and confirmed through file-tool evidence."
    return {
        "assistant_text": repair_text,
        "result": repair_result,
        "content": visible,
        "repaired": True,
        "failed": False,
        "rounds_used": rounds_used,
    }
