"""Pre-inference context gathering — direct tool calls, no model needed.

Scans the workspace to build a structured context snapshot that downstream
stages (probes, primary model) can use without needing to discover basics
themselves.  Runs in ~100-500ms with no LLM inference.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from src.core.runtime.runtime_logger import get_logger
from src.core.sandbox.file_writer import FileWriter

log = get_logger("context_gatherer")

# Files worth auto-reading the first N lines of when detected.
_KEY_FILES = (
    "README.md", "readme.md",
    "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg",
    "package.json", "Cargo.toml", "go.mod",
    "Makefile", "CMakeLists.txt",
    "ARCHITECTURE.md", "CLAUDE.md",
)
_KEY_FILE_HEAD_LINES = 30


@dataclass(frozen=True)
class GatheredContext:
    """Result of a workspace context scan."""

    file_tree: str = ""
    file_count: int = 0
    key_file_snippets: dict[str, str] = field(default_factory=dict)
    project_brief: str = ""
    journal_summary: str = ""
    gathering_ms: float = 0.0


def gather_workspace_context(
    file_writer: FileWriter,
    active_project: str = "",
    project_meta: Any | None = None,
    journal: Any | None = None,
) -> GatheredContext:
    """Gather workspace context using direct tool calls (no model).

    Args:
        file_writer: FileWriter with sandbox access.
        active_project: Relative project path within sandbox ("" = root).
        project_meta: Optional ProjectMeta for project brief.
        journal: Optional ActionJournal for recent activity.

    Returns:
        GatheredContext with whatever could be gathered.
        Never raises — returns partial context on errors.
    """
    t0 = time.perf_counter()

    # 1. File tree
    file_tree = ""
    file_count = 0
    try:
        tree_result = file_writer.list_files(path=active_project, depth=2)
        if tree_result.get("success"):
            entries = tree_result.get("tree", [])
            file_tree = _format_tree(entries)
            file_count = _count_files(entries)
    except Exception as exc:
        log.warning("Context gather: file tree failed: %s", exc)

    # 2. Key file snippets
    key_snippets: dict[str, str] = {}
    try:
        tree_result_deep = file_writer.list_files(path=active_project, depth=1)
        if tree_result_deep.get("success"):
            root_names = {e["name"] for e in tree_result_deep.get("tree", [])}
            for kf in _KEY_FILES:
                if kf in root_names:
                    path = f"{active_project}/{kf}" if active_project else kf
                    read_result = file_writer.read_file(path)
                    if read_result.get("success"):
                        content = read_result["content"]
                        lines = content.splitlines()[:_KEY_FILE_HEAD_LINES]
                        key_snippets[kf] = "\n".join(lines)
    except Exception as exc:
        log.warning("Context gather: key file scan failed: %s", exc)

    # 3. Project brief
    project_brief = ""
    if project_meta is not None:
        try:
            project_brief = project_meta.prompt_context()
        except Exception as exc:
            log.warning("Context gather: project brief failed: %s", exc)

    # 4. Journal summary
    journal_summary = ""
    if journal is not None:
        try:
            journal_summary = journal.summary_since(n=5)
        except Exception as exc:
            log.warning("Context gather: journal summary failed: %s", exc)

    elapsed = (time.perf_counter() - t0) * 1000

    return GatheredContext(
        file_tree=file_tree,
        file_count=file_count,
        key_file_snippets=key_snippets,
        project_brief=project_brief,
        journal_summary=journal_summary,
        gathering_ms=round(elapsed, 1),
    )


def _format_tree(entries: list[dict], indent: int = 0) -> str:
    """Format a list_files tree result into a readable text tree."""
    lines: list[str] = []
    prefix = "  " * indent
    for entry in entries:
        name = entry.get("name", "?")
        etype = entry.get("type", "file")
        if etype == "dir":
            lines.append(f"{prefix}{name}/")
            children = entry.get("children", [])
            if children:
                lines.append(_format_tree(children, indent + 1))
        else:
            size = entry.get("size", 0)
            size_label = _human_size(size)
            lines.append(f"{prefix}{name} ({size_label})")
    return "\n".join(lines)


def _count_files(entries: list[dict]) -> int:
    """Count total files in a tree."""
    count = 0
    for entry in entries:
        if entry.get("type") == "file":
            count += 1
        for child in entry.get("children", []):
            count += _count_files([child]) if child.get("type") == "dir" else 1
    return count


def _human_size(nbytes: int) -> str:
    if nbytes < 1024:
        return f"{nbytes}B"
    if nbytes < 1024 * 1024:
        return f"{nbytes / 1024:.1f}KB"
    return f"{nbytes / (1024 * 1024):.1f}MB"
