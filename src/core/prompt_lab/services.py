"""Service bundle for Prompt Lab Phase 1A.

Prompt Lab stays service-first here. We do not force a separate manager layer
until stateful coordination proves it is needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .storage import PromptLabStorage, build_prompt_lab_storage
from .validation import validate_prompt_lab_state


@dataclass
class PromptLabServiceBundle:
    """Minimal service registry for Prompt Lab orchestration and CLI use."""

    storage: PromptLabStorage
    validate_state: Callable[[str | Path | PromptLabStorage], Any]
    metadata: dict[str, Any] = field(default_factory=dict)


def build_prompt_lab_services(project_root: str | Path) -> PromptLabServiceBundle:
    storage = build_prompt_lab_storage(project_root)
    return PromptLabServiceBundle(
        storage=storage,
        validate_state=validate_prompt_lab_state,
        metadata={
            "status": "phase_1a",
            "persistence": {
                "design_objects": "json_canonical",
                "history": "sqlite_canonical",
            },
            "cli_mode": "inspection_only",
            "runtime_rule": "main_app_consumes_active_published_only",
            "architecture_style": "service_first_manager_optional",
        },
    )
