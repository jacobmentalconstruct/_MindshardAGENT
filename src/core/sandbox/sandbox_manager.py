"""Sandbox manager — owns the selected sandbox root and exposes standard folders.

Validates sandbox configuration and ensures required subdirectories exist.
"""

from pathlib import Path

from src.core.sandbox.path_guard import PathGuard
from src.core.sandbox.cli_runner import CLIRunner
from src.core.sandbox.audit_log import AuditLog
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.runtime_logger import get_logger

log = get_logger("sandbox_manager")

_SANDBOX_SUBDIRS = ["_tools", "_sessions", "_outputs", "_logs"]


class SandboxManager:
    """Manages the sandbox root directory and its standard structure."""

    def __init__(self, sandbox_root: str | Path, activity: ActivityStream,
                 on_confirm_destructive=None):
        self._root = Path(sandbox_root).resolve()
        self._activity = activity
        self._guard = PathGuard(self._root)

        self._ensure_structure()

        # Audit log lives in .mindshard/logs/
        self._audit = AuditLog(self._root / "_logs" / "audit.jsonl")
        self._cli = CLIRunner(self._guard, activity,
                              on_confirm_destructive=on_confirm_destructive,
                              audit_log=self._audit)
        log.info("SandboxManager active: %s", self._root)
        activity.info("sandbox", f"Sandbox root: {self._root}")

    def _ensure_structure(self) -> None:
        for subdir in _SANDBOX_SUBDIRS:
            d = self._root / subdir
            d.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    @property
    def tools_dir(self) -> Path:
        return self._root / "_tools"

    @property
    def sessions_dir(self) -> Path:
        return self._root / "_sessions"

    @property
    def outputs_dir(self) -> Path:
        return self._root / "_outputs"

    @property
    def logs_dir(self) -> Path:
        return self._root / "_logs"

    @property
    def guard(self) -> PathGuard:
        return self._guard

    @property
    def cli(self) -> CLIRunner:
        return self._cli

    @property
    def audit(self) -> AuditLog:
        return self._audit
