# Prompt Lab

Prompt Lab is the app-owned maintenance, training, and design subsystem for
MindshardAGENT.

This folder holds subsystem-owned static assets and human-facing reference
material for the Prompt Lab package. It is not the canonical home for builder
project memory. Builder-side planning records such as dev log, TODO, north-star
notes, and onboarding remain in the app journal.

Phase 1 scaffold goals:

- establish a first-class Prompt Lab package in `src/`
- define the storage doctrine for project-local Prompt Lab data
- provide import-safe entrypoint shells for CLI, MCP, and workbench use
- avoid implementing real subsystem behavior yet

Phase 1A additions:

- canonical Prompt Lab objects are now real import-safe data records
- JSON design storage is canonical for profiles, plans, bindings, and artifacts
- SQLite history storage is canonical for eval, validation, and promotion records
- CLI support remains inspection-first and admin-safe, not a freeform editing path
- the main app must consume only explicit active published state, never drafts

Primary subsystem entrypoint:

- `src/prompt_lab/main.py`

This is intentionally not named `app.py` so the Prompt Lab subsystem remains
clearly distinct from the main MindshardAGENT application entrypoint.

Prompt Lab runtime/design data belongs under:

- `.mindshard/prompt_lab/`

Prompt Lab code belongs under:

- `src/core/prompt_lab/`
- `src/prompt_lab/`
