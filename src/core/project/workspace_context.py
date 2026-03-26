"""Workspace-owned project context bootstrap."""

from __future__ import annotations

from dataclasses import dataclass

from src.core.project.project_meta import ProjectMeta
from src.core.runtime.action_journal import ActionJournal
from src.core.runtime.runtime_logger import get_logger
from src.core.sandbox.workspace_layout import ensure_sidecar_dirs

log = get_logger("workspace_context")


@dataclass(frozen=True)
class WorkspaceContext:
    """Workspace-side project metadata and journaling state."""

    project_meta: ProjectMeta
    journal: ActionJournal


def initialize_workspace_context(sandbox_root: str, *, vcs) -> WorkspaceContext:
    """Initialize per-workspace sidecars and attach local VCS."""

    ensure_sidecar_dirs(sandbox_root)
    project_meta = ProjectMeta(sandbox_root)
    journal = ActionJournal(sandbox_root)

    try:
        vcs.attach(sandbox_root)
    except Exception as exc:
        log.warning("VCS attach failed: %s", exc)

    return WorkspaceContext(project_meta=project_meta, journal=journal)
