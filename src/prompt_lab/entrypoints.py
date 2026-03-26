"""Prompt Lab entrypoint skeletons.

Prompt Lab is a separate app-owned subsystem. These entrypoints are intentionally
minimal in the scaffold tranche and should remain import-safe.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.core.prompt_lab.services import PromptLabServiceBundle, build_prompt_lab_services
from src.core.prompt_lab.storage import ensure_prompt_lab_directories


@dataclass
class PromptLabEntrypoints:
    project_root: Path
    services: PromptLabServiceBundle


def build_prompt_lab_entrypoints(project_root: str | Path) -> PromptLabEntrypoints:
    root = Path(project_root).resolve()
    ensure_prompt_lab_directories(root)
    return PromptLabEntrypoints(
        project_root=root,
        services=build_prompt_lab_services(root),
    )
