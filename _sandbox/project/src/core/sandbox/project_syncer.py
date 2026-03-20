"""Project sync-back — applies sandbox/project/ changes to the real source tree.

Workflow:
    1. User clicks "Load Self" → project_loader copies source into sandbox/project/
    2. Agent reads/modifies files in sandbox/project/
    3. User clicks "Sync Back" → this module diffs and applies changes

Safety:
    - Always generates a diff summary BEFORE writing
    - Writes a sync manifest to _sandbox/_logs/sync_log.jsonl
    - Never touches files outside the project root
    - Skips _sandbox, venv, __pycache__, .git directories
"""

import json
import shutil
import filecmp
from pathlib import Path
from typing import Any

from src.core.utils.clock import utc_iso
from src.core.runtime.runtime_logger import get_logger

log = get_logger("project_syncer")

# Directories that should never be synced back
_NEVER_SYNC = {
    "venv", ".venv", "__pycache__", ".git", ".idea", ".vscode",
    "_sandbox", "node_modules", ".mypy_cache", ".pytest_cache",
}

# Extensions that should never be synced back
_NEVER_SYNC_EXT = {".pyc", ".pyo", ".db", ".db-shm", ".db-wal", ".log", ".jsonl"}


def diff_sandbox_to_source(
    sandbox_root: str | Path,
    project_root: str | Path,
    target_name: str = "project",
) -> dict[str, Any]:
    """Compare sandbox/project/ against real source tree.

    Returns:
        {
            "added": [relative paths of new files],
            "modified": [relative paths of changed files],
            "removed": [relative paths deleted in sandbox],
            "unchanged": int,
            "sandbox_dir": str,
            "project_dir": str,
        }
    """
    sandbox_dir = Path(sandbox_root).resolve() / target_name
    source_dir = Path(project_root).resolve()

    if not sandbox_dir.exists():
        return {"error": "No project loaded in sandbox", "added": [],
                "modified": [], "removed": [], "unchanged": 0,
                "sandbox_dir": str(sandbox_dir), "project_dir": str(source_dir)}

    added = []
    modified = []
    removed = []
    unchanged = 0

    # Files in sandbox copy
    sandbox_files = set()
    for f in sandbox_dir.rglob("*"):
        if f.is_file() and _should_sync(f.relative_to(sandbox_dir)):
            rel = str(f.relative_to(sandbox_dir))
            sandbox_files.add(rel)

            source_file = source_dir / rel
            if not source_file.exists():
                added.append(rel)
            elif not filecmp.cmp(str(f), str(source_file), shallow=False):
                modified.append(rel)
            else:
                unchanged += 1

    # Files in source but not in sandbox (deleted by agent)
    for f in source_dir.rglob("*"):
        if f.is_file() and _should_sync(f.relative_to(source_dir)):
            rel = str(f.relative_to(source_dir))
            if rel not in sandbox_files:
                removed.append(rel)

    return {
        "added": sorted(added),
        "modified": sorted(modified),
        "removed": sorted(removed),
        "unchanged": unchanged,
        "sandbox_dir": str(sandbox_dir),
        "project_dir": str(source_dir),
    }


def apply_sync(
    sandbox_root: str | Path,
    project_root: str | Path,
    target_name: str = "project",
    apply_deletes: bool = False,
) -> dict[str, Any]:
    """Apply sandbox changes back to the real source tree.

    Args:
        sandbox_root: Sandbox root directory
        project_root: Real project root
        target_name: Subfolder name in sandbox
        apply_deletes: If True, also delete files that were removed in sandbox

    Returns:
        Summary dict with counts and the list of affected files.
    """
    diff = diff_sandbox_to_source(sandbox_root, project_root, target_name)
    if diff.get("error"):
        return diff

    sandbox_dir = Path(sandbox_root).resolve() / target_name
    source_dir = Path(project_root).resolve()

    applied_add = []
    applied_mod = []
    applied_del = []
    errors = []

    # Copy new files
    for rel in diff["added"]:
        try:
            src = sandbox_dir / rel
            dst = source_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            applied_add.append(rel)
        except Exception as e:
            errors.append({"file": rel, "op": "add", "error": str(e)})

    # Copy modified files
    for rel in diff["modified"]:
        try:
            src = sandbox_dir / rel
            dst = source_dir / rel
            shutil.copy2(src, dst)
            applied_mod.append(rel)
        except Exception as e:
            errors.append({"file": rel, "op": "modify", "error": str(e)})

    # Delete removed files (only if explicitly requested)
    if apply_deletes:
        for rel in diff["removed"]:
            try:
                dst = source_dir / rel
                if dst.exists():
                    dst.unlink()
                    applied_del.append(rel)
            except Exception as e:
                errors.append({"file": rel, "op": "delete", "error": str(e)})

    result = {
        "added": applied_add,
        "modified": applied_mod,
        "deleted": applied_del,
        "errors": errors,
        "total_applied": len(applied_add) + len(applied_mod) + len(applied_del),
        "skipped_deletes": len(diff["removed"]) if not apply_deletes else 0,
    }

    log.info("Sync complete: +%d ~%d -%d (%d errors)",
             len(applied_add), len(applied_mod), len(applied_del), len(errors))

    return result


def log_sync(sandbox_root: str | Path, sync_result: dict[str, Any],
             direction: str = "sandbox_to_source") -> None:
    """Append a sync event to the sync log (JSON-lines)."""
    log_path = Path(sandbox_root).resolve() / "_logs" / "sync_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "ts": utc_iso(),
        "direction": direction,
        "added": sync_result.get("added", []),
        "modified": sync_result.get("modified", []),
        "deleted": sync_result.get("deleted", []),
        "errors": sync_result.get("errors", []),
        "total_applied": sync_result.get("total_applied", 0),
    }

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def get_sync_log(sandbox_root: str | Path, limit: int = 20) -> list[dict]:
    """Read recent sync log entries."""
    log_path = Path(sandbox_root).resolve() / "_logs" / "sync_log.jsonl"
    if not log_path.exists():
        return []
    entries = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries[-limit:]


def _should_sync(rel_path: Path) -> bool:
    """Check if a relative path should be included in sync."""
    parts = rel_path.parts
    if any(p in _NEVER_SYNC for p in parts):
        return False
    if rel_path.suffix in _NEVER_SYNC_EXT:
        return False
    return True
