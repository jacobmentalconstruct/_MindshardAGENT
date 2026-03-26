# MindshardAGENT Onboarding — Next Session Handoff

## Purpose

This document is a verbose onboarding handoff for:
- the next builder session
- future agents joining midstream
- any technically serious reviewer who needs to understand where the project stands without replaying the entire conversation

This is a practical handoff, not a full specification.
It is meant to answer:
- what this app is
- what was just completed
- what is currently stable
- what records are canonical
- what should happen next
- what to avoid breaking

## Current Project Position

MindshardAGENT is now a stabilized local agent workbench with:
- a decomposed main app shell
- a functioning loop-based runtime
- sandbox/tool execution surfaces
- prompt inspection in the main app
- a dedicated Prompt Lab subsystem for prompt/execution design infrastructure
- MCP surfaces for the main agent, UI bridge, and Prompt Lab
- SQLite-backed builder memory via the app journal

The system is no longer in the same structural condition it was in before the recent cleanup/refactor passes.
The app is materially more coherent, more inspectable, and more bounded by explicit subsystem seams.

## What Was Completed In This Run

### Core stabilization and refactor continuation

Already completed before the final seam-review/documentation pass:
- app shell decomposition (`app.py`, `app_bootstrap.py`, `app_lifecycle.py`)
- ownership cleanup around `engine.py`, `app_commands.py`, and related app/core seams
- loop contract normalization
- Prompt Workbench decomposition
- Prompt Lab Phase 1A
- Prompt Lab Phase 1B
- Prompt Lab Phase 1C
- Prompt Lab Phase 2 minimal dedicated workbench
- Prompt Lab runtime/apply polish and evaluation/promotion inspection growth

### Prompt Lab subsystem result

Prompt Lab now exists as a first-class subsystem with:
- canonical data objects
- JSON-backed design-state storage
- SQLite-backed indexed history
- validation
- packages and active/published state
- runtime loader
- CLI
- MCP surface
- dedicated Tk workbench
- a narrow main-app bridge for summary/reload/open/status

### Post-integration seam review and hardening

A focused seam audit was performed after Prompt Lab integration.

Concrete fixes landed:
- `src/app_commands.py`
  - fixed the missing `threading` import for the CLI-panel callback path
- `src/core/project/project_command_handler.py`
  - Prompt Lab summary now refreshes automatically on:
    - attach sandbox
    - self-attach working copy
    - successful detach

New regression coverage:
- `tests/test_app_integration_seams.py`

## Verified State

Latest verified state after the seam audit:
- `python -m pytest tests\test_app_integration_seams.py tests\test_prompt_lab_phase1c.py -q` -> `8 passed`
- `python -m pytest -q` -> `63 passed`
- `python -m tests.test_tool_roundtrip` -> `92/92`

Prompt Lab and main app were also visually checked during this run:
- the main app Prompt Lab summary surface rendered cleanly
- the dedicated Prompt Lab workbench launched and displayed cleanly
- no visible errors were reported by the user during the UI pass

## Where The Truth Lives

One of the most important things for a future agent to understand is that the system has multiple truth layers.

### 1. Builder / project continuity truth

Location:
- `_docs/_journalDB/app_journal.sqlite3`

Use this for:
- dev log
- TODOs
- work logs
- roadmap
- next-session guidance
- doctrine
- design records

This is not runtime app state.

### 2. Project-local runtime state

Location:
- `.mindshard/`

Use this for:
- sessions
- logs
- state folders
- project-local sidecar data

### 3. Prompt Lab design and package state

Location:
- `.mindshard/prompt_lab/`

Use this for:
- prompt profiles
- execution plans
- bindings
- drafts
- published packages
- active package state
- build artifacts
- eval runs
- promotion records
- Prompt Lab SQLite DB and operation log

### 4. Prompt versioning / evaluation persistence

Location:
- `.prompt-versioning/`

## The Most Important Architectural Distinction

The most important current design distinction is:

- the main app is the live runtime/operator shell
- Prompt Lab is the separate prompt/execution design subsystem

The main app bridge to Prompt Lab is intentionally narrow:
- inspect
- reload
- open
- status only

It should not silently grow into:
- a full prompt profile editor
- an execution-plan editor
- a binding mutation surface
- a hidden replacement for the Prompt Lab workbench

## Prompt Lab Current Status

Prompt Lab is integrated and operational, but still mostly empty in product terms.

Infrastructure that exists:
- core canonical objects and services
- package contract
- active/published/draft state
- validation and promotion records
- operation log
- runtime loader
- CLI and MCP access
- dedicated workbench tabs:
  - Sources
  - Build
  - Execution
  - Bindings
  - Promotion
  - Evaluation

What is still next:
- author real prompt profiles
- author real execution plans
- author real bindings
- publish the first real package
- activate it
- verify the main app consumes it end to end

This is the next true product-building frontier.

## Main App Current Status

The main app is in a good place.

Important current qualities:
- app startup and shutdown are no longer centered in one giant file
- Prompt Workbench is a real inspection surface
- tool-call transcript hygiene is improved
- loop behavior is more contract-driven
- project attach/detach flows are more coherent
- Prompt Lab summary state now follows project lifecycle transitions correctly

Residual architectural noise still exists, but it is mostly known pressure, not emergency instability.

Known long-term hotspots still worth remembering:
- `src/core/engine.py`
- `src/app_bootstrap.py`
- some long-standing worker-thread/UI scheduling surfaces

Nothing in that set looked like a “must-fix tonight” breakage at end of session.

## Important Journal Entries To Read First

Canonical records:
- `journal_4570627c94a0` — Dev Log
- `journal_4ee1f592eeec` — TODO List
- `journal_9c8459f9f482` — Roadmap
- `journal_23ef3dbc0feb` — Next Session Guide

