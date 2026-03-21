"""Docker CLI runner — same interface as CLIRunner but executes inside a container.

Drop-in replacement for CLIRunner when Docker mode is enabled. The ToolRouter
doesn't know or care which runner it's talking to — same .run() interface,
same result dict shape.

Key differences from CLIRunner:
- Commands run in a Linux bash shell (not Windows cmd.exe)
- No PathGuard needed (the container IS the boundary)
- No CommandPolicy allowlist needed (container isolation is the policy)
- Destructive confirmation still applies (user safety, not system safety)
"""

from typing import Any

from src.core.sandbox.docker_manager import DockerManager, CONTAINER_WORKDIR
from src.core.sandbox.audit_log import AuditLog
from src.core.sandbox.gui_launch_guard import detect_gui_launch
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.runtime_logger import get_logger
from src.core.utils.clock import utc_iso, Stopwatch

log = get_logger("docker_runner")

# Commands that are still blocked even inside Docker
# (not for security — the container handles that — but for sanity)
DOCKER_BLOCKED = {
    "reboot", "shutdown", "halt", "init",  # don't kill the container from inside
}

# Commands that are destructive (trigger user confirmation)
DOCKER_DESTRUCTIVE = {"rm", "rmdir", "del"}


class DockerRunner:
    """Execute commands inside the Docker sandbox container.

    Same interface as CLIRunner.run() — returns the same dict shape.
    The ToolRouter dispatches to this instead of CLIRunner when Docker is on.
    """

    def __init__(self, docker: DockerManager, activity: ActivityStream,
                 timeout: int = 30, on_confirm_destructive=None,
                 audit_log: AuditLog | None = None):
        self._docker = docker
        self._activity = activity
        self._timeout = timeout
        self._on_confirm_destructive = on_confirm_destructive
        self._audit = audit_log

    def run(self, command: str, cwd: str | None = None) -> dict[str, Any]:
        """Execute a command inside the Docker container.

        Args:
            command: Shell command string (runs in bash)
            cwd: Working directory inside the container. Defaults to /sandbox.

        Returns:
            Dict with: command, cwd, stdout, stderr, exit_code, started_at, finished_at
        """
        started_at = utc_iso()

        # Resolve working directory inside container
        if cwd:
            # Relative paths resolve against /sandbox
            if not cwd.startswith("/"):
                work_dir = f"{CONTAINER_WORKDIR}/{cwd}"
            else:
                work_dir = cwd
        else:
            work_dir = CONTAINER_WORKDIR

        host_cwd = self._host_cwd(work_dir)

        # Check container is running
        if not self._docker.is_running():
            msg = "Docker container is not running"
            self._activity.error("docker_cli", msg)
            if self._audit:
                self._audit.record(command, work_dir, "error", reason=msg)
            return {
                "command": command, "cwd": work_dir,
                "stdout": "", "stderr": msg,
                "exit_code": -1,
                "started_at": started_at, "finished_at": utc_iso(),
            }

        # Minimal sanity blocklist
        stripped = command.strip()
        if stripped:
            base_cmd = stripped.split()[0].lower()
            if base_cmd in DOCKER_BLOCKED:
                msg = f"Command '{base_cmd}' is blocked (container safety)"
                self._activity.warn("docker_cli.policy", f"BLOCKED: {command[:60]} — {msg}")
                if self._audit:
                    self._audit.record(command, work_dir, "blocked", reason=msg)
                return {
                    "command": command, "cwd": work_dir,
                    "stdout": "", "stderr": f"Command blocked: {msg}",
                    "exit_code": -1,
                    "started_at": started_at, "finished_at": utc_iso(),
                }

        gui_match = detect_gui_launch(command, self._docker.sandbox_root, host_cwd)
        if gui_match:
            msg = "Docker mode blocks GUI launches because desktop windows will not display meaningfully."
            self._activity.warn("docker_cli.policy", f"BLOCKED: {command[:60]} — {msg}")
            if self._audit:
                self._audit.record(command, work_dir, "blocked", reason=msg)
            return {
                "command": command, "cwd": work_dir,
                "stdout": "", "stderr": msg,
                "exit_code": -1,
                "started_at": started_at, "finished_at": utc_iso(),
            }

        # Destructive command confirmation (user safety, not system safety)
        if stripped:
            base_cmd = stripped.split()[0].lower()
            if base_cmd in DOCKER_DESTRUCTIVE and self._on_confirm_destructive:
                confirmed = self._on_confirm_destructive(command)
                if not confirmed:
                    log.info("Destructive command cancelled by user: %s", command)
                    self._activity.warn("docker_cli.confirm", f"CANCELLED: {command[:60]}")
                    if self._audit:
                        self._audit.record(command, work_dir, "cancelled",
                                           reason="User denied destructive command")
                    return {
                        "command": command, "cwd": work_dir,
                        "stdout": "", "stderr": "Command cancelled by user",
                        "exit_code": -1,
                        "started_at": started_at, "finished_at": utc_iso(),
                    }

        self._activity.tool("docker_cli", f"$ {command}  [cwd: {work_dir}]")
        log.info("Docker exec: %s (cwd=%s)", command, work_dir)

        sw = Stopwatch()
        result = self._docker.exec_command(command, cwd=work_dir, timeout=self._timeout)
        elapsed = sw.elapsed_ms()

        stdout = result["stdout"]
        stderr = result["stderr"]
        exit_code = result["exit_code"]
        finished_at = utc_iso()

        # Log result
        level = "TOOL" if exit_code == 0 else "WARN"
        self._activity.push(level, "docker_cli",
                            f"Exit {exit_code} ({elapsed:.0f}ms) | {command[:80]}")

        if stdout.strip():
            self._activity.tool("docker_cli.stdout", stdout.strip()[:500])
        if stderr.strip():
            self._activity.warn("docker_cli.stderr", stderr.strip()[:500])

        # Audit trail
        if self._audit:
            outcome = "executed" if exit_code == 0 else "error"
            if "timed out" in stderr:
                outcome = "timeout"
            self._audit.record(command, work_dir, outcome,
                               exit_code=exit_code, duration_ms=elapsed)

        return {
            "command": command,
            "cwd": work_dir,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "started_at": started_at,
            "finished_at": finished_at,
        }

    def _host_cwd(self, docker_cwd: str) -> str:
        if not docker_cwd.startswith(CONTAINER_WORKDIR):
            return str(self._docker.sandbox_root)
        suffix = docker_cwd[len(CONTAINER_WORKDIR):].lstrip("/")
        if not suffix:
            return str(self._docker.sandbox_root)
        return str((self._docker.sandbox_root / suffix).resolve())
