# Storage Doctrine

Prompt Lab uses a strict separation between builder memory and app-owned
runtime/design state.

## Builder / project memory

These records belong in the app journal:

- architecture plans
- dev log
- TODOs
- north-star notes
- rollout decisions
- onboarding notes

## Prompt Lab runtime/design state

These records belong to the subsystem itself:

- prompt source libraries and source refs
- prompt profiles
- execution plans
- binding records
- build artifacts
- evaluation runs
- promotion records
- draft / published / active state

## Phase 1 persistence doctrine

- JSON is canonical for Prompt Lab design objects.
- SQLite is canonical for indexed evaluation history and promotion ledger.
- Prompt sources remain file-backed.
- The main app may consume only explicit active published state, never drafts.
- Prompt Lab stays service-first; dedicated managers are optional, not mandatory.
- The Phase 1 execution model is ordered-plan based but must retain
  graph-capable identity and relationship fields for later evolution.
- Prompt Lab CLI commands are inspection/admin oriented and must not become an
  uncontrolled editing surface.

## Project-local storage root

- `.mindshard/prompt_lab/`
