"""Binding persistence service."""

from __future__ import annotations

from .operation_log import PromptLabOperationLog
from .contracts import BindingRecord
from .storage import PromptLabStorage


class BindingService:
    def __init__(self, storage: PromptLabStorage, *, operation_log: PromptLabOperationLog | None = None):
        self.storage = storage
        self._operation_log = operation_log

    def list_bindings(self) -> list[dict[str, str]]:
        items = self.storage.list_design_objects("binding_record")
        if self._operation_log is not None:
            self._operation_log.record(
                channel="service",
                action="list_bindings",
                status="ok",
                details={"count": len(items)},
            )
        return items

    def get_binding(self, binding_id: str) -> BindingRecord:
        binding = self.storage.load_design_object("binding_record", binding_id)
        if self._operation_log is not None:
            self._operation_log.record(
                channel="service",
                action="get_binding",
                status="ok",
                details={"binding_id": binding_id},
            )
        return binding

    def save_binding(self, binding: BindingRecord) -> BindingRecord:
        saved = self.storage.save_binding_record(binding)
        if self._operation_log is not None:
            self._operation_log.record(
                channel="service",
                action="save_binding",
                status="ok",
                details={"binding_id": saved.id},
            )
        return saved

    def list_bindings_for_plan(self, execution_plan_id: str) -> list[BindingRecord]:
        bindings: list[BindingRecord] = []
        for item in self.list_bindings():
            if not item["id"]:
                continue
            binding = self.get_binding(item["id"])
            if binding.execution_plan_id == execution_plan_id:
                bindings.append(binding)
        if self._operation_log is not None:
            self._operation_log.record(
                channel="service",
                action="list_bindings_for_plan",
                status="ok",
                details={"plan_id": execution_plan_id, "count": len(bindings)},
            )
        return bindings
