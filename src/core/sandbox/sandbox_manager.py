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

_MINDSHARD_SUBDIRS = ["logs", "outputs", "sessions", "state", "tools", "parts", "ref", "vcs"]
_LEGACY_ROOT_DIRS = ["_tools", "_sessions", "_outputs", "_logs"]


class SandboxManager:
    """Manages the sandbox root directory and its standard structure."""

    def __init__(self, sandbox_root: str | Path, activity: ActivityStream,
                 on_confirm_destructive=None):
        self._root = Path(sandbox_root).resolve()
        self._activity = activity
        self._guard = PathGuard(self._root)
        self._mindshard_root = self._root / ".mindshard"

        self._ensure_structure()
        self._cleanup_legacy_dirs()

        # Audit log lives in .mindshard/logs/
        self._audit = AuditLog(self._mindshard_root / "logs" / "audit.jsonl")
        self._cli = CLIRunner(self._guard, activity,
                              on_confirm_destructive=on_confirm_destructive,
                              audit_log=self._audit)
        log.info("SandboxManager active: %s", self._root)
        activity.info("sandbox", f"Sandbox root: {self._root}")

    def _ensure_structure(self) -> None:
        for subdir in _MINDSHARD_SUBDIRS:
            d = self._mindshard_root / subdir
            d.mkdir(parents=True, exist_ok=True)

    def _cleanup_legacy_dirs(self) -> None:
        """Remove empty legacy root folders left over from the pre-.mindshard layout."""
        for subdir in _LEGACY_ROOT_DIRS:
            legacy_dir = self._root / subdir
            if not legacy_dir.exists() or not legacy_dir.is_dir():
                continue
            try:
                next(legacy_dir.iterdir())
                self._activity.warn(
                    "sandbox",
                    f"Legacy folder still present outside .mindshard/: {legacy_dir.name}",
                )
            except StopIteration:
                try:
                    legacy_dir.rmdir()
                    self._activity.info("sandbox", f"Removed empty legacy folder: {legacy_dir.name}")
                except OSError:
                    pass
            except Exception:
                pass

    @property
    def root(self) -> Path:
        return self._root

    @property
    def tools_dir(self) -> Path:
        return self._mindshard_root / "tools"

    @property
    def sessions_dir(self) -> Path:
        return self._mindshard_root / "sessions"

    @property
    def outputs_dir(self) -> Path:
        return self._mindshard_root / "outputs"

    @property
    def logs_dir(self) -> Path:
        return self._mindshard_root / "logs"

    @property
    def guard(self) -> PathGuard:
        return self._guard

    @property
    def cli(self) -> CLIRunner:
        return self._cli

    @property
    def audit(self) -> AuditLog:
        return self._audit
