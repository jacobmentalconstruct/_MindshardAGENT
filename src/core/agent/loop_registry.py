"""
FILE: loop_registry.py
ROLE: Loop instantiation and registration for the engine's LoopManager.
WHAT IT OWNS:
  - build_loop_manager: creates a fresh LoopManager and registers all available loops.

This module owns the LOOP SELECTION POLICY — which loop types exist and in what
order they are registered (which determines dispatch priority). Engine calls
build_loop_manager() whenever the runtime context changes (sandbox set, project
changed, knowledge store updated).

Domain: agent (single domain — valid component)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.agent.direct_chat_loop import DirectChatLoop
from src.core.agent.loop_manager import LoopManager
from src.core.agent.planner_only_loop import PlannerOnlyLoop
from src.core.agent.recovery_agent_loop import RecoveryAgentLoop
from src.core.agent.review_judge_loop import ReviewJudgeLoop
from src.core.agent.thought_chain_loop import ThoughtChainLoop

if TYPE_CHECKING:
    from src.core.agent.response_loop import ResponseLoop
    from src.core.config.app_config import AppConfig
    from src.core.runtime.activity_stream import ActivityStream
    from src.core.sandbox.tool_catalog import ToolCatalog


def build_loop_manager(
    config: "AppConfig",
    activity: "ActivityStream",
    tool_catalog: "ToolCatalog",
    response_loop: "ResponseLoop | None",
    sandbox_root_getter,
    active_project_getter,
) -> LoopManager:
    """Instantiate and register all available loops into a new LoopManager.

    Owns which loop types are available and their registration order.
    Engine replaces self.loop_manager with the result whenever context changes.
    """
    manager = LoopManager(activity)
    manager.register(DirectChatLoop(config, activity))
    manager.register(
        PlannerOnlyLoop(
            config,
            activity,
            tool_catalog,
            sandbox_root_getter=sandbox_root_getter,
            active_project_getter=active_project_getter,
        )
    )
    manager.register(ThoughtChainLoop(config, activity))
    if response_loop is not None:
        manager.register(response_loop)
        manager.register(RecoveryAgentLoop(activity, tool_agent_loop=response_loop))
        manager.register(ReviewJudgeLoop(config, activity, tool_agent_loop=response_loop))
    return manager
