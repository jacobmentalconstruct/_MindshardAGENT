"""Sandbox-owned context builder for engine activation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.core.sandbox.file_writer import FileWriter
from src.core.sandbox.sandbox_manager import SandboxManager
from src.core.sandbox.sandbox_runtime_factory import SandboxRuntime, build_sandbox_runtime

if TYPE_CHECKING:
    from src.core.config.app_config import AppConfig
    from src.core.runtime.activity_stream import ActivityStream
    from src.core.sandbox.command_policy import CommandPolicy
    from src.core.sandbox.docker_manager import DockerManager
    from src.core.sandbox.docker_runner import DockerRunner
    from src.core.sandbox.python_runner import PythonRunner


@dataclass(frozen=True)
class SandboxContext:
    """All sandbox-owned runtime objects needed by the engine."""

    sandbox: SandboxManager
    file_writer: FileWriter
    docker_runner: DockerRunner | None
    python_runner: PythonRunner
    command_policy: CommandPolicy
    cli_runner: object


def build_sandbox_context(
    config: "AppConfig",
    *,
    activity: "ActivityStream",
    docker_manager: "DockerManager",
    sandbox_root: str,
    on_confirm_destructive=None,
    on_confirm_gui_launch=None,
) -> SandboxContext:
    """Create sandbox-owned runtime objects for the active sandbox root."""

    sandbox = SandboxManager(
        sandbox_root,
        activity,
        on_confirm_destructive=on_confirm_destructive,
        gui_policy_getter=lambda: config.gui_launch_policy,
        on_confirm_gui_launch=on_confirm_gui_launch,
    )

    file_writer = FileWriter(
        sandbox.guard,
        activity,
        audit_log=sandbox.audit,
    )

    runtime: SandboxRuntime = build_sandbox_runtime(
        config,
        sandbox,
        docker_manager,
        activity=activity,
        on_confirm_destructive=on_confirm_destructive,
        on_confirm_gui_launch=on_confirm_gui_launch,
    )

    return SandboxContext(
        sandbox=sandbox,
        file_writer=file_writer,
        docker_runner=runtime.docker_runner,
        python_runner=runtime.python_runner,
        command_policy=runtime.command_policy,
        cli_runner=runtime.cli_runner,
    )
