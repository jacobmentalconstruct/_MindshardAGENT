"""Execution plan persistence service."""

from __future__ import annotations

from .operation_log import PromptLabOperationLog
from .contracts import ExecutionPlan
from .storage import PromptLabStorage


class ExecutionPlanService:
    def __init__(self, storage: PromptLabStorage, *, operation_log: PromptLabOperationLog | None = None):
        self.storage = storage
        self._operation_log = operation_log

    def list_plans(self) -> list[dict[str, str]]:
        items = self.storage.list_design_objects("execution_plan")
        if self._operation_log is not None:
            self._operation_log.record(
                channel="service",
                action="list_plans",
                status="ok",
                details={"count": len(items)},
            )
        return items

    def get_plan(self, plan_id: str) -> ExecutionPlan:
        plan = self.storage.load_design_object("execution_plan", plan_id)
        if self._operation_log is not None:
            self._operation_log.record(
                channel="service",
                action="get_plan",
                status="ok",
                details={"plan_id": plan_id},
            )
        return plan

    def save_plan(self, plan: ExecutionPlan) -> ExecutionPlan:
        saved = self.storage.save_execution_plan(plan)
        if self._operation_log is not None:
            self._operation_log.record(
                channel="service",
                action="save_plan",
                status="ok",
                details={"plan_id": saved.id},
            )
        return saved
