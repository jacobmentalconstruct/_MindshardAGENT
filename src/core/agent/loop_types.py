"""Shared types and identifiers for agent execution loops."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol


DIRECT_CHAT_LOOP = "direct_chat"
TOOL_AGENT_LOOP = "tool_agent"
PLANNER_ONLY_LOOP = "planner_only"
THOUGHT_CHAIN_LOOP = "thought_chain"
RECOVERY_AGENT_LOOP = "recovery_agent"


@dataclass(frozen=True)
class LoopRequest:
    user_text: str
    chat_history: list[dict[str, str]]
    on_token: Callable[[str], None] | None = None
    on_complete: Callable[[dict[str, Any]], None] | None = None
    on_error: Callable[[str], None] | None = None
    on_tool_start: Callable[[str], None] | None = None
    on_tool_result: Callable[[dict], None] | None = None
    mode_hint: str | None = None


class LoopRunner(Protocol):
    loop_id: str

    def run(self, request: LoopRequest) -> None:
        ...

    def request_stop(self) -> None:
        ...
