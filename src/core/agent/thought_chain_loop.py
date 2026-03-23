"""Loop adapter for Cannibalistic Thought Chain planning."""

from __future__ import annotations

from src.core.agent.loop_types import LoopRequest, THOUGHT_CHAIN_LOOP
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

    def run(self, request: LoopRequest) -> None:
        chain = ThoughtChain(self._config, self._activity)

        def _on_complete(result: dict) -> None:
            tasks = result.get("tasks", [])
            if tasks:
                lines = [
                    f"{task['number']}. {'[' + task['complexity'] + '] ' if task.get('complexity') else ''}{task['text']}"
                    for task in tasks
                ]
                content = "Task list:\n" + "\n".join(lines)
            else:
                content = result.get("final_text", "")

            if request.on_complete:
                request.on_complete({
                    "content": content,
                    "metadata": {
                        "model": resolve_model_for_role(self._config, PLANNER_ROLE),
                        "tokens_in": "?",
                        "tokens_out": "?",
                        "time": "?",
                        "rounds": result.get("depth", self._depth),
                        "loop_mode": self.loop_id,
                        "thought_chain_rounds": result.get("depth", self._depth),
                        "task_count": len(tasks),
                    },
                    "history_addition": [
                        {"role": "user", "content": request.user_text},
                        {"role": "assistant", "content": content},
                    ],
                })

        chain.run(
            goal=request.user_text,
            depth=self._depth,
            on_complete=_on_complete,
            on_error=request.on_error,
        )

    def request_stop(self) -> None:
        return
