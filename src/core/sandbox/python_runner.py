"""Structured Python script runner with optional GUI launch gating."""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.runtime_logger import get_logger
from src.core.sandbox.audit_log import AuditLog
from src.core.sandbox.docker_manager import CONTAINER_WORKDIR, DockerManager
from src.core.sandbox.gui_launch_guard import GuiLaunchMatch, detect_gui_script
from src.core.sandbox.path_guard import PathGuard
from src.core.sandbox.run_workspace import RunWorkspace, create_run_workspace, record_run_result
from src.core.utils.clock import Stopwatch, utc_iso

log = get_logger("python_runner")

WORKSPACE_SANDBOX = "sandbox"
WORKSPACE_RUN_COPY = "run_copy"


class PythonRunner:
    """Run sandbox-local Python files without exposing arbitrary shell execution."""

    def __init__(
        self,
        guard: PathGuard,
        activity: ActivityStream,
        *,
        timeout: int = 30,
        audit_log: AuditLog | None = None,
        docker_manager: DockerManager | None = None,
        gui_policy_getter=None,
        on_confirm_gui_launch=None,
    ):
        self._guard = guard
        self._activity = activity
        self._timeout = timeout
        self._audit = audit_log
        self._docker = docker_manager
        self._gui_policy_getter = gui_policy_getter
        self._on_confirm_gui_launch = on_confirm_gui_launch

    @property
    def docker_mode(self) -> bool:
        return self._docker is not None

    def run_file(
        self,
        path: str,
        *,
        args: Iterable[Any] | None = None,
        cwd: str | None = None,
        timeout: int | None = None,
        workspace: str | None = None,
    ) -> dict[str, Any]:
        """Execute a Python file from inside the sandbox."""

        started_at = utc_iso()
        timeout_s = self._normalize_timeout(timeout)

        try:
            script_path = self._guard.validate(path)
        except ValueError as exc:
            return self._blocked_result(
                path=path,
                cwd="",
                command="",
                started_at=started_at,
                reason=str(exc),
            )

        if not script_path.exists() or not script_path.is_file():
            return self._blocked_result(
                path=str(script_path),
                cwd="",
                command="",
                started_at=started_at,
                reason=f"Python file not found: {script_path.name}",
            )

        if script_path.suffix.lower() not in {".py", ".pyw"}:
            return self._blocked_result(
                path=str(script_path),
                cwd="",
                command="",
                started_at=started_at,
                reason="run_python_file only supports .py or .pyw files",
            )

        try:
            work_dir = self._guard.validate_cwd(cwd) if cwd else script_path.parent
        except ValueError as exc:
            return self._blocked_result(
                path=str(script_path),
                cwd=str(cwd or ""),
                command="",
                started_at=started_at,
                reason=str(exc),
            )

        arg_list = [str(arg) for arg in (args or [])]
        workspace_mode = self._normalize_workspace_mode(workspace)
        if workspace_mode is None:
            return self._blocked_result(
                path=str(script_path),
                cwd=str(work_dir),
                command="",
                started_at=started_at,
                reason="workspace must be 'run_copy' or 'sandbox'",
            )

        gui_match = detect_gui_script(script_path)
        gate = self._evaluate_gui_policy(
            script_path=script_path,
            work_dir=work_dir,
            command=self._display_command(script_path, arg_list, workspace_mode),
            gui_match=gui_match,
            started_at=started_at,
        )
        if gate is not None:
            return gate

        run_workspace: RunWorkspace | None = None
        executed_script = script_path
        executed_cwd = work_dir
        if workspace_mode == WORKSPACE_RUN_COPY:
            try:
                run_workspace = create_run_workspace(
                    self._guard.root,
                    script_path,
                    work_dir,
                    arg_list,
                )
            except Exception as exc:
                log.exception("Run workspace staging failed: %s", script_path)
                return self._blocked_result(
                    path=str(script_path),
                    cwd=str(work_dir),
                    command="",
                    started_at=started_at,
                    reason=f"Failed to prepare disposable run workspace: {exc}",
                )
            executed_script = run_workspace.script_path
            executed_cwd = run_workspace.cwd

        display_command = self._display_command(script_path, arg_list, workspace_mode)

        self._activity.tool(
            "python_runner",
            f"python {script_path.name}  [workspace: {workspace_mode}] [cwd: {executed_cwd}]",
        )
        log.info("Python exec: %s (workspace=%s cwd=%s)", script_path, workspace_mode, executed_cwd)

        sw = Stopwatch()
        try:
            if self.docker_mode:
                result = self._run_in_docker(executed_script, executed_cwd, arg_list, timeout_s)
                stdout = result["stdout"]
                stderr = result["stderr"]
                exit_code = result["exit_code"]
            else:
                proc = subprocess.run(
                    [sys.executable, str(executed_script), *arg_list],
                    cwd=str(executed_cwd),
                    capture_output=True,
                    text=True,
                    timeout=timeout_s,
                )
                stdout = proc.stdout
                stderr = proc.stderr
                exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            stdout = ""
            stderr = f"Python script timed out after {timeout_s}s"
            exit_code = -1
        except Exception as exc:
            stdout = ""
            stderr = str(exc)
            exit_code = -1
            log.exception("Python runner failed: %s", script_path)

        finished_at = utc_iso()
        elapsed = sw.elapsed_ms()
        level = "TOOL" if exit_code == 0 else "WARN"
        self._activity.push(
            level,
            "python_runner",
            f"Exit {exit_code} ({elapsed:.0f}ms) | {script_path.name} [{workspace_mode}]",
        )

        if stdout.strip():
            self._activity.tool("python_runner.stdout", stdout.strip()[:500])
        if stderr.strip():
            self._activity.warn("python_runner.stderr", stderr.strip()[:500])

        if self._audit:
            outcome = "executed" if exit_code == 0 else "error"
            if "timed out" in stderr.lower():
                outcome = "timeout"
            self._audit.record(
                command=display_command,
                cwd=str(executed_cwd),
                outcome=outcome,
                exit_code=exit_code,
                duration_ms=elapsed,
            )

        payload = {
            "command": display_command,
            "path": str(script_path),
            "cwd": str(executed_cwd),
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "started_at": started_at,
            "finished_at": finished_at,
            "gui_launch": bool(gui_match),
            "workspace_mode": workspace_mode,
        }
        if run_workspace:
            payload["run_id"] = run_workspace.run_id
            payload["run_root"] = str(run_workspace.run_root)
            payload["workspace_root"] = str(run_workspace.workspace_root)
            payload["executed_path"] = str(executed_script)
            record_run_result(run_workspace, payload)
        return payload

    def _evaluate_gui_policy(
        self,
        *,
        script_path: Path,
        work_dir: Path,
        command: str,
        gui_match: GuiLaunchMatch | None,
        started_at: str,
    ) -> dict[str, Any] | None:
        if not gui_match:
            return None

        if self.docker_mode:
            return self._blocked_result(
                path=str(script_path),
                cwd=str(work_dir),
                command=command,
                started_at=started_at,
                reason="Docker mode blocks GUI launches because desktop windows will not display meaningfully.",
            )

        policy = self._current_gui_policy()
        if policy == "allow":
            return None

        if policy == "deny":
            return self._blocked_result(
                path=str(script_path),
                cwd=str(work_dir),
                command=command,
                started_at=started_at,
                reason="GUI launch blocked by settings (GUI / Tkinter policy = Block).",
            )

        if not self._on_confirm_gui_launch:
            return self._blocked_result(
                path=str(script_path),
                cwd=str(work_dir),
                command=command,
                started_at=started_at,
                reason="GUI launch requires approval, but no approval handler is configured.",
            )

        decision = self._on_confirm_gui_launch(command, gui_match)
        if decision in {"allow_once", "always_allow"}:
            return None

        return self._blocked_result(
            path=str(script_path),
            cwd=str(work_dir),
            command=command,
            started_at=started_at,
            reason="GUI launch cancelled by user.",
            outcome="cancelled",
        )

    def _run_in_docker(
        self,
        script_path: Path,
        work_dir: Path,
        arg_list: list[str],
        timeout_s: int,
    ) -> dict[str, Any]:
        if not self._docker or not self._docker.is_running():
            return {
                "stdout": "",
                "stderr": "Docker container is not running",
                "exit_code": -1,
            }

        script_rel = script_path.relative_to(self._guard.root).as_posix()
        cwd_rel = work_dir.relative_to(self._guard.root).as_posix()
        container_script = f"{CONTAINER_WORKDIR}/{script_rel}" if script_rel else CONTAINER_WORKDIR
        container_cwd = f"{CONTAINER_WORKDIR}/{cwd_rel}" if cwd_rel else CONTAINER_WORKDIR
        command = "python " + " ".join(
            [shlex.quote(container_script), *[shlex.quote(arg) for arg in arg_list]]
        )
        return self._docker.exec_command(command, cwd=container_cwd, timeout=timeout_s)

    def _blocked_result(
        self,
        *,
        path: str,
        cwd: str,
        command: str,
        started_at: str,
        reason: str,
        outcome: str = "blocked",
    ) -> dict[str, Any]:
        self._activity.warn("python_runner", reason)
        if self._audit:
            self._audit.record(
                command=command or f"run_python_file {path}",
                cwd=cwd or str(self._guard.root),
                outcome=outcome,
                reason=reason,
            )
        return {
            "command": command,
            "path": path,
            "cwd": cwd,
            "stdout": "",
            "stderr": reason,
            "exit_code": -1,
            "started_at": started_at,
            "finished_at": utc_iso(),
            "gui_launch": "gui" in reason.lower() or "window" in reason.lower(),
        }

    def _display_command(self, script_path: Path, arg_list: list[str], workspace_mode: str) -> str:
        rel = script_path.relative_to(self._guard.root).as_posix()
        args = " ".join(shlex.quote(arg) for arg in arg_list)
        suffix = f" [workspace: {workspace_mode}]"
        return f"python {rel}" + (f" {args}" if args else "") + suffix

    def _current_gui_policy(self) -> str:
        if not self._gui_policy_getter:
            return "ask"
        try:
            value = str(self._gui_policy_getter() or "ask").strip().lower()
        except Exception:
            value = "ask"
        return value if value in {"deny", "ask", "allow"} else "ask"

    def _normalize_timeout(self, timeout: int | None) -> int:
        try:
            timeout_s = int(timeout if timeout is not None else self._timeout)
        except (TypeError, ValueError):
            timeout_s = self._timeout
        return max(1, min(timeout_s, 120))

    def _normalize_workspace_mode(self, workspace: str | None) -> str | None:
        value = str(workspace or WORKSPACE_RUN_COPY).strip().lower()
        if value in {WORKSPACE_RUN_COPY, WORKSPACE_SANDBOX}:
            return value
        return None
