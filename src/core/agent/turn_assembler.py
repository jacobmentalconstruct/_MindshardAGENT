"""Turn assembler — builds the message list for a single agent turn.

Responsibilities:
  - STM sliding window (recent turns kept verbatim)
  - Evidence bag falloff (ingest old turns, build summary)
  - Goal setting from planner
  - Token budget guard (register, enforce, report)
  - Final message assembly from trimmed components

This module owns memory + context assembly. It does NOT own streaming,
tool dispatch, or model invocation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.core.agent.context_budget import ContextBudgetGuard
from src.core.agent.prompt_builder import build_messages
from src.core.config.app_config import AppConfig
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.runtime_logger import get_logger

log = get_logger("turn_assembler")


@dataclass
class AssembledTurn:
    """Result of assembling a turn's messages."""
    messages: list[dict[str, str]]
    budget_report: Any  # BudgetReport from ContextBudgetGuard
    bag_summary: str
    window_size: int
    falloff_count: int


def assemble_turn(
    *,
    config: AppConfig,
    activity: ActivityStream,
    chat_history: list[dict[str, str]],
    user_text: str,
    system_prompt: str,
    planner_messages: list[dict[str, str]],
    stage_messages: list[dict[str, str]],
    planner_text: str,
    evidence_bag=None,
) -> AssembledTurn:
    """Build the final message list for an agent turn.

    Handles STM windowing, evidence bag falloff/summary, budget guarding,
    and message assembly. Returns an AssembledTurn with everything the
    streaming loop needs.
    """
    window_size = config.stm_window_size
    bag_summary = ""

    # ── STM sliding window + evidence bag falloff ──
    if (
        evidence_bag
        and config.evidence_bag_enabled
        and len(chat_history) > window_size
    ):
        falloff = chat_history[:-window_size]
        window = chat_history[-window_size:]
        # Ingest fallen-off turns into evidence bag (full text preserved)
        try:
            n_ingested = evidence_bag.ingest_falloff(falloff)
            if n_ingested:
                activity.info(
                    "evidence", f"Ingested {n_ingested} turns into evidence bag"
                )
        except Exception as exc:
            log.warning("Evidence bag ingest failed: %s", exc)
        # Build compact summary for prompt injection
        try:
            bag_summary = evidence_bag.build_summary(
                user_text,
                token_budget=config.evidence_bag_summary_budget,
            )
        except Exception as exc:
            log.warning("Evidence bag summary failed: %s", exc)
    else:
        window = list(chat_history)

    # Set goal from planner if available (not every turn)
    if evidence_bag and planner_text:
        try:
            evidence_bag.set_goal(planner_text[:500])
        except Exception as exc:
            log.warning("Evidence bag set_goal failed: %s", exc)

    # ── Token budget guard ──
    budget = ContextBudgetGuard(
        max_tokens=config.max_context_tokens,
        reserve_ratio=config.budget_reserve_ratio,
    )
    budget.register("system_prompt", system_prompt, priority=0)

    planner_text_block = planner_messages[0]["content"] if planner_messages else ""
    budget.register("planner", planner_text_block, priority=2)

    stage_text_block = stage_messages[0]["content"] if stage_messages else ""
    budget.register("stage_context", stage_text_block, priority=4)

    bag_summary_block = (
        "## Prior Context (Evidence Bag)\n"
        "The following is a summary of earlier conversation that is no longer "
        "in your active window. The full evidence is preserved and retrievable. "
        "Do NOT treat this as complete — if you need specifics, say so.\n\n"
        f"{bag_summary}"
    ) if bag_summary else ""
    budget.register("bag_summary", bag_summary_block, priority=5)
    budget.register("rag_context", "", priority=6)

    history = list(window)
    history.append({"role": "user", "content": user_text})
    budget.register("stm_window", history, priority=3, is_message_list=True)

    trimmed = budget.enforce()
    budget_report = budget.budget_report()

    # Log budget data
    if budget_report.over_budget:
        activity.warn(
            "budget",
            f"Token budget trimmed: {budget_report.total_before_trim} -> "
            f"{budget_report.total_after_trim}/{budget_report.available_tokens} tokens"
        )
        if budget_report.would_benefit_from_multipass:
            activity.warn(
                "budget",
                "Multi-pass would preserve more context (>30% trimmed)"
            )
    else:
        activity.info(
            "budget",
            f"Token budget: {budget_report.total_before_trim}/"
            f"{budget_report.available_tokens} tokens"
        )

    # ── Assemble messages from trimmed components ──
    messages = build_messages(trimmed["system_prompt"], trimmed["stm_window"])
    injections: list[dict[str, str]] = []
    if trimmed["planner"]:
        injections.append({"role": "system", "content": trimmed["planner"]})
    if trimmed["stage_context"]:
        injections.append({"role": "system", "content": trimmed["stage_context"]})
    if trimmed["bag_summary"]:
        injections.append({"role": "system", "content": trimmed["bag_summary"]})
    if injections:
        messages[1:1] = injections

    falloff_count = len(chat_history) - len(window) if len(chat_history) > len(window) else 0

    return AssembledTurn(
        messages=messages,
        budget_report=budget_report,
        bag_summary=bag_summary,
        window_size=window_size,
        falloff_count=falloff_count,
    )
