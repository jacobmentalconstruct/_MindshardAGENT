"""Planner-only loop for explicit planning requests."""

from __future__ import annotations

import threading

from src.core.agent.execution_planner import run_execution_planner
from src.core.agent.loop_types import LoopRequest, PLANNER_ONLY_LOOP
from src.core.config.app_config import AppConfig
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.runtime_logger import get_logger
from src.core.sandbox.tool_catalog import ToolCatalog

log = get_logger("planner_only_loop")


class PlannerOnlyLoop:
    loop_id = PLANNER_ONLY_LOOP

    def __init__(
        self,
        config: AppConfig,
        activity: ActivityStream,
        tool_catalog: ToolCatalog,
        sandbox_root_getter,
        active_project_getter,
    ):
        self._config = config
        self._activity = activity
        self._tool_catalog = tool_catalog
        self._sandbox_root_getter = sandbox_root_getter
        self._active_project_getter = active_project_getter

    def run(self, request: LoopRequest) -> None:
        def _worker():
            try:
                planner_result = run_execution_planner(
                    config=self._config,
                    activity=self._activity,
                    tool_catalog=self._tool_catalog,
                    user_text=request.user_text,
                    sandbox_root=self._sandbox_root_getter(),
                    active_project=self._active_project_getter(),
                )
                if not planner_result or not planner_result.plan_text:
                    if request.on_error:
                        request.on_error("Planner did not produce a plan")
                    return
                if request.on_complete:
                    request.on_complete({
                        "content": planner_result.plan_text,
                        "metadata": {
                            "model": planner_result.model_name,
                            "tokens_in": f"~{planner_result.tokens_in}",
                            "tokens_out": f"~{planner_result.tokens_out}",
                            "time": f"{planner_result.wall_ms:.0f}ms",
                            "rounds": 1,
                            "loop_mode": self.loop_id,
                            "planning_used": True,
                            "planner_model": planner_result.model_name,
                        },
                        "history_addition": [
                            {"role": "user", "content": request.user_text},
                            {"role": "assistant", "content": planner_result.plan_text},
                        ],
                    })
            except Exception as exc:
                log.exception("Planner-only loop failed")
                if request.on_error:
                    request.on_error(str(exc))

        threading.Thread(target=_worker, daemon=True, name="planner-only-loop").start()

    def request_stop(self) -> None:
        return
