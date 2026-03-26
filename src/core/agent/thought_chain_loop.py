"""Loop adapter for Cannibalistic Thought Chain planning."""

from __future__ import annotations

from src.core.agent.loop_types import LoopRequest, THOUGHT_CHAIN_LOOP, build_loop_result
from src.core.agent.model_roles import PLANNER_ROLE, resolve_model_for_role
from src.core.agent.thought_chain import ThoughtChain
from src.core.config.app_config import AppConfig
from src.core.runtime.activity_stream import ActivityStream


class ThoughtChainLoop:
    loop_id = THOUGHT_CHAIN_LOOP

    def __init__(self, config: AppConfig, activity: ActivityStream, depth: int = 3):
        self._config = config
        self._activity = activity
        self._depth = depth
        self._chain: ThoughtChain | None = None

    def run(self, request: LoopRequest) -> None:
        chain = ThoughtChain(self._config, self._activity)
        self._chain = chain

        def _on_complete(result: dict) -> None:
            tasks = result.get("tasks", [])
            stopped = bool(result.get("stopped"))
            if tasks:
                lines = [
                    f"{task['number']}. {'[' + task['complexity'] + '] ' if task.get('complexity') else ''}{task['text']}"
                    for task in tasks
                ]
                content = "Task list:\n" + "\n".join(lines)
            else:
                content = result.get("final_text", "")
            if stopped:
                completed = int(result.get("completed_rounds", 0) or 0)
                stop_note = f"[Stopped by user request after {completed} round(s).]"
                content = f"{content}\n\n{stop_note}".strip() if content else stop_note

            if request.on_complete:
                completed_rounds = int(result.get("completed_rounds", 0) or 0)
                request.on_complete(build_loop_result(
                    user_text=request.user_text,
                    content=content,
                    loop_id=self.loop_id,
                    metadata={
                        "model": resolve_model_for_role(self._config, PLANNER_ROLE),
                        "tokens_in": "?",
                        "tokens_out": "?",
                        "time": "?",
                        "rounds": completed_rounds or result.get("depth", self._depth),
                        "thought_chain_rounds": completed_rounds or result.get("depth", self._depth),
                        "task_count": len(tasks),
                        "stopped": stopped,
                    },
                ))

        chain.run(
            goal=request.user_text,
            depth=self._depth,
            on_complete=_on_complete,
            on_error=request.on_error,
        )

    def request_stop(self) -> None:
        if self._chain is not None:
            self._chain.request_stop()

    def join(self, timeout: float = 3.0) -> None:
        if self._chain is not None:
            self._chain.join(timeout=timeout)
