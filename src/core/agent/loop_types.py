"""Shared types, identifiers, and result helpers for agent execution loops."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol, TypedDict


DIRECT_CHAT_LOOP = "direct_chat"
TOOL_AGENT_LOOP = "tool_agent"
PLANNER_ONLY_LOOP = "planner_only"
THOUGHT_CHAIN_LOOP = "thought_chain"
RECOVERY_AGENT_LOOP = "recovery_agent"
REVIEW_JUDGE_LOOP = "review_judge"
STOPPED_BY_USER_MESSAGE = "[Stopped by user request.]"


class LoopMessage(TypedDict):
    role: str
    content: str


class LoopMetadata(TypedDict, total=False):
    model: str
    tokens_in: str
    tokens_out: str
    time: str
    rounds: int
    loop_mode: str
    stopped: bool


class LoopResult(TypedDict, total=False):
    content: str
    metadata: LoopMetadata
    history_addition: list[LoopMessage]
    prompt_build: Any


@dataclass(frozen=True)
class LoopRequest:
    user_text: str
    chat_history: list[LoopMessage]
    on_token: Callable[[str], None] | None = None
    on_complete: Callable[[LoopResult], None] | None = None
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


class JoinableLoop(Protocol):
    def join(self, timeout: float = 3.0) -> None:
        ...


def build_history_addition(user_text: str, assistant_text: str) -> list[LoopMessage]:
    return [
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": assistant_text},
    ]


def build_loop_result(
    *,
    user_text: str,
    content: str,
    loop_id: str,
    metadata: dict[str, Any] | None = None,
    prompt_build: Any | None = None,
    history_addition: list[LoopMessage] | None = None,
) -> LoopResult:
    meta: LoopMetadata = dict(metadata or {})
    meta.setdefault("loop_mode", loop_id)
    meta.setdefault("stopped", False)

    result: LoopResult = {
        "content": content,
        "metadata": meta,
        "history_addition": history_addition or build_history_addition(user_text, content),
    }
    if prompt_build is not None:
        result["prompt_build"] = prompt_build
    return result


def patch_loop_result(
    result: LoopResult | dict[str, Any],
    *,
    loop_id: str | None = None,
    user_text: str | None = None,
    content: str | None = None,
    metadata_updates: dict[str, Any] | None = None,
) -> LoopResult:
    patched: LoopResult = dict(result)
    patched_content = content if content is not None else str(patched.get("content", ""))
    meta: LoopMetadata = dict(patched.get("metadata", {}))
    if loop_id:
        meta["loop_mode"] = loop_id
    if metadata_updates:
        meta.update(metadata_updates)
    meta.setdefault("stopped", False)
    patched["content"] = patched_content
    patched["metadata"] = meta
    if user_text is not None:
        patched["history_addition"] = build_history_addition(user_text, patched_content)
    return patched
