"""
FILE: sync_command_handler.py
ROLE: Sync-to-source command orchestrator (project + vcs).
WHAT IT OWNS:
  - sync_to_source: diff sandbox against source, confirm with user, apply changes,
    record journal entry, and optionally snapshot via VCS.

This module owns the SYNC WORKFLOW DECISION — what constitutes a valid sync,
how to present diffs to the user, and what to do after applying changes.
It delegates diff/apply/log mechanics to project_syncer in sandbox domain.

Domains: project + vcs (2 — valid manager)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import src.core.runtime.action_journal as aj

if TYPE_CHECKING:
    from src.app_state import AppState


def sync_to_source(s: AppState) -> None:
    """Diff the current sandbox against its source path, confirm, and apply.

    Owns the full sync workflow:
      1. Resolve source_path from project meta — abort if unavailable
      2. Compute diff via project_syncer
      3. Present summary to user with messagebox confirmation
      4. Apply changes (no deletes for safety)
      5. Record journal entry
      6. Snapshot via VCS if attached
    """
    from src.core.sandbox.project_syncer import diff_sandbox_to_source, apply_sync, log_sync
    from tkinter import messagebox

    sync_source = None
    if s.engine.project_meta:
        sync_source = s.engine.project_meta.source_path
    if not sync_source:
        s.activity.info("sync", "No source_path set — in-place project, sync unavailable")
        if s.ui_facade:
            s.ui_facade.post_system_message(
                "Sync Back is unavailable for in-place projects (no original source path configured)."
            )
        return

    diff = diff_sandbox_to_source(s.config.sandbox_root, sync_source, target_name="")

    if diff.get("error"):
        s.activity.error("sync", diff["error"])
        if s.ui_facade:
            s.ui_facade.post_system_message(f"Sync failed: {diff['error']}")
        return

    n_add = len(diff["added"])
    n_mod = len(diff["modified"])
    n_del = len(diff["removed"])

    if n_add == 0 and n_mod == 0 and n_del == 0:
        s.activity.info("sync", "No changes to sync — project matches source")
        if s.ui_facade:
            s.ui_facade.post_system_message("No changes detected — project matches source.")
        return

    summary_lines = []
    if n_add:
        summary_lines.append(f"  + {n_add} new file(s): {', '.join(diff['added'][:5])}")
        if n_add > 5:
            summary_lines.append(f"    ... and {n_add - 5} more")
    if n_mod:
        summary_lines.append(f"  ~ {n_mod} modified: {', '.join(diff['modified'][:5])}")
        if n_mod > 5:
            summary_lines.append(f"    ... and {n_mod - 5} more")
    if n_del:
        summary_lines.append(f"  - {n_del} deleted: {', '.join(diff['removed'][:5])}")
        if n_del > 5:
            summary_lines.append(f"    ... and {n_del - 5} more")

    summary_text = "\n".join(summary_lines)
    proceed = messagebox.askyesno(
        "Sync Back to Source",
        f"Apply project changes to source at:\n{sync_source}\n\n{summary_text}\n\n"
        f"Deletions will NOT be applied (safety).\n"
        f"This overwrites real source files.",
    )
    if not proceed:
        s.activity.info("sync", "Sync cancelled by user")
        return

    result = apply_sync(s.config.sandbox_root, sync_source, target_name="", apply_deletes=False)
    log_sync(s.config.sandbox_root, result, direction="sandbox_to_source")

    total = result["total_applied"]
    errors = len(result["errors"])
    s.activity.info(
        "sync",
        f"Sync complete: +{len(result['added'])} ~{len(result['modified'])} ({errors} errors)",
    )
    if s.ui_facade:
        s.ui_facade.post_system_message(
            f"Synced {total} file(s) back to source. "
            f"+{len(result['added'])} new, ~{len(result['modified'])} modified. "
            f"{f'{errors} error(s).' if errors else 'No errors.'}"
        )

    if s.engine.journal:
        s.engine.journal.record(
            aj.PROJECT_SYNC,
            f"Synced {total} files: +{len(result['added'])} ~{len(result['modified'])}",
            {
                "added": result["added"],
                "modified": result["modified"],
                "errors": result["errors"],
            },
        )

    if s.engine.vcs.is_attached:
        snap_msg = f"Post-sync snapshot: +{len(result['added'])} ~{len(result['modified'])} files"
        try:
            commit_hash = s.engine.vcs.snapshot(snap_msg)
            if commit_hash:
                s.activity.info("vcs", f"Snapshot committed: {commit_hash[:8]}")
        except Exception as vcs_err:
            s.log.warning("VCS snapshot failed: %s", vcs_err)
