# 60 Integration Seams

## Purpose

This document maps the places where newer work joins older structures.
These are the most important places to inspect when looking for integration bugs or architectural drift.

## Why Seams Matter Here

MindshardAGENT has grown across multiple refactor tranches.
That means some of the highest-value review targets are not isolated subsystems, but the join points between them.

## Seam 1: App Layer -> Engine

Primary files:
- `src/app_streaming.py`
- `src/app_commands.py`
- `src/core/engine.py`

This seam translates UI/app actions into engine runtime behavior.

Risks:
- callback bugs
- stale state handoff
- accidental app-layer ownership of core logic

Recent example:
- the direct CLI-panel callback bug caused by a missing `threading` import in `src/app_commands.py`

## Seam 2: Project Lifecycle -> Runtime State

Primary files:
- `src/core/project/project_command_handler.py`
- `src/core/project/project_lifecycle.py`
- `src/core/engine.py`
- `src/app_session.py`
- `src/app_prompt.py`
- `src/app_prompt_lab.py`

This seam is responsible for keeping project attachment/detachment aligned with:
- session state
- prompt inspector state
- Prompt Lab summary state
- window/project labels

Risks:
- stale UI after attach/detach
- stores still pointing at the old project
- stale Prompt Lab summary state

Recent example:
- Prompt Lab summary now refreshes automatically on attach, self-attach, and detach success

## Seam 3: Main App Prompt Workbench -> Prompt Lab

Primary files:
- `src/app_prompt_lab.py`
- `src/ui/panes/prompt_workbench_tabs.py`
- `src/core/prompt_lab/runtime_loader.py`

This seam is intentionally narrow.

It should expose only:
- summary
- reload
- open
- status

It should not become:
- prompt profile editor
- execution plan editor
- binding mutation surface
- evaluation management surface

This is a critical architectural boundary.

## Seam 4: Prompt Lab Entry Surface -> Prompt Lab Core

Primary files:
- `src/prompt_lab/main.py`
- `src/prompt_lab/cli.py`
- `src/prompt_lab/mcp_server.py`
- `src/prompt_lab/workbench.py`
- `src/core/prompt_lab/services.py`

This seam matters because Prompt Lab should be:
- tool-first
- service-first
- UI layered over stable services

Risks:
- UI starts duplicating domain behavior
- entrypoints disagree about object/state meaning
- MCP and UI diverge from the same service layer

## Seam 5: Prompt Lab Published State -> Runtime Loader

Primary files:
- `src/core/prompt_lab/runtime_loader.py`
- `src/core/prompt_lab/package_service.py`
- `src/core/prompt_lab/storage.py`

This seam enforces one of the system’s most important truth boundaries:
- drafts are not runtime truth
- only active published state is runtime-consumable

Risks:
- draft leakage into runtime behavior
- active state out of sync with published records
- inconsistent package resolution

## Seam 6: Tool Router -> Transcript / UI

Primary files:
- `src/core/agent/tool_router.py`
- `src/core/agent/transcript_formatter.py`
- `src/core/agent/turn_pipeline.py`
- `src/app_streaming.py`

This seam is where executable tool behavior meets user-visible transcript behavior.

Key boundary:
- raw tool calls should execute
- user-visible chat should not imitate executable tool syntax

This seam was already hardened in earlier work to keep `TOOL_CALLS:`-style output out of persisted transcript content.

## Seam 7: UI Threads / Workers

Primary files:
- `src/app_polling.py`
- `src/app_ui_bridge.py`
- `src/ui/widgets/vcs_panel.py`

This seam governs background work and UI-thread safety.

Risks:
- blocking work on the UI thread
- direct widget mutation from worker threads
- brittle scheduling patterns

Static audits still flag this area as a continuing watch surface.

## Best Review Starting Points

When doing a fast integration review, start here:
1. `src/app_prompt_lab.py`
2. `src/core/project/project_command_handler.py`
3. `src/app_commands.py`
4. `src/core/prompt_lab/runtime_loader.py`
5. `src/prompt_lab/workbench.py`
6. `src/ui/panes/prompt_workbench_tabs.py`
