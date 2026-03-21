"""Docker container lifecycle manager — USER ONLY, never agent-accessible.

Manages the sandbox container: build image, create/start/stop/destroy container,
check status. The agent never sees or controls Docker — it just gets a Linux
shell instead of Windows cmd.exe.
"""

import hashlib
import subprocess
import json
from pathlib import Path
from typing import Any

from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.runtime_logger import get_logger

log = get_logger("docker_manager")

IMAGE_NAME = "mindshard-sandbox:latest"
CONTAINER_WORKDIR = "/sandbox"


def _derive_container_name(sandbox_root: str | Path) -> str:
    """Derive a unique container name from the sandbox path.

    Each install/sandbox gets its own container so multiple instances
    don't collide.  Format: mindshard-<8-char hash>
    """
    path_str = str(Path(sandbox_root).resolve()).lower()
    short_hash = hashlib.sha256(path_str.encode()).hexdigest()[:8]
    return f"mindshard-{short_hash}"


class DockerManager:
    """Manages the MindshardAGENT sandbox Docker container."""

    def __init__(self, activity: ActivityStream, sandbox_root: str | Path = ""):
        self._activity = activity
        self._sandbox_root = Path(sandbox_root).resolve() if sandbox_root else Path.cwd()
        # Container name derived from sandbox path — unique per install
        self._container_name = (
            _derive_container_name(sandbox_root) if sandbox_root
            else "mindshard-sandbox"
        )

    def set_sandbox_root(self, sandbox_root: str | Path) -> None:
        """Update the container name when sandbox root changes."""
        self._sandbox_root = Path(sandbox_root).resolve()
        self._container_name = _derive_container_name(sandbox_root)
        log.info("Container name set: %s", self._container_name)

    @property
    def container_name(self) -> str:
        return self._container_name

    @property
    def sandbox_root(self) -> Path:
        return self._sandbox_root

    def is_docker_available(self) -> bool:
        """Check if Docker daemon is running."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def image_exists(self) -> bool:
        """Check if the sandbox image has been built."""
        try:
            result = subprocess.run(
                ["docker", "image", "inspect", IMAGE_NAME],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    def build_image(self, dockerfile_dir: str | Path) -> bool:
        """Build the sandbox Docker image from the Dockerfile.

        Args:
            dockerfile_dir: Directory containing the Dockerfile

        Returns:
            True if build succeeded
        """
        dockerfile_dir = Path(dockerfile_dir)
        if not (dockerfile_dir / "Dockerfile").exists():
            log.error("No Dockerfile found in %s", dockerfile_dir)
            self._activity.error("docker", f"No Dockerfile in {dockerfile_dir}")
            return False

        self._activity.info("docker", "Building sandbox image...")
        log.info("Building Docker image from %s", dockerfile_dir)

        try:
            result = subprocess.run(
                ["docker", "build", "-t", IMAGE_NAME, str(dockerfile_dir)],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                self._activity.info("docker", f"Image {IMAGE_NAME} built successfully")
                log.info("Docker image built: %s", IMAGE_NAME)
                return True
            else:
                self._activity.error("docker", f"Image build failed: {result.stderr[:200]}")
                log.error("Docker build failed: %s", result.stderr[:500])
                return False
        except subprocess.TimeoutExpired:
            self._activity.error("docker", "Image build timed out (5 min)")
            return False
        except Exception as e:
            log.exception("Docker build error")
            self._activity.error("docker", f"Build error: {e}")
            return False

    def container_status(self) -> str:
        """Get container status: 'running', 'stopped', 'not_found', or 'error'."""
        try:
            result = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Status}}", self._container_name],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()  # "running", "exited", "created", etc.
            return "not_found"
        except Exception:
            return "error"

    def create_and_start(self, sandbox_root: str | Path,
                         memory_limit: str = "512m",
                         cpu_limit: float = 1.0) -> bool:
        """Create and start the sandbox container with volume mount.

        Args:
            sandbox_root: Host path to mount as /sandbox in the container
            memory_limit: Docker memory limit (e.g., "512m", "1g")
            cpu_limit: CPU limit (e.g., 1.0 = one full core)

        Returns:
            True if container started successfully
        """
        sandbox_root = Path(sandbox_root).resolve()

        # Stop and remove existing container if present
        status = self.container_status()
        if status != "not_found":
            self.destroy()

        # Convert Windows path to Docker-compatible format
        # Docker Desktop on Windows needs forward slashes
        host_path = str(sandbox_root).replace("\\", "/")

        cmd = [
            "docker", "run", "-d",
            "--name", self._container_name,
            "--memory", memory_limit,
            "--cpus", str(cpu_limit),
            "--network", "none",  # No network access for the sandbox
            "-v", f"{host_path}:{CONTAINER_WORKDIR}",
            "-w", CONTAINER_WORKDIR,
            IMAGE_NAME,
        ]

        self._activity.info("docker", f"Starting container with sandbox: {sandbox_root}")
        log.info("Creating container: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                container_id = result.stdout.strip()[:12]
                self._activity.info("docker",
                    f"Container {self._container_name} started ({container_id})")
                log.info("Container started: %s (%s)", self._container_name, container_id)
                return True
            else:
                self._activity.error("docker",
                    f"Container start failed: {result.stderr[:200]}")
                log.error("Container start failed: %s", result.stderr[:500])
                return False
        except Exception as e:
            log.exception("Container start error")
            self._activity.error("docker", f"Start error: {e}")
            return False

    def stop(self) -> bool:
        """Stop the running container."""
        try:
            result = subprocess.run(
                ["docker", "stop", self._container_name],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                self._activity.info("docker", f"Container {self._container_name} stopped")
                return True
            return False
        except Exception:
            return False

    def destroy(self) -> bool:
        """Stop and remove the container."""
        try:
            subprocess.run(
                ["docker", "rm", "-f", self._container_name],
                capture_output=True, text=True, timeout=15,
            )
            self._activity.info("docker", f"Container {self._container_name} removed")
            log.info("Container destroyed: %s", self._container_name)
            return True
        except Exception:
            return False

    def is_running(self) -> bool:
        """Check if the container is currently running."""
        return self.container_status() == "running"

    def exec_command(self, command: str, cwd: str = CONTAINER_WORKDIR,
                     timeout: int = 30) -> dict[str, Any]:
        """Execute a command inside the running container.

        This is the low-level method used by DockerRunner.

        Args:
            command: Shell command to execute
            cwd: Working directory inside the container
            timeout: Timeout in seconds

        Returns:
            Dict with stdout, stderr, exit_code
        """
        cmd = [
            "docker", "exec",
            "-w", cwd,
            self._container_name,
            "bash", "-c", command,
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
                "exit_code": -1,
            }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
            }

    def get_info(self) -> dict[str, Any]:
        """Get container info for display."""
        status = self.container_status()
        info = {
            "container_name": self._container_name,
            "image": IMAGE_NAME,
            "status": status,
            "docker_available": self.is_docker_available(),
            "image_exists": self.image_exists(),
        }
        return info
