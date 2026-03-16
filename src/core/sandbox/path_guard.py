"""Path guard — enforces sandbox boundary for all file/CLI operations.

All paths must resolve to within the sandbox root.
Blocks traversal escapes, symlink escapes, and absolute paths outside root.
"""

import os
from pathlib import Path

from src.core.runtime.runtime_logger import get_logger

log = get_logger("path_guard")


class PathGuard:
    """Enforces that all resolved paths stay within the sandbox root."""

    def __init__(self, sandbox_root: str | Path):
        self._root = Path(sandbox_root).resolve()
        if not self._root.exists():
            self._root.mkdir(parents=True, exist_ok=True)
        log.info("PathGuard active: root=%s", self._root)

    @property
    def root(self) -> Path:
        return self._root

    def validate(self, target: str | Path) -> Path:
        """Resolve target and verify it is within sandbox root.

        Returns the resolved path if safe.
        Raises ValueError if the path escapes the sandbox.
        """
        target = Path(target)

        # If relative, resolve against sandbox root
        if not target.is_absolute():
            target = self._root / target

        resolved = target.resolve()

        # Check containment
        try:
            resolved.relative_to(self._root)
        except ValueError:
            log.warning("PATH BLOCKED: %s escapes sandbox %s", resolved, self._root)
            raise ValueError(
                f"Path '{resolved}' is outside sandbox root '{self._root}'. Access denied."
            )

        return resolved

    def is_safe(self, target: str | Path) -> bool:
        """Check if a path is within sandbox without raising."""
        try:
            self.validate(target)
            return True
        except ValueError:
            return False

    def validate_cwd(self, cwd: str | Path) -> Path:
        """Validate a working directory for CLI execution."""
        resolved = self.validate(cwd)
        if not resolved.is_dir():
            raise ValueError(f"Working directory does not exist: {resolved}")
        return resolved
