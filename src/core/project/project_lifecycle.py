"""
FILE: project_lifecycle.py
ROLE: Project detachment workflow owner (project + sessions).
WHAT IT OWNS:
  - detach: final snapshot → archive sidecar → vault registration → sidecar removal
            → engine state reset

This module owns the DETACH WORKFLOW DECISION — what constitutes a valid detach,
what order the steps execute, and what state is cleared when done.
Engine.detach_project() delegates here; project_command_handler also calls
engine.detach_project() and never bypasses this module.

Domain: project + sessions (2 domains — valid manager)
"""

from __future__ import annotations

from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.engine import Engine


def detach(
    engine: "Engine",
    on_progress: Callable[[str], None] | None = None,
    keep_sidecar: bool = False,
) -> dict:
    """Run the full project detachment sequence.

    Steps:
      1. Final VCS snapshot (non-fatal if fails)
      2. Archive .mindshard/ sidecar to vault directory
      3. Register archive entry in the memory vault
      4. Optionally remove .mindshard/ from working copy
      5. Clear engine runtime state (vcs, project_meta, sandbox_root)

    Returns a result dict with keys: success, error, archive_path,
    sidecar_retained, project_name.
    """
    from src.core.project.project_archiver import archive_sidecar, remove_sidecar
    from src.core.vcs.mindshard_vcs import MindshardVCS
    from src.core.runtime.runtime_logger import get_logger

    log = get_logger("project_lifecycle")
    result: dict = {
        "success": False,
        "error": None,
        "archive_path": "",
        "sidecar_retained": keep_sidecar,
    }

    if not engine.config.sandbox_root:
        result["error"] = "No project attached"
        return result

    # 1. Final VCS snapshot
    snap_hash = None
    if engine.vcs.is_attached:
        try:
            snap_hash = engine.vcs.snapshot("Final snapshot — MindshardAGENT detaching")
        except Exception as e:
            log.warning("Final snapshot failed: %s", e)

    if on_progress:
        on_progress("Archiving .mindshard/ ...")

    # 2. Archive sidecar
    archive_result = archive_sidecar(
        engine.config.sandbox_root,
        engine.vault.vault_dir,
        final_snapshot_hash=snap_hash,
    )
    if not archive_result["success"]:
        result["error"] = archive_result.get("error", "Archive failed")
        return result

    if on_progress:
        on_progress("Registering in memory vault ...")

    # 3. Register in vault
    meta_data: dict = {}
    if engine.project_meta:
        meta_data = {
            "project_root": engine.config.sandbox_root,
            "source_path": engine.project_meta.source_path or "",
            "profile": engine.project_meta.profile,
            "project_purpose": engine.project_meta.get("project_purpose", ""),
            "current_goal": engine.project_meta.get("current_goal", ""),
        }
    engine.vault.register(archive_result, meta_data)

    if not keep_sidecar:
        if on_progress:
            on_progress("Removing .mindshard/ ...")

        # 4. Remove sidecar
        removed = remove_sidecar(engine.config.sandbox_root)
        if not removed:
            result["error"] = "Archive saved but sidecar removal failed"
            result["archive_path"] = archive_result["archive_path"]
            return result

    # 5. Clear runtime state
    engine.vcs = MindshardVCS()
    engine.project_meta = None
    engine.config.sandbox_root = ""

    result["success"] = True
    result["archive_path"] = archive_result["archive_path"]
    result["project_name"] = archive_result["project_name"]
    return result
