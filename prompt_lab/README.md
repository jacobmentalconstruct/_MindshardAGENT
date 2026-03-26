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

Phase 1B additions:

- concrete source/profile/plan/binding service families now sit behind storage
- the published package contract is now real and JSON-backed
- the active Prompt Lab state is now real and JSON-backed
- publish/activate operations are available through the Prompt Lab CLI
- runtime consumption is still deferred, but the contract boundary is now explicit

Phase 1C additions:

- a Prompt Lab MCP server now exposes inspection/admin-safe service operations
- Prompt Lab operations are recorded in `.mindshard/prompt_lab/operations.jsonl`
- runtime loading now resolves only explicit active published state
- the main app now shows a Prompt Lab summary and can reload that state on demand
- the main app still does not edit Prompt Lab state directly

Phase 2 additions:

- `src/prompt_lab/main.py` now launches a dedicated minimal Prompt Lab workbench
- the workbench exposes restrained Sources, Build, Execution, Bindings,
  Promotion, and Evaluation surfaces over the settled services
- `Open Lab` from the main app now opens the dedicated Prompt Lab workbench
  instead of only opening the state folder on disk
- the main app bridge remains intentionally narrow: inspect, reload, open, and
  status only

Phase 2 polish additions:

- the dedicated workbench now gives clearer operator feedback for validation,
  activation, and reload actions
- the Promotion tab now makes active-package state and package history easier
  to inspect before activating anything
- the Evaluation tab now exposes validation snapshots, promotion records, eval
  runs, and recent operations as separate inspectable surfaces
- these additions stay inspection/admin-safe and do not turn Prompt Lab into an
  uncontrolled freeform editor

Primary subsystem entrypoint:

- `src/prompt_lab/main.py`

This is intentionally not named `app.py` so the Prompt Lab subsystem remains
clearly distinct from the main MindshardAGENT application entrypoint.

Prompt Lab runtime/design data belongs under:

- `.mindshard/prompt_lab/`

Prompt Lab code belongs under:

- `src/core/prompt_lab/`
- `src/prompt_lab/`
