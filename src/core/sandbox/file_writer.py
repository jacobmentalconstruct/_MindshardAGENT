"""File writer — direct file creation/reading within the sandbox.

Solves the fundamental problem that small models cannot reliably create
multi-line files through Windows cmd.exe shell quoting. Instead of fighting
echo/python -c escaping, the model calls write_file with raw content and
the agent writes it directly to disk.

Also provides read_file for reliable file reading (no cat/type confusion).
"""

import os
from pathlib import Path
from typing import Any

from src.core.sandbox.path_guard import PathGuard
from src.core.sandbox.audit_log import AuditLog
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.runtime_logger import get_logger
from src.core.utils.clock import utc_iso, Stopwatch

log = get_logger("file_writer")

# Safety limits
MAX_WRITE_SIZE = 512_000     # 512 KB max per write
MAX_READ_SIZE = 1_024_000    # 1 MB max per read
BLOCKED_EXTENSIONS = {".exe", ".bat", ".cmd", ".ps1", ".vbs", ".wsf", ".msi", ".scr", ".com"}


class FileWriter:
    """Read and write files within the sandbox boundary."""

    def __init__(self, guard: PathGuard, activity: ActivityStream,
                 audit_log: AuditLog | None = None):
        self._guard = guard
        self._activity = activity
        self._audit = audit_log

    def write_file(self, path: str, content: str,
                   mode: str = "write") -> dict[str, Any]:
        """Write content to a file within the sandbox.

        Args:
            path: File path (relative to sandbox root, or absolute within sandbox)
            content: Text content to write
            mode: "write" (create/overwrite), "append" (add to end)

        Returns:
            Dict with: path, success, bytes_written, error (if any)
        """
        sw = Stopwatch()

        # Validate path is inside sandbox
        try:
            resolved = self._guard.validate(path)
        except ValueError as e:
            self._log_audit("write_file", path, "blocked", reason=str(e))
            return {"path": path, "success": False, "error": str(e)}

        # Block dangerous extensions
        ext = resolved.suffix.lower()
        if ext in BLOCKED_EXTENSIONS:
            msg = f"Cannot write files with extension '{ext}' (security policy)"
            log.warning("WRITE BLOCKED: %s — %s", path, msg)
            self._activity.warn("file_writer", f"BLOCKED: {path} — {msg}")
            self._log_audit("write_file", path, "blocked", reason=msg)
            return {"path": path, "success": False, "error": msg}

        # Size check
        if len(content) > MAX_WRITE_SIZE:
            msg = f"Content too large ({len(content)} bytes, max {MAX_WRITE_SIZE})"
            self._log_audit("write_file", path, "blocked", reason=msg)
            return {"path": path, "success": False, "error": msg}

        # Ensure parent directory exists
        resolved.parent.mkdir(parents=True, exist_ok=True)

        # Determine file mode
        open_mode = "a" if mode == "append" else "w"
        action = "Appending to" if mode == "append" else "Writing"

        try:
            with open(resolved, open_mode, encoding="utf-8", newline="\n") as f:
                f.write(content)

            bytes_written = len(content.encode("utf-8"))
            elapsed = sw.elapsed_ms()

            log.info("%s %s (%d bytes, %.0fms)", action, resolved, bytes_written, elapsed)
            self._activity.tool("file_writer",
                                f"{action} {resolved.name} ({bytes_written} bytes)")

            self._log_audit("write_file", str(resolved), "executed",
                            exit_code=0, duration_ms=elapsed)

            return {
                "path": str(resolved),
                "success": True,
                "bytes_written": bytes_written,
                "action": mode,
            }

        except Exception as e:
            elapsed = sw.elapsed_ms()
            log.exception("Write failed: %s", path)
            self._activity.warn("file_writer", f"FAILED: {path} — {e}")
            self._log_audit("write_file", path, "error",
                            reason=str(e), duration_ms=elapsed)
            return {"path": path, "success": False, "error": str(e)}

    def read_file(self, path: str) -> dict[str, Any]:
        """Read a file from within the sandbox.

        Args:
            path: File path (relative to sandbox root, or absolute within sandbox)

        Returns:
            Dict with: path, success, content, size, error (if any)
        """
        sw = Stopwatch()

        # Validate path is inside sandbox
        try:
            resolved = self._guard.validate(path)
        except ValueError as e:
            self._log_audit("read_file", path, "blocked", reason=str(e))
            return {"path": path, "success": False, "error": str(e)}

        if not resolved.exists():
            msg = f"File not found: {resolved.name}"
            self._log_audit("read_file", str(resolved), "error", reason=msg)
            return {"path": str(resolved), "success": False, "error": msg}

        if not resolved.is_file():
            msg = f"Not a file: {resolved.name}"
            self._log_audit("read_file", str(resolved), "error", reason=msg)
            return {"path": str(resolved), "success": False, "error": msg}

        # Size check
        file_size = resolved.stat().st_size
        if file_size > MAX_READ_SIZE:
            msg = f"File too large ({file_size} bytes, max {MAX_READ_SIZE})"
            self._log_audit("read_file", str(resolved), "blocked", reason=msg)
            return {"path": str(resolved), "success": False, "error": msg}

        try:
            content = resolved.read_text(encoding="utf-8")
            elapsed = sw.elapsed_ms()

            log.info("Read %s (%d bytes, %.0fms)", resolved, file_size, elapsed)
            self._activity.tool("file_writer",
                                f"Read {resolved.name} ({file_size} bytes)")

            self._log_audit("read_file", str(resolved), "executed",
                            exit_code=0, duration_ms=elapsed)

            return {
                "path": str(resolved),
                "success": True,
                "content": content,
                "size": file_size,
            }

        except UnicodeDecodeError:
            msg = f"Cannot read binary file: {resolved.name}"
            self._log_audit("read_file", str(resolved), "error", reason=msg)
            return {"path": str(resolved), "success": False, "error": msg}
        except Exception as e:
            elapsed = sw.elapsed_ms()
            log.exception("Read failed: %s", path)
            self._log_audit("read_file", path, "error",
                            reason=str(e), duration_ms=elapsed)
            return {"path": path, "success": False, "error": str(e)}

    def _log_audit(self, operation: str, path: str, outcome: str,
                   exit_code: int | None = None, reason: str = "",
                   duration_ms: float = 0) -> None:
        """Record operation in audit log."""
        if self._audit:
            self._audit.record(
                command=f"{operation} {path}",
                cwd=str(self._guard.root),
                outcome=outcome,
                exit_code=exit_code,
                reason=reason,
                duration_ms=duration_ms,
            )