Prompt Lab records:
- `journal_80861681795a` — Prompt Lab TODO
- `journal_03a4367e64b8` — Prompt Lab Architecture Doctrine
- `journal_04dc82b3a583` — Prompt Lab North-Star Guardrails
- `journal_7ec641d66fbf` — Session 12 Work Log — Prompt Lab Phase 1A
- `journal_b51a6b5b424c` — Session 13 Work Log — Prompt Lab Phase 1B
- `journal_1c_phase14a6c3d9` — Session 14 Work Log — Prompt Lab Phase 1C
- `journal_d08f34280298` — Session 16 Work Log — Prompt Lab Phase 2 minimal workbench
- `journal_b66a47e0ebd8` — Session 17 Work Log — Prompt Lab polish and draw-down
- `journal_cb2b45322dd5` — Session 18 Work Log — Prompt Lab seam audit and stabilization

Builder/process doctrine:
- `journal_d0089a8d631f` — Builder Workflow Doctrine — Constraint Field and Tranche Discipline
- `journal_db115bbd05a0` — Builder Paradigm Doctrine — Reflective Workflow Description
- `journal_74db1e12f2f3` — Builder Constraint Contract

External-facing docs:
- `journal_faa130e1a87d` — External System Atlas

## Important Files To Read First

For app/runtime orientation:
- `src/app.py`
- `src/app_bootstrap.py`
- `src/app_lifecycle.py`
- `src/core/engine.py`
- `src/app_streaming.py`

For Prompt Workbench / Prompt Lab bridge:
- `src/app_prompt.py`
- `src/app_prompt_lab.py`
- `src/ui/panes/prompt_workbench.py`
- `src/ui/panes/prompt_workbench_tabs.py`

For project lifecycle:
- `src/core/project/project_command_handler.py`
- `src/core/project/project_lifecycle.py`
- `src/core/project/project_meta.py`

For Prompt Lab core:
- `src/core/prompt_lab/contracts.py`
- `src/core/prompt_lab/storage.py`
- `src/core/prompt_lab/services.py`
- `src/core/prompt_lab/validation.py`
- `src/core/prompt_lab/runtime_loader.py`
- `src/core/prompt_lab/package_service.py`

For Prompt Lab entrypoints:
- `src/prompt_lab/main.py`
- `src/prompt_lab/cli.py`
- `src/prompt_lab/mcp_server.py`
- `src/prompt_lab/workbench.py`

For current seam regressions and tests:
- `src/app_commands.py`
- `tests/test_app_integration_seams.py`

## External-Facing Atlas

A clean outward-facing doc pack now exists at:
- `_docs/external_atlas/`

Start there if the next agent needs:
- system orientation without raw repo dumps
- explainer/video/infographic prep
- a glossary or curated architecture map

Key atlas files:
- `README.md`
- `atlas_registry.json`
- `00_SYSTEM_OVERVIEW.md`
- `10_ARCHITECTURE_MAP.md`
- `20_RUNTIME_LIFECYCLE.md`
- `30_SUBSYSTEM_CATALOG.md`
- `40_FILE_TREE_GUIDE.md`
- `50_GLOSSARY.md`
- `60_INTEGRATION_SEAMS.md`
- `70_STORAGE_AND_TRUTH_MODEL.md`
- `80_OPERATOR_WORKFLOWS.md`
- `90_VIDEO_OVERVIEW_PROMPT.md`

That atlas is isolated from builder-only docs so it can be handed to other agents cleanly.

## Important Product/Prompt Notes

One meaningful product-language issue surfaced during testing:

When asked about its own environment or operating condition without enough attached context, smaller models can still produce generic fallback language like:
- “as an AI model...”

This is not a platform/integration failure.
It is a prompt-engineering and behavior-shaping target.

Future work here should steer the system toward responses more like:
- contextual uncertainty explanation
- explicit acknowledgement of missing monitoring access
- grounded operator-facing phrasing

This should become part of later prompt/behavior shaping work.

## Recommended Next Step

The next meaningful build step is:

### Begin the first real Prompt Lab authoring tranche

That means:
- create real prompt profiles
- create real execution plans
- create real bindings
- create a first real published package
- activate it
- verify the main app consumes the active published state correctly

This is the right next move because the infrastructure phase is already largely complete.
More infrastructure work now would risk motion without product learning.

## Things Not To Accidentally Do Next

- do not widen the main-app Prompt Lab bridge into a hidden full editor
- do not let drafts become runtime-consumable
- do not reintroduce giant inline lifecycle logic into `app.py`
- do not discard the app journal as the canonical continuity surface
- do not mix outward-facing atlas docs back into builder-only records

## Suggested Next Session Opening Sequence

1. Read:
   - `journal_4570627c94a0`
   - `journal_4ee1f592eeec`
   - `journal_23ef3dbc0feb`
   - `journal_cb2b45322dd5`

2. Skim:
   - `_docs/external_atlas/README.md`
   - `_docs/external_atlas/atlas_registry.json`

3. Inspect:
   - `src/core/prompt_lab/`
   - `src/prompt_lab/`
   - `src/app_prompt_lab.py`

4. Decide the first authored package target:
   - which loop role(s)
   - which prompt profile(s)
   - which execution plan shape
   - what “success” means for the first end-to-end package

## Final Status At Handoff

The app is in a strong state.

The runtime is stable.
Prompt Lab is real.
The join points have been reviewed and patched where needed.
The builder/project memory is updated.
The public-facing atlas exists.

The project is ready to move from infrastructure and integration into real authored Prompt Lab behavior.

