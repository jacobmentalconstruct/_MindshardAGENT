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
- published Prompt Lab packages
- active Prompt Lab state
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
- Published packages are the only publishable design bundles.
- Active state must point only to a published package, never to drafts or loose
  design objects.
- Publish requires a structurally valid Prompt Lab state and a package
  selection that fully covers the enabled nodes of the selected execution plan.

## Project-local storage root

- `.mindshard/prompt_lab/`

## Phase 1B package contract

- published packages live under `.mindshard/prompt_lab/published/`
- active state lives under `.mindshard/prompt_lab/active/`
- promotion history remains indexed in SQLite
- the main app is still expected to consume only active published state when
  runtime integration lands

## Phase 1C operational doctrine

- Prompt Lab MCP tools operate on the same canonical services and storage as the CLI.
- Prompt Lab administrative and runtime-facing actions are logged to
  `.mindshard/prompt_lab/operations.jsonl`.
- Runtime inspection/loaders resolve only the explicit active published package.
- The main app may summarize and reload Prompt Lab state, but it must not derive
  runtime behavior from drafts or loose design objects.

## Phase 2 workbench doctrine

- The dedicated Prompt Lab workbench is the real subsystem UI surface.
- The main app bridge remains a launch/summary/reload seam only.
- The workbench stays read/admin-safe until richer editing phases are
  deliberately implemented.
- `Open Lab` should now open the dedicated Prompt Lab workbench, not merely the
  filesystem location.
- runtime/apply feedback should be explicit and calm: status lines, validation
  visibility, and activation outcomes should be inspectable without widening
  the main-app bridge
- evaluation and promotion history should deepen through inspect-first surfaces
  before any broader editing power is introduced

## Prompt Training Regimen V0 doctrine

- training suites are Prompt Lab design objects and are JSON-canonical under
  `.mindshard/prompt_lab/training_suites/`
- training-generated overlay prompt text belongs under
  `.mindshard/prompt_lab/source_overlays/`
- training runs are indexed SQLite history objects and are canonical as
  `training_run` records
- V0 training operates on one prompt profile at a time against a published
  baseline package while keeping execution plans and bindings fixed
- training outputs are draft recommendations only:
  - candidate draft profiles
  - overlay source files
  - recorded scorecards and deltas
  - recommended winner, if any
- V0 training must not publish or activate anything automatically
- deterministic checks remain the primary scoring layer; tiny-model judging is
  optional and additive, never authoritative over deterministic failures
- `_docs/benchmark_suite.json` is only a seed source; runtime training suites
  must be owned by Prompt Lab after import
