"""Sandbox runtime factory — selects and constructs the execution backend.

Owns the decision: "which CLI runner and command policy should this engine use,
given the current config and Docker availability?"

Callers receive a SandboxRuntime dataclass and store the runners — they do not
own the selection logic itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.core.sandbox.command_policy import CommandPolicy
from src.core.sandbox.docker_runner import DockerRunner
from src.core.sandbox.python_runner import PythonRunner

if TYPE_CHECKING:
    from src.core.config.app_config import AppConfig
    from src.core.runtime.activity_stream import ActivityStream
    from src.core.sandbox.docker_manager import DockerManager
    from src.core.sandbox.sandbox_manager import SandboxManager


@dataclass
class SandboxRuntime:
    """All runtime components that depend on the docker-vs-local decision."""
    cli_runner: Any                    # DockerRunner | CliRunner
    docker_runner: DockerRunner | None
    python_runner: PythonRunner
    command_policy: CommandPolicy


def build_sandbox_runtime(
    config: "AppConfig",
    sandbox: "SandboxManager",
    docker_manager: "DockerManager",
    *,
    activity: "ActivityStream",
    on_confirm_destructive=None,
    on_confirm_gui_launch=None,
) -> SandboxRuntime:
    """Decide which execution backend to use and instantiate the required runners.

    Returns a SandboxRuntime with cli_runner, docker_runner, python_runner, and
    command_policy — callers must not replicate this logic.

    Decision rule:
    - If docker_enabled AND Docker is actually available → Docker container mode
    - Otherwise → local subprocess mode (allowlist policy)
    """
    if config.docker_enabled and docker_manager.is_docker_available():
        docker_runner = DockerRunner(
            docker_manager, activity,
            on_confirm_destructive=on_confirm_destructive,
            audit_log=sandbox.audit,
        )
        command_policy = CommandPolicy(mode="permissive")
        python_runner = PythonRunner(
            sandbox.guard, activity,
            audit_log=sandbox.audit,
            docker_manager=docker_manager,
            gui_policy_getter=lambda: config.gui_launch_policy,
            on_confirm_gui_launch=on_confirm_gui_launch,
        )
        activity.info("engine",
            f"Docker sandbox mode — container: {docker_manager.container_status()}")
        return SandboxRuntime(
            cli_runner=docker_runner,
            docker_runner=docker_runner,
            python_runner=python_runner,
            command_policy=command_policy,
        )
    else:
        command_policy = CommandPolicy(mode="allowlist")
        python_runner = PythonRunner(
            sandbox.guard, activity,
            audit_log=sandbox.audit,
            gui_policy_getter=lambda: config.gui_launch_policy,
            on_confirm_gui_launch=on_confirm_gui_launch,
        )
        if config.docker_enabled:
            activity.warn("engine",
                "Docker enabled but not available — falling back to local sandbox")
        return SandboxRuntime(
            cli_runner=sandbox.cli,
            docker_runner=None,
            python_runner=python_runner,
            command_policy=command_policy,
        )
