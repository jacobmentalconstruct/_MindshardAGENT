"""Recovery-agent execution loop.

Wraps the tool-agent (ResponseLoop) with a recovery-framed system message.
Use when the agent needs to approach a task with explicit failure awareness
and a mandate to try a different strategy than usual.

Selected automatically by the loop_selector when user text contains phrases
like "try a different approach" or "that didn't work", or via mode_hint="recovery_agent".
"""

from __future__ import annotations

from src.core.agent.loop_types import RECOVERY_AGENT_LOOP, LoopRequest, LoopRunner, patch_loop_result
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.runtime_logger import get_logger

log = get_logger("recovery_agent_loop")

_RECOVERY_PREAMBLE = (
    "You are operating in RECOVERY MODE. A previous attempt at this task failed "
    "or produced an unsatisfactory result. Your job is to try a materially "
    "different approach:\n"
    "- Do NOT repeat the same tool calls or strategy that failed.\n"
    "- Start by diagnosing WHY the previous attempt might have failed.\n"
    "- Propose and execute an alternative approach.\n"
    "- If you are unsure what failed, ask the user before proceeding.\n"
)


class RecoveryAgentLoop:
    """Wraps the tool-agent loop with recovery-mode framing.

    Injects a recovery preamble into the user message and delegates
    execution to the registered tool-agent (ResponseLoop). The tool-agent
    runs with full tool access so it can try new approaches freely.
    """

    loop_id = RECOVERY_AGENT_LOOP

    def __init__(
        self,
        activity: ActivityStream,
        tool_agent_loop: LoopRunner,
    ) -> None:
        self._activity = activity
        self._tool_agent = tool_agent_loop
        self._stop_requested = False

    def run(self, request: LoopRequest) -> None:
        self._stop_requested = False
        self._activity.info("loop", "Recovery agent loop selected — framing as recovery task")

        # Inject recovery preamble into the user text
        framed_text = f"{_RECOVERY_PREAMBLE}\nUSER REQUEST:\n{request.user_text}"

        # Build a modified request with the recovery-framed text and no mode_hint
        # (to avoid infinite recursion if tool_agent_loop also checks mode_hint)
        recovery_request = LoopRequest(
            user_text=framed_text,
            chat_history=request.chat_history,
            on_token=request.on_token,
            on_complete=_wrap_on_complete(request.on_complete, self.loop_id, request.user_text),
            on_error=request.on_error,
            on_tool_start=request.on_tool_start,
            on_tool_result=request.on_tool_result,
            mode_hint=None,  # let tool_agent run without further redirection
        )

        self._tool_agent.run(recovery_request)

    def request_stop(self) -> None:
        self._stop_requested = True
        self._tool_agent.request_stop()

    def join(self, timeout: float = 3.0) -> None:
        if hasattr(self._tool_agent, "join"):
            self._tool_agent.join(timeout=timeout)


def _wrap_on_complete(original_on_complete, loop_id: str, user_text: str):
    """Wrap on_complete to override the loop_mode metadata key."""
    if original_on_complete is None:
        return None

    def _wrapped(result: dict) -> None:
        original_on_complete(patch_loop_result(result, loop_id=loop_id, user_text=user_text))

    return _wrapped
