"""Agent-owned builders for tool/response runtime objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.core.agent.loop_registry import build_loop_manager
from src.core.agent.response_loop import ResponseLoop
from src.core.agent.tool_router import ToolRouter

if TYPE_CHECKING:
    from src.core.config.app_config import AppConfig
    from src.core.runtime.activity_stream import ActivityStream
    from src.core.sandbox.command_policy import CommandPolicy
    from src.core.sandbox.file_writer import FileWriter
    from src.core.sandbox.tool_catalog import ToolCatalog
    from src.core.sessions.knowledge_store import KnowledgeStore


@dataclass(frozen=True)
class ResponseRuntimeBundle:
    """Agent-owned runtime objects used by Engine during prompt execution."""

    tool_router: ToolRouter
    response_loop: ResponseLoop
    loop_manager: object


def build_agent_loop_manager(
    *,
    config: "AppConfig",
    activity: "ActivityStream",
    tool_catalog: "ToolCatalog",
    response_loop: ResponseLoop | None,
    sandbox_root_getter,
    active_project_getter,
):
    """Rebuild only the loop manager from already-live runtime objects."""

    return build_loop_manager(
        config=config,
        activity=activity,
        tool_catalog=tool_catalog,
        response_loop=response_loop,
        sandbox_root_getter=sandbox_root_getter,
        active_project_getter=active_project_getter,
    )


def build_response_runtime(
    *,
    config: "AppConfig",
    tool_catalog: "ToolCatalog",
    cli_runner,
    activity: "ActivityStream",
    file_writer: "FileWriter",
    sandbox_root: str,
    python_runner,
    command_policy: "CommandPolicy | None",
    knowledge_store: "KnowledgeStore | None",
    embed_fn,
    session_id_fn,
    journal,
    evidence_bag,
    vcs,
    active_project: str,
    project_meta,
    on_tools_reloaded=None,
    reload_tools_fn=None,
) -> ResponseRuntimeBundle:
    """Build tool router, response loop, and loop manager from current runtime state."""

    tool_router = ToolRouter(
        tool_catalog,
        cli_runner,
        activity,
        file_writer=file_writer,
        sandbox_root=sandbox_root,
        on_tools_reloaded=on_tools_reloaded,
        reload_tools_fn=reload_tools_fn,
        python_runner=python_runner,
    )

    response_loop = ResponseLoop(
        config,
        tool_catalog,
        tool_router,
        activity,
        command_policy=command_policy,
        knowledge_store=knowledge_store,
        embed_fn=embed_fn,
        session_id_fn=session_id_fn,
        docker_mode=False if command_policy is not None else True,
        journal=journal,
        file_writer=file_writer,
        evidence_bag=evidence_bag,
    )
    response_loop.set_workspace(
        vcs=vcs,
        active_project=active_project,
        project_meta=project_meta,
    )

    loop_manager = build_agent_loop_manager(
        config=config,
        activity=activity,
        tool_catalog=tool_catalog,
        response_loop=response_loop,
        sandbox_root_getter=lambda: config.sandbox_root,
        active_project_getter=lambda: active_project,
    )

    return ResponseRuntimeBundle(
        tool_router=tool_router,
        response_loop=response_loop,
        loop_manager=loop_manager,
    )
