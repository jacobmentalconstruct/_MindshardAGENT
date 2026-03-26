# 20 Runtime Lifecycle

## Why This Document Exists

This document explains how the app moves through its major runtime states.

It focuses on:
- startup
- project attachment
- prompt submission
- loop execution
- Prompt Lab launch and runtime consumption
- shutdown

## 1. Startup

Startup begins at:
- `src/app.py`

That entrypoint delegates into:
- `src/app_bootstrap.py`

Bootstrap creates and wires:
- config
- logging
- activity/event infrastructure
- engine
- session and knowledge stores
- main window
- UI facade
- optional UI bridge
- prompt workbench summary state

After wiring is complete, the Tk main loop begins.

## 2. Initial Runtime State

At startup, the app establishes:
- a selected model context
- a sandbox root
- session store and knowledge store bindings
- prompt inspector state
- Prompt Lab summary state

If no active Prompt Lab package exists for the current project, the Prompt Lab summary reports that explicitly.

## 3. Project Attach Flow

Project attach is one of the most important runtime transitions.

The operator selects a project folder.
Then the system:
- updates `config.sandbox_root`
- rebinds the engine sandbox
- loads or creates project metadata
- updates window/project labels
- reinitializes session and knowledge stores
- creates a new session context
- refreshes prompt inspector state
- refreshes Prompt Lab summary state

This flow is coordinated in:
- `src/core/project/project_command_handler.py`

## 4. Self-Attach Flow

The app can also create and attach a self-edit working copy.

That flow:
- copies the source into a working destination
- attaches the resulting sandbox/project
- marks the project with a self-edit profile
- refreshes runtime state similarly to normal project attach

This is also coordinated from:
- `src/core/project/project_command_handler.py`

## 5. Prompt Submission Flow

When the user submits text in the main app:
- the UI hands it to the app layer
- the app layer routes it into the engine
- the engine builds a loop request
- the loop manager selects or honors the execution path
- the active loop runs
- tool calls and tokens stream back through callbacks
- results are appended to runtime history
- UI updates are posted through the app/UI layers

Major files involved:
- `src/app_streaming.py`
- `src/core/engine.py`
- `src/core/agent/loop_manager.py`
- `src/core/agent/loop_selector.py`
- `src/core/agent/response_loop.py`
- specific loop implementations under `src/core/agent/`

## 6. Loop Execution

The runtime uses multiple loop types, including:
- direct chat
- planner only
- thought chain
- review judge
- recovery agent

The loop family is governed by:
- `src/core/agent/loop_contract.md`
- `src/core/agent/loop_types.py`

The important lifecycle idea is that loops are not ad hoc.
They run through a contract for:
- request shape
- result shape
- history ownership
- stop semantics
- metadata

## 7. Tool Execution

When loops emit tool calls:
- the router parses them
- tools are resolved through the sandbox/tool catalog
- results are executed and formatted
- transcript-visible content is kept separate from raw executable tool syntax

Important files:
- `src/core/agent/tool_router.py`
- `src/core/sandbox/tool_catalog.py`
- `src/core/sandbox/tool_discovery.py`
- `src/core/sandbox/cli_runner.py`
- `src/core/sandbox/file_writer.py`

## 8. Prompt Inspection Flow

The main app includes a Prompt Workbench that can:
- inspect the compiled prompt
- inspect prompt sources
- inspect prompt-related surfaces
- show Prompt Lab summary state

This is not the deep authoring environment.
It is the live operator-facing inspection surface in the main app.

## 9. Prompt Lab Launch Flow

Prompt Lab can be launched from the main app bridge.

The bridge:
- determines the effective project root
- refreshes the active package summary
- launches the Prompt Lab workbench process
- records operation-log entries

Important file:
- `src/app_prompt_lab.py`

Prompt Lab entrypoint:
- `src/prompt_lab/main.py`

Dedicated workbench:
- `src/prompt_lab/workbench.py`

## 10. Prompt Lab Runtime Consumption

Prompt Lab runtime state is not consumed directly from drafts.

The runtime loader reads only:
- explicit active state
- explicit published package state

That loader then resolves:
- active package
- execution plan
- prompt profiles
- bindings

This is handled by:
- `src/core/prompt_lab/runtime_loader.py`

This is one of the most important safety boundaries in the system.

## 11. Detach Flow

When a project is detached:
- final archive/snapshot work runs
- sidecar state may be archived and optionally removed
- runtime state is cleared
- project labels and prompt inspector UI are cleared
- Prompt Lab summary state is refreshed

This keeps the operator from seeing stale project-specific Prompt Lab status after detach.

## 12. Shutdown

Shutdown is owned by:
- `src/app_lifecycle.py`

The shutdown path coordinates:
- active-stop requests
- timer cleanup
- save/teardown sequencing
- bridge shutdown
- engine stop
- store close

The important architectural point is that shutdown is no longer embedded as a giant inline block in `app.py`.
