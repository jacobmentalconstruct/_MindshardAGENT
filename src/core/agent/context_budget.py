"""Token budget guard and context assembly instrumentation.

Ensures the total prompt stays within max_context_tokens before hitting the model.
Trims components in priority order (least valuable first). Logs detailed token
breakdowns for data gathering toward multi-pass prompt splitting.

Usage:
    guard = ContextBudgetGuard(max_tokens=8192, reserve_ratio=0.15)
    guard.register("system_prompt", system_text, priority=0)  # never trim
    guard.register("planner", planner_text, priority=1)
    guard.register("stage_context", stage_text, priority=4)
    guard.register("bag_summary", bag_text, priority=5)
    guard.register("stm_window", window_msgs, priority=3, is_message_list=True)
    guard.register("rag_context", rag_text, priority=6)  # trim first

    trimmed = guard.enforce()
    # trimmed["stm_window"] may have fewer messages
    # trimmed["rag_context"] may be shorter or empty

Multi-pass infrastructure:
    report = guard.budget_report()
    # Detailed breakdown of every component's token count, trim actions taken,
    # and whether multi-pass would have been beneficial.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.core.runtime.runtime_logger import get_logger
from src.core.utils.text_metrics import estimate_tokens

log = get_logger("context_budget")


@dataclass
class BudgetSlot:
    """A named component of the prompt with its token cost and trim priority."""
    name: str
    content: Any           # str or list[dict] for message lists
    priority: int          # higher = trimmed first; 0 = never trim
    is_message_list: bool  # if True, content is list[dict] and trimmed by dropping oldest
    original_tokens: int = 0
    trimmed_tokens: int = 0
    was_trimmed: bool = False

    @property
    def tokens(self) -> int:
        if self.is_message_list:
            return sum(estimate_tokens(m.get("content", "")) for m in self.content)
        return estimate_tokens(self.content) if isinstance(self.content, str) else 0


@dataclass
class BudgetReport:
    """Instrumentation data for token budget decisions."""
    max_tokens: int
    reserve_tokens: int
    available_tokens: int
    total_before_trim: int
    total_after_trim: int
    over_budget: bool
    would_benefit_from_multipass: bool
    slots: list[dict] = field(default_factory=list)
    trim_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "max_tokens": self.max_tokens,
            "reserve_tokens": self.reserve_tokens,
            "available_tokens": self.available_tokens,
            "total_before_trim": self.total_before_trim,
            "total_after_trim": self.total_after_trim,
            "over_budget": self.over_budget,
            "would_benefit_from_multipass": self.would_benefit_from_multipass,
            "slots": self.slots,
            "trim_actions": self.trim_actions,
        }


class ContextBudgetGuard:
    """Enforces token budget by trimming lower-priority context components."""

    def __init__(self, max_tokens: int = 8192, reserve_ratio: float = 0.15):
        """
        Args:
            max_tokens: Hard ceiling (model's num_ctx).
            reserve_ratio: Fraction reserved for model output (0.15 = 15%).
        """
        self.max_tokens = max_tokens
        self.reserve_tokens = int(max_tokens * reserve_ratio)
        self.available = max_tokens - self.reserve_tokens
        self._slots: list[BudgetSlot] = []

    def register(
        self,
        name: str,
        content: Any,
        priority: int = 5,
        is_message_list: bool = False,
    ) -> None:
        """Register a prompt component.

        Args:
            name: Human-readable label for logging.
            content: The text (str) or message list (list[dict]).
            priority: Trim order. 0 = never trim, higher = trimmed first.
            is_message_list: If True, trimming drops oldest messages.
        """
        slot = BudgetSlot(
            name=name,
            content=content,
            priority=priority,
            is_message_list=is_message_list,
        )
        slot.original_tokens = slot.tokens
        self._slots.append(slot)

    def enforce(self) -> dict[str, Any]:
        """Trim components until total fits within budget.

        Returns dict mapping slot names to their (possibly trimmed) content.
        """
        total = sum(s.original_tokens for s in self._slots)

        if total <= self.available:
            log.debug(
                "Budget OK: %d/%d tokens (%.0f%% used)",
                total, self.available, 100 * total / self.available,
            )
            return {s.name: s.content for s in self._slots}

        log.warning(
            "Budget exceeded: %d/%d tokens — trimming",
            total, self.available,
        )

        # Sort trimmable slots by priority (highest first = trim first)
        trimmable = sorted(
            [s for s in self._slots if s.priority > 0],
            key=lambda s: -s.priority,
        )

        overage = total - self.available

        for slot in trimmable:
            if overage <= 0:
                break

            if slot.is_message_list:
                overage = self._trim_message_list(slot, overage)
            else:
                overage = self._trim_text(slot, overage)

        final_total = sum(s.tokens for s in self._slots)
        if final_total > self.available:
            log.warning(
                "Budget still over after trimming: %d/%d tokens",
                final_total, self.available,
            )

        return {s.name: s.content for s in self._slots}

    def _trim_message_list(self, slot: BudgetSlot, overage: int) -> int:
        """Drop oldest messages from a message list until overage is resolved."""
        messages = list(slot.content)
        removed = 0
        while overage > 0 and len(messages) > 2:  # keep at least 2 messages
            dropped = messages.pop(0)
            dropped_tokens = estimate_tokens(dropped.get("content", ""))
            overage -= dropped_tokens
            removed += 1

        slot.content = messages
        slot.was_trimmed = removed > 0
        slot.trimmed_tokens = slot.tokens
        if removed:
            log.info("Trimmed %s: dropped %d oldest messages", slot.name, removed)
        return overage

    def _trim_text(self, slot: BudgetSlot, overage: int) -> int:
        """Truncate text content to fit budget."""
        text = slot.content
        if not text:
            return overage

        current_tokens = estimate_tokens(text)
        target_tokens = max(0, current_tokens - overage)

        if target_tokens <= 0:
            # Remove entirely
            saved = current_tokens
            slot.content = ""
            slot.was_trimmed = True
            slot.trimmed_tokens = 0
            log.info("Trimmed %s: removed entirely (%d tokens)", slot.name, saved)
            return overage - saved

        # Truncate to target char count
        target_chars = target_tokens * 4
        slot.content = text[:target_chars] + "\n[...truncated to fit token budget]"
        slot.was_trimmed = True
        slot.trimmed_tokens = estimate_tokens(slot.content)
        saved = current_tokens - slot.trimmed_tokens
        log.info("Trimmed %s: %d -> %d tokens", slot.name, current_tokens, slot.trimmed_tokens)
        return overage - saved

    def budget_report(self) -> BudgetReport:
        """Generate instrumentation report for data gathering.

        This data feeds future multi-pass decisions: if trimming is frequent
        or aggressive, multi-pass would produce better results.
        """
        total_before = sum(s.original_tokens for s in self._slots)
        total_after = sum(s.tokens for s in self._slots)
        over = total_before > self.available
        trim_actions = [
            f"{s.name}: {s.original_tokens} -> {s.trimmed_tokens} tokens"
            for s in self._slots if s.was_trimmed
        ]

        # Multi-pass heuristic: if we trimmed > 30% of content, splitting
        # would have preserved more information
        trimmed_pct = (
            (total_before - total_after) / total_before * 100
            if total_before > 0 else 0
        )
        would_benefit = trimmed_pct > 30

        slots = [
            {
                "name": s.name,
                "priority": s.priority,
                "original_tokens": s.original_tokens,
                "final_tokens": s.tokens,
                "was_trimmed": s.was_trimmed,
                "is_message_list": s.is_message_list,
            }
            for s in self._slots
        ]

        return BudgetReport(
            max_tokens=self.max_tokens,
            reserve_tokens=self.reserve_tokens,
            available_tokens=self.available,
            total_before_trim=total_before,
            total_after_trim=total_after,
            over_budget=over,
            would_benefit_from_multipass=would_benefit,
            slots=slots,
            trim_actions=trim_actions,
        )
