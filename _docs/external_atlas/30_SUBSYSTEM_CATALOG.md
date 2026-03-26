# 30 Subsystem Catalog

## How To Use This Catalog

Each section below describes:
- what the subsystem is for
- what it owns
- what it should not be confused with
- where its anchor files live

## Main App Shell

**Purpose**
- visible desktop operator shell
- app bootstrap, lifecycle, and app-layer coordination

**Owns**
- startup wiring
- lifecycle wiring
- UI callback shims
- session/app coordination

**Anchor files**
- `src/app.py`
- `src/app_bootstrap.py`
- `src/app_lifecycle.py`
- `src/app_state.py`

**Do not confuse with**
- core runtime logic
- Prompt Lab subsystem logic

## Engine Runtime

**Purpose**
- central runtime coordinator for the active agent session

**Owns**
- prompt submission entry
- loop dispatch
- sandbox binding
- knowledge/evidence binding
- history handling

**Anchor files**
- `src/core/engine.py`
- `src/core/agent/response_runtime_builder.py`

**Do not confuse with**
- individual loop logic
- app-layer bootstrap

## Agent / Loop System

**Purpose**
- define and execute the agent’s reasoning modes

**Owns**
- loop selection
- loop contract
- loop execution behavior
- prompt-building flow
- transcript hygiene around tool use

**Anchor files**
- `src/core/agent/loop_manager.py`
- `src/core/agent/loop_selector.py`
- `src/core/agent/loop_types.py`
- `src/core/agent/response_loop.py`
- `src/core/agent/prompt_builder.py`

**Representative loop files**
- `direct_chat_loop.py`
- `planner_only_loop.py`
- `thought_chain_loop.py`
- `review_judge_loop.py`
- `recovery_agent_loop.py`

## Sandbox / Tool System

**Purpose**
- controlled local execution against the project workspace

**Owns**
- CLI execution
- file writing
- tool discovery
- command policy
- Docker-backed or local runtime decisions

**Anchor files**
- `src/core/sandbox/cli_runner.py`
- `src/core/sandbox/file_writer.py`
- `src/core/sandbox/tool_discovery.py`
- `src/core/sandbox/tool_catalog.py`
- `src/core/sandbox/command_policy.py`
- `src/core/sandbox/docker_manager.py`

## Project Lifecycle System

**Purpose**
- attach, detach, archive, and describe the active project/workspace

**Owns**
- project metadata
- project attach/detach workflows
- sidecar archiving
- source/service file access related to the project

**Anchor files**
- `src/core/project/project_command_handler.py`
- `src/core/project/project_lifecycle.py`
- `src/core/project/project_meta.py`
- `src/core/project/project_archiver.py`
- `src/core/project/workspace_context.py`

## Sessions / Knowledge / Evidence

**Purpose**
- persistent per-project session and auxiliary memory state

**Owns**
- session storage
- knowledge storage
- evidence bag adapter
- turn knowledge writing

**Anchor files**
- `src/core/sessions/session_store.py`
- `src/core/sessions/knowledge_store.py`
- `src/core/sessions/evidence_adapter.py`
- `src/core/sessions/turn_knowledge_writer.py`

## Runtime / Activity Infrastructure

**Purpose**
- runtime logging, activity, eventing, journaling, and monitoring helpers

**Owns**
- activity stream
- event bus
- runtime logger
- action journal
- resource monitoring

**Anchor files**
- `src/core/runtime/activity_stream.py`
- `src/core/runtime/event_bus.py`
- `src/core/runtime/runtime_logger.py`

## UI System

**Purpose**
- compose the visible desktop interface

**Owns**
- main window
- layout panes
- widgets
- UI state
- UI facade

**Anchor files**
- `src/ui/gui_main.py`
- `src/ui/ui_facade.py`
- `src/ui/ui_state.py`
- `src/ui/panes/control_pane.py`
- `src/ui/panes/prompt_workbench.py`
- `src/ui/panes/prompt_workbench_tabs.py`

## Prompt Workbench

**Purpose**
- prompt-facing operator inspection surface inside the main app

**Owns**
- compiled prompt summary
- source stack inspection
- inspect/tools/bag tabs
- Prompt Lab summary bridge in the main app

**Anchor files**
- `src/app_prompt.py`
- `src/app_prompt_lab.py`
- `src/ui/panes/prompt_workbench.py`
- `src/ui/panes/prompt_workbench_tabs.py`

**Do not confuse with**
- the separate Prompt Lab workbench

## Prompt Lab Core

**Purpose**
- canonical prompt/execution design subsystem

**Owns**
- prompt profiles
- execution plans
- binding records
- package publication/activation
- validation
- operation log
- runtime loader

**Anchor files**
- `src/core/prompt_lab/contracts.py`
- `src/core/prompt_lab/storage.py`
- `src/core/prompt_lab/validation.py`
- `src/core/prompt_lab/services.py`
- `src/core/prompt_lab/runtime_loader.py`
- `src/core/prompt_lab/package_service.py`

## Prompt Lab Entry Surfaces

**Purpose**
- human and agent entrypoints into Prompt Lab

**Owns**
- CLI
- MCP surface
- dedicated Tk workbench
- subsystem `main.py` entrypoint

**Anchor files**
- `src/prompt_lab/main.py`
- `src/prompt_lab/cli.py`
- `src/prompt_lab/mcp_server.py`
- `src/prompt_lab/workbench.py`

## MCP Surfaces

**Purpose**
- expose app and subsystem capabilities through server/tool interfaces

**Anchor files**
- `src/mcp/server.py`
- `src/mcp/ui_bridge_server.py`
- `mcp_agent_server.py`
- `mcp_ui_bridge_server.py`
- `mcp_prompt_lab_server.py`

## Builder Memory / Journal

**Purpose**
- long-lived project and builder continuity

**Owns**
- dev logs
- TODOs
- doctrine
- work logs
- specs mirrored into journal entries

**Anchor locations**
- `_docs/_journalDB/app_journal.sqlite3`
- `.dev-tools/_app-journal/`

**Do not confuse with**
- Prompt Lab runtime data
- project-local agent sidecar state
