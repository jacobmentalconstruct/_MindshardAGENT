"""Prompt Lab bridge callbacks for the main app."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from src.core.prompt_lab.operation_log import PromptLabOperationLog
from src.core.prompt_lab.paths import resolve_prompt_lab_paths
from src.core.prompt_lab.runtime_loader import describe_active_prompt_lab_runtime
from src.prompt_lab.workbench import launch_prompt_lab_workbench_process

if TYPE_CHECKING:
    from src.app_state import AppState


_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _prompt_lab_project_root(s: AppState) -> Path:
    config = getattr(s, "config", None)
    sandbox_root = str(getattr(config, "sandbox_root", "") or "").strip()
    if sandbox_root:
        return Path(sandbox_root).resolve()
    return _PROJECT_ROOT


def _operation_log(project_root: Path) -> PromptLabOperationLog:
    return PromptLabOperationLog(resolve_prompt_lab_paths(project_root).operations_log_path)


def refresh_prompt_lab_summary(s: AppState, *, announce: bool = False) -> str:
    project_root = _prompt_lab_project_root(s)
    summary = describe_active_prompt_lab_runtime(project_root)
    if s.ui_facade is not None:
        s.ui_facade.set_prompt_lab_summary(summary)
    _operation_log(project_root).record(
        channel="app",
        action="refresh_prompt_lab_summary",
        status="ok",
        details={"announced": bool(announce), "project_root": str(project_root)},
    )
    if announce:
        s.activity.info("prompt_lab", "Prompt Lab active package summary reloaded")
    return summary


def open_prompt_lab_surface(s: AppState) -> None:
    project_root = _prompt_lab_project_root(s)
    err = launch_prompt_lab_workbench_process(project_root)
    if err:
        _operation_log(project_root).record(
            channel="app",
            action="open_prompt_lab_surface",
            status="error",
            details={"message": str(err), "project_root": str(project_root)},
        )
        s.activity.error("prompt_lab", f"Could not open Prompt Lab workbench: {err}")
        return
    _operation_log(project_root).record(
        channel="app",
        action="open_prompt_lab_surface",
        status="ok",
        details={"project_root": str(project_root)},
    )
    s.activity.info("prompt_lab", "Opened Prompt Lab workbench")
