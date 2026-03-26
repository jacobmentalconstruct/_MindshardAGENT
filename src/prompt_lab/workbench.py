"""Dedicated Prompt Lab workbench shell stub."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.prompt_lab.entrypoints import build_prompt_lab_entrypoints


@dataclass(frozen=True)
class PromptLabWorkbenchState:
    project_root: Path
    status: str = "scaffold_only"


def build_workbench_state(project_root: str | Path) -> PromptLabWorkbenchState:
    entrypoints = build_prompt_lab_entrypoints(project_root)
    return PromptLabWorkbenchState(project_root=entrypoints.project_root)
