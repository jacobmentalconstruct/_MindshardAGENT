"""Registry and dispatcher for agent execution loops."""

from __future__ import annotations

from src.core.agent.loop_selector import select_loop_mode
from src.core.agent.loop_types import LoopRequest, LoopRunner
from src.core.runtime.activity_stream import ActivityStream


class LoopManager:
    def __init__(self, activity: ActivityStream):
        self._activity = activity
        self._loops: dict[str, LoopRunner] = {}
        self._active_loop_id: str = ""

    def register(self, loop: LoopRunner) -> None:
        self._loops[loop.loop_id] = loop

    def loop_ids(self) -> list[str]:
        return sorted(self._loops)

    @property
    def active_loop_id(self) -> str:
        return self._active_loop_id

    def run(self, request: LoopRequest) -> str:
        from src.core.agent.loop_types import TOOL_AGENT_LOOP
        has_tools = TOOL_AGENT_LOOP in self._loops
        loop_id = select_loop_mode(request.user_text, request.mode_hint, has_tools=has_tools)
        loop = self._loops.get(loop_id)
        if loop is None:
            loop_id = next(iter(self._loops), "")
            loop = self._loops.get(loop_id) if loop_id else None
        if loop is None:
            raise RuntimeError("No execution loops are registered")

        self._active_loop_id = loop.loop_id
        self._activity.info("loop", f"Selected loop: {loop.loop_id}")
        loop.run(request)
        return loop.loop_id

    def request_stop(self) -> None:
        loop = self._loops.get(self._active_loop_id)
        if loop is not None:
            loop.request_stop()
