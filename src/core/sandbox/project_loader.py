"""Project loader — copies app source into the sandbox for agent self-iteration.

Clones the AgenticTOOLBOX source tree into _sandbox/project/ so the
sandboxed agent can read, modify, and test its own code. Excludes
runtime artifacts (venv, __pycache__, .db, logs, etc).

Usage from CLI or app:
    from src.core.sandbox.project_loader import load_project, snapshot_diff
    load_project(project_root, sandbox_root)
    diff = snapshot_diff(sandbox_root)
"""

import shutil
from pathlib import Path

from src.core.runtime.runtime_logger import get_logger

log = get_logger("project_loader")

# Directories to skip when copying
_SKIP_DIRS = {
    "venv", ".venv", "__pycache__", ".git", ".idea", ".vscode",
    "_sandbox", "node_modules", ".mypy_cache", ".pytest_cache",
}

# File patterns to skip
_SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".db", ".db-shm", ".db-wal",
    ".log", ".jsonl", ".egg-info",
}

# Specific files to skip
_SKIP_FILES = {
    "app_config.json",  # don't copy runtime config
}


def load_project(project_root: str | Path, sandbox_root: str | Path,
                 target_name: str = "project") -> Path:
    """Copy the app source tree into the sandbox.

    Args:
        project_root: The AgenticTOOLBOX root directory
        sandbox_root: The sandbox root directory
        target_name: Subfolder name inside sandbox (default: "project")

    Returns:
        Path to the project copy inside the sandbox
    """
    src = Path(project_root).resolve()
    dest = Path(sandbox_root).resolve() / target_name

    # Clean previous copy if exists
    if dest.exists():
        shutil.rmtree(dest)

    dest.mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped = 0

    for item in _walk_filtered(src):
        rel = item.relative_to(src)
        target = dest / rel

        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            copied += 1

    log.info("Project loaded: %d files copied to %s", copied, dest)
    return dest


def _walk_filtered(root: Path):
    """Walk the source tree, yielding files that pass the filter."""
    for item in root.rglob("*"):
        # Skip excluded directories
        parts = item.relative_to(root).parts
        if any(p in _SKIP_DIRS for p in parts):
            continue

        # Skip excluded extensions
        if item.is_file() and item.suffix in _SKIP_EXTENSIONS:
            continue

        # Skip specific files
        if item.is_file() and item.name in _SKIP_FILES:
            continue

        yield item


def get_project_path(sandbox_root: str | Path,
                     target_name: str = "project") -> Path | None:
    """Get the path to the project copy, or None if not loaded."""
    p = Path(sandbox_root).resolve() / target_name
    return p if p.exists() else None


def list_project_files(sandbox_root: str | Path,
                       target_name: str = "project") -> list[str]:
    """List all files in the sandbox project copy (relative paths)."""
    project_dir = Path(sandbox_root).resolve() / target_name
    if not project_dir.exists():
        return []
    files = []
    for f in sorted(project_dir.rglob("*")):
        if f.is_file():
            files.append(str(f.relative_to(project_dir)))
    return files


def snapshot_manifest(sandbox_root: str | Path,
                      target_name: str = "project") -> dict[str, int]:
    """Build a manifest of file paths -> sizes for change detection.

    Returns:
        Dict mapping relative paths to file sizes in bytes.
    """
    project_dir = Path(sandbox_root).resolve() / target_name
    if not project_dir.exists():
        return {}
    manifest = {}
    for f in project_dir.rglob("*"):
        if f.is_file():
            rel = str(f.relative_to(project_dir))
            manifest[rel] = f.stat().st_size
    return manifest


def diff_manifests(before: dict[str, int],
                   after: dict[str, int]) -> dict[str, list[str]]:
    """Compare two manifests and return changes.

    Returns:
        Dict with keys: "added", "removed", "modified"
    """
    added = [f for f in after if f not in before]
    removed = [f for f in before if f not in after]
    modified = [f for f in after if f in before and after[f] != before[f]]
    return {"added": sorted(added), "removed": sorted(removed),
            "modified": sorted(modified)}
