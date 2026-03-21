"""Sandboxed CLI command execution.

Executes subprocess commands only within the validated sandbox root.
All commands are validated against the CommandPolicy allowlist before execution.
Captures stdout, stderr, exit code. Emits activity events.
All command attempts are recorded in the audit log.
"""

import subprocess
from typing import Any

from src.core.sandbox.path_guard import PathGuard
from src.core.sandbox.command_policy import CommandPolicy
from src.core.sandbox.audit_log import AuditLog
from src.core.sandbox.gui_launch_guard import detect_gui_launch
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.runtime_logger import get_logger
from src.core.utils.clock import utc_iso, Stopwatch

log = get_logger("cli_runner")


class CLIRunner:
    """Execute CLI commands inside the sandbox boundary with policy enforcement."""

    def __init__(self, guard: PathGuard, activity: ActivityStream,
                 policy: CommandPolicy | None = None, timeout: int = 30,
                 on_confirm_destructive=None, audit_log: AuditLog | None = None,
                 gui_policy_getter=None, on_confirm_gui_launch=None):
        self._guard = guard
        self._activity = activity
        self._policy = policy or CommandPolicy(mode="allowlist")
        self._timeout = timeout
        self._on_confirm_destructive = on_confirm_destructive
        self._audit = audit_log
        self._gui_policy_getter = gui_policy_getter
        self._on_confirm_gui_launch = on_confirm_gui_launch

    def run(self, command: str, cwd: str | None = None) -> dict[str, Any]:
        """Execute a CLI command within the sandbox.

        The command is first validated against the security policy.
        Only allowlisted commands may execute.

        Args:
            command: Shell command string
            cwd: Working directory (must be inside sandbox). Defaults to sandbox root.

        Returns:
            Dict with: command, cwd, stdout, stderr, exit_code, started_at, finished_at
        """
        started_at = utc_iso()

        # Validate working directory
        work_dir = self._guard.validate_cwd(cwd) if cwd else self._guard.root

        # ── Command policy check ──────────────────────
        allowed, reason = self._policy.validate(command)
        if not allowed:
            log.warning("COMMAND BLOCKED: %s — %s", command, reason)
            return self._blocked_result(command, work_dir, started_at, f"Command blocked: {reason}")

        # ── Destructive command confirmation ──────────
        if self._policy.is_destructive(command) and self._on_confirm_destructive:
            confirmed = self._on_confirm_destructive(command)
            if not confirmed:
                log.info("Destructive command cancelled by user: %s", command)
                self._activity.warn("cli.confirm", f"CANCELLED: {command[:60]}")
                if self._audit:
                    self._audit.record(command, str(work_dir), "cancelled",
                                       reason="User denied destructive command")
                return {
                    "command": command, "cwd": str(work_dir),
                    "stdout": "", "stderr": "Command cancelled by user",
                    "exit_code": -1,
                    "started_at": started_at, "finished_at": utc_iso(),
                }

        gui_match = detect_gui_launch(command, self._guard.root, work_dir)
        if gui_match:
            policy = self._current_gui_policy()
            if policy == "deny":
                return self._blocked_result(
                    command,
                    work_dir,
                    started_at,
                    "Local GUI launch blocked by settings (GUI / Tkinter policy = Block).",
                )
            if policy == "ask":
                if not self._on_confirm_gui_launch:
                    return self._blocked_result(
                        command,
                        work_dir,
                        started_at,
                        "GUI launch requires approval, but no approval handler is configured.",
                    )
                decision = self._on_confirm_gui_launch(command, gui_match)
                if decision not in {"allow_once", "always_allow"}:
                    return self._blocked_result(
                        command,
                        work_dir,
                        started_at,
                        "GUI launch cancelled by user.",
                        outcome="cancelled",
                    )

        self._activity.tool("cli", f"$ {command}  [cwd: {work_dir}]")
        log.info("CLI exec: %s (cwd=%s)", command, work_dir)

        sw = Stopwatch()
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=self._timeout,
                env=None,  # inherit environment
            )
            stdout = result.stdout
            stderr = result.stderr
            exit_code = result.returncode

        except subprocess.TimeoutExpired:
            stdout = ""
            stderr = f"Command timed out after {self._timeout}s"
            exit_code = -1
            log.warning("CLI timeout: %s", command)
        except Exception as e:
            stdout = ""
            stderr = str(e)
            exit_code = -1
            log.exception("CLI error: %s", command)

        finished_at = utc_iso()
        elapsed = sw.elapsed_ms()

        # Log result
        level = "TOOL" if exit_code == 0 else "WARN"
        self._activity.push(level, "cli",
                            f"Exit {exit_code} ({elapsed:.0f}ms) | {command[:80]}")

        if stdout.strip():
            self._activity.tool("cli.stdout", stdout.strip()[:500])
        if stderr.strip():
            self._activity.warn("cli.stderr", stderr.strip()[:500])

        # Audit trail
        if self._audit:
            outcome = "executed" if exit_code == 0 else "error"
            if "timed out" in stderr:
                outcome = "timeout"
            self._audit.record(command, str(work_dir), outcome,
                               exit_code=exit_code, duration_ms=elapsed)

        return {
            "command": command,
            "cwd": str(work_dir),
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "started_at": started_at,
            "finished_at": finished_at,
        }

    def _blocked_result(
        self,
        command: str,
        work_dir,
        started_at: str,
        reason: str,
        *,
        outcome: str = "blocked",
    ) -> dict[str, Any]:
        hint = self._blocked_command_hint(command)
        stderr = reason if not hint else f"{reason}\nSuggested alternative: {hint}"
        self._activity.warn("cli.policy", f"BLOCKED: {command[:60]} — {reason}")
        if self._audit:
            self._audit.record(command, str(work_dir), outcome, reason=reason)
        return {
            "command": command,
            "cwd": str(work_dir),
            "stdout": "",
            "stderr": stderr,
            "exit_code": -1,
            "started_at": started_at,
            "finished_at": utc_iso(),
        }

    def _current_gui_policy(self) -> str:
        if not self._gui_policy_getter:
            return "ask"
        try:
            value = str(self._gui_policy_getter() or "ask").strip().lower()
        except Exception:
            value = "ask"
        return value if value in {"deny", "ask", "allow"} else "ask"

    def _blocked_command_hint(self, command: str) -> str:
        stripped = command.strip().lower()
        if not stripped:
            return ""
        base_cmd = stripped.split()[0].removesuffix(".exe")
        if base_cmd in {"type", "cat", "head", "tail", "more"}:
            return "Use read_file instead of shell file-reading commands."
        if base_cmd in {"dir", "ls", "tree"}:
            return "Use list_files for structured workspace exploration."
        if base_cmd in {"echo", "touch"} or ">" in stripped:
            return "Use write_file to create or append to files."
        if base_cmd in {"python", "py", "pythonw"}:
            return "Use run_python_file to execute sandbox-local Python scripts safely."
        if base_cmd in {"pip", "pip3", "npm", "yarn", "choco", "winget", "scoop"}:
            return "Package installation is disabled by default. Use the existing runtime and never try `pip install tkinter`."
        return ""
