"""Planner-only loop for explicit planning requests."""

from __future__ import annotations

import threading

from src.core.agent.execution_planner import run_execution_planner
from src.core.agent.loop_types import (
    LoopRequest,
    PLANNER_ONLY_LOOP,
    STOPPED_BY_USER_MESSAGE,
    build_loop_result,
)
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
        self._stop_requested = False
        self._worker_thread: threading.Thread | None = None

    def run(self, request: LoopRequest) -> None:
        def _worker():
            try:
                self._stop_requested = False
                planner_result = run_execution_planner(
                    config=self._config,
                    activity=self._activity,
                    tool_catalog=self._tool_catalog,
                    user_text=request.user_text,
                    sandbox_root=self._sandbox_root_getter(),
                    active_project=self._active_project_getter(),
                    should_stop=lambda: self._stop_requested,
                )
                if not planner_result:
                    if self._stop_requested and request.on_complete:
                        request.on_complete(build_loop_result(
                            user_text=request.user_text,
                            content=STOPPED_BY_USER_MESSAGE,
                            loop_id=self.loop_id,
                            metadata={
                                "model": "",
                                "tokens_in": "~0",
                                "tokens_out": "~0",
                                "time": "0ms",
                                "rounds": 1,
                                "planning_used": False,
                                "planner_model": "",
                                "stopped": True,
                            },
                        ))
                    elif request.on_error:
                        request.on_error("Planner did not produce a plan")
                    return
                if not planner_result.plan_text and not planner_result.stopped:
                    if request.on_error:
                        request.on_error("Planner did not produce a plan")
                    return
                content = planner_result.plan_text or STOPPED_BY_USER_MESSAGE
                if planner_result.stopped and planner_result.plan_text:
                    content = f"{planner_result.plan_text}\n\n{STOPPED_BY_USER_MESSAGE}"
                if request.on_complete:
                    request.on_complete(build_loop_result(
                        user_text=request.user_text,
                        content=content,
                        loop_id=self.loop_id,
                        metadata={
                            "model": planner_result.model_name,
                            "tokens_in": f"~{planner_result.tokens_in}",
                            "tokens_out": f"~{planner_result.tokens_out}",
                            "time": f"{planner_result.wall_ms:.0f}ms",
                            "rounds": 1,
                            "planning_used": True,
                            "planner_model": planner_result.model_name,
                            "stopped": planner_result.stopped,
                        },
                    ))
            except Exception as exc:
                log.exception("Planner-only loop failed")
                if request.on_error:
                    request.on_error(str(exc))

        thread = threading.Thread(target=_worker, daemon=True, name="planner-only-loop")
        self._worker_thread = thread
        thread.start()

    def request_stop(self) -> None:
        self._stop_requested = True

    def join(self, timeout: float = 3.0) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)
