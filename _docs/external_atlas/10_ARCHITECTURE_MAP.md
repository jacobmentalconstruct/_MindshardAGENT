# 10 Architecture Map

## Architecture Shape

MindshardAGENT is organized into a few major layers:

- app layer
- core layer
- UI layer
- Prompt Lab layer
- MCP/server layer
- storage/state layer

These are not perfectly isolated in the abstract, but the current structure is intentionally moving toward clearer ownership boundaries.

## Layer 1: App Layer

The app layer is the orchestration shell around the desktop application.

Representative files:
- `src/app.py`
- `src/app_bootstrap.py`
- `src/app_lifecycle.py`
- `src/app_state.py`
- `src/app_streaming.py`
- `src/app_session.py`
- `src/app_prompt.py`
- `src/app_prompt_lab.py`
- `src/app_commands.py`

Responsibilities:
- create the app runtime
- wire callbacks
- connect UI actions to deeper services
- manage lifecycle and shutdown
- bridge the main app UI to Prompt Lab summary/open/reload behavior

This layer should coordinate, not become the home of deep domain logic.

## Layer 2: Core Layer

The core layer contains the runtime and domain logic.

Representative anchors:
- `src/core/engine.py`
- `src/core/agent/`
- `src/core/sandbox/`
- `src/core/project/`
- `src/core/sessions/`
- `src/core/prompt_lab/`
- `src/core/runtime/`
- `src/core/config/`
- `src/core/vcs/`
- `src/core/vault/`

This is the layer that owns:
- agent loops and prompt assembly
- sandbox/process execution
- project attachment/detachment logic
- session and evidence/knowledge state
- Prompt Lab canonical objects and services
- runtime logging and event flow

## Layer 3: UI Layer

The UI layer is the visible Tkinter interface.

Representative anchors:
- `src/ui/gui_main.py`
- `src/ui/ui_facade.py`
- `src/ui/ui_state.py`
- `src/ui/panes/`
- `src/ui/widgets/`
- `src/ui/dialogs/`

This layer owns:
- desktop layout
- panes, widgets, dialogs
- user-visible controls and summaries
- main app Prompt Workbench

The UI layer should not own deep runtime behavior.

## Layer 4: Prompt Lab Layer

Prompt Lab is both:
- a core service/data model under `src/core/prompt_lab/`
- a separate subsystem entry surface under `src/prompt_lab/`

Core Prompt Lab owns:
- canonical records
- storage
- validation
- package state
- operation logs
- runtime loader
- services for sources, profiles, plans, bindings, and packages

Prompt Lab entrypoints own:
- CLI
- MCP server
- dedicated Tk workbench
- entrypoint wiring

This is an important architectural distinction:
- `src/core/prompt_lab/` is the real subsystem logic
- `src/prompt_lab/` is how operators and agents enter it

## Layer 5: MCP / Server Layer

The repo exposes server surfaces for external control.

Representative files:
- `mcp_agent_server.py`
- `mcp_prompt_lab_server.py`
- `mcp_ui_bridge_server.py`
- `src/mcp/server.py`
- `src/mcp/ui_bridge_server.py`
- `src/prompt_lab/mcp_server.py`

These layers expose:
- main agent/server operations
- UI bridge surfaces
- Prompt Lab tool surface

The MCP layer should call established services, not duplicate domain behavior.

## Layer 6: Storage / State Layer

Storage is intentionally split by kind of truth.

Key locations:
- `.mindshard/`
- `.prompt-versioning/`
- `_docs/_journalDB/app_journal.sqlite3`
- `prompt_lab/`
- `.mindshard/prompt_lab/`

These do different jobs:
- project-local runtime state
- prompt tuning and evaluation state
- builder/project memory
- Prompt Lab assets and project-local Prompt Lab state

## Architecture Diagram

```text
User
  -> Main Tk App
     -> app-layer shims
     -> UIFacade / panes / widgets
     -> Engine
        -> Agent subsystem
        -> Sandbox subsystem
        -> Project subsystem
        -> Sessions subsystem
        -> Runtime subsystem
     -> Prompt Lab bridge

Prompt Lab Workbench / CLI / MCP
  -> Prompt Lab entrypoints
  -> core.prompt_lab services
  -> Prompt Lab storage and package state

Builder / Project Memory
  -> app journal SQLite
```

## Current Important Boundary

One of the most important current architecture rules is:

- the main app exposes only a narrow Prompt Lab bridge
- Prompt Lab itself is the dedicated design/evaluation workbench

This prevents the main app from slowly becoming the full prompt-engineering suite by accident.
