"""
FILE: source_file_service.py
ROLE: Prompt source file I/O and OS-level file operations (project domain).
WHAT IT OWNS:
  - read_prompt_source: read a prompt source file from disk
  - write_prompt_source: write a prompt source file with mkdir-on-demand
  - open_in_editor: launch a file in the OS default editor (os.startfile)
  - open_folder: launch a folder in the OS file manager (os.startfile)

This module owns the I/O and OS-launch decisions for prompt source files.
The UI (ControlPane/PromptSourceEditor) calls these functions rather than
performing file operations directly. This keeps the UI domain free of
filesystem and OS-level concerns.

Domain: project (single domain — valid component)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def read_prompt_source(path: Path) -> tuple[Optional[str], Optional[str]]:
    """Read a prompt source file from disk.

    Returns (content, None) on success.
    Returns (None, error_message) on failure.
    """
    try:
        return path.read_text(encoding="utf-8"), None
    except Exception as exc:
        return None, str(exc)


def write_prompt_source(path: Path, content: str) -> Optional[str]:
    """Write a prompt source file to disk, creating parent dirs as needed.

    Returns None on success.
    Returns an error message string on failure.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return None
    except Exception as exc:
        return str(exc)


def open_in_editor(path: Path) -> Optional[str]:
    """Open a file in the OS default editor via os.startfile.

    Returns None on success.
    Returns an error message string on failure.
    """
    try:
        import os
        os.startfile(str(path))  # type: ignore[attr-defined]
        return None
    except Exception as exc:
        return str(exc)


def open_folder(path: Path) -> Optional[str]:
    """Open a folder in the OS file manager via os.startfile.

    Creates the folder if it does not exist.
    Returns None on success.
    Returns an error message string on failure.
    """
    try:
        import os
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(str(path))  # type: ignore[attr-defined]
        return None
    except Exception as exc:
        return str(exc)
