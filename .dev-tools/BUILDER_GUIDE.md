# Builder Guide

This file records the task list, builder contract, and handoff notes for anyone extending this tool project.

## Purpose

`.final-tools` is meant to become a reusable local tooling kit for AI agents working inside project folders.

The target use cases are:

- understanding an unfamiliar codebase
- understanding local data files and documents
- making safe edits
- running lightweight static analysis
- exposing those capabilities over MCP

## Builder Contract

These are the rules I am explicitly trying to preserve as the builder of this toolkit.

### Non-negotiable contract

- No UI.
- Every tool must be headless and scriptable.
- Every tool must be usable both directly and through MCP.
- Every tool must export `FILE_METADATA`.
- Every tool must export `run(arguments: dict) -> dict`.
- Every tool must use `standard_main(...)` from `common.py`.
- Every tool must return the same top-level JSON envelope:
  - `status`
  - `tool`
  - `input`
  - `result`
- Every tool script must include a file header explaining:
  - what it is
  - what it does
  - how to use it
  - expected input object
- MCP must call the same `run(arguments)` path as CLI use. No duplicated business logic.
- A new tool should be deterministic by default and avoid hidden state.

### Project hygiene rules

- Keep files ASCII unless there is a real reason not to.
- Keep dependencies minimal and prefer the Python standard library.
- Preserve portable paths and simple startup.
- Add documentation when adding a capability, not afterward.
- Prefer machine-friendly JSON outputs over prose-heavy outputs.
- Prefer additive evolution over breaking contract changes.

### Tool addition checklist

When adding a new tool:

1. Add the script under `tools/`.
2. Add a clear header at the top of the file.
3. Define `FILE_METADATA`.
4. Implement `run(arguments)`.
5. Use `standard_main(FILE_METADATA, run)`.
6. Register the tool in `mcp_server.py`.
7. Add the tool to `tool_manifest.json`.
8. Add at least one example job JSON under `jobs/examples/`.
9. Add or update docs in this file if the contract changes.
10. Smoke-test `metadata`, `run`, and MCP registration.

### Drop-bin intake rules

Use `drop-bin/` as the only place for raw incoming scripts that are not yet normalized.

- Anything in `drop-bin/` is considered intake, not part of the official tool suite.
- A script should not be exposed through MCP directly from `drop-bin/`.
- A script should not be treated as vend-stable until it is promoted into `tools/`.
- If a dropped script is project-specific, keep it in `drop-bin/` or move it into a project-only folder outside this reusable toolkit.
- If a dropped script is broadly reusable, convert it into a proper final tool and then add it to `tools/`.

### Promotion checklist from drop-bin to tools

When promoting a script from `drop-bin/`:

1. Decide whether it is truly reusable.
2. Strip out UI assumptions and project-specific assumptions.
3. Rewrite the header so it matches the suite style.
4. Add `FILE_METADATA`.
5. Convert the entrypoint to `run(arguments)`.
6. Route CLI handling through `standard_main(...)`.
7. Register it in `mcp_server.py`.
8. Add it to `tool_manifest.json`.
9. Add an example job JSON.
10. Update this guide if the suite contract changed.

## Current Toolset

- `workspace_audit`
  - folder orientation
- `data_shape_inspector`
  - local data structure inspection
- `structured_patch`
  - safe structured edits
- `python_risk_scan`
  - practical AST-based risk scanning
- `tk_ui_map`
  - Tkinter-oriented UI structure mapping
- `tk_ui_thread_audit`
  - blocking-callback and thread-safety audit
- `tk_ui_event_map`
  - callback and event graph extraction
- `tk_ui_layout_audit`
  - layout and geometry hotspot audit
- `tk_ui_test_scaffold`
  - unittest smoke-test generation for UI classes

## Planned Next Tools

These are the next recommended additions, in order.

### Turn 0: shared foundation

- Add safe reusable file loaders.
- Add path classification helpers for code, docs, tests, config, assets, and data.
- Add a shared artifact-writing helper under `artifacts/`.
- Add tiny fixtures for smoke testing.

### Turn 1: `codebase_index`

- Extract symbols, imports, entrypoints, and file summaries.
- Emit a deterministic codebase index artifact.

### Turn 2: `dependency_graph`

- Build module/file dependency edges.
- Highlight cycles, hotspots, and dependents.

### Turn 3: `docs_catalog`

- Index local docs by file, heading, and section.
- Link docs to code when possible.

### Turn 4: `config_surface`

- Map env vars, config files, ports, commands, and flags.

### Turn 5: `test_map`

- Discover tests, frameworks, commands, and source-to-test relationships.

### Turn 6: `change_impact`

- Use the earlier artifacts to estimate likely affected code, docs, config, and tests.

## Tkinter Tool Family

Because many projects in this environment use Tkinter heavily, the suite should carry a small family of Tkinter-aware tools.

### Implemented now

- `tk_ui_map`
  - maps windows, dialogs, widget construction, layout calls, event bindings, scheduling calls, and UI composition
- `tk_ui_thread_audit`
  - flags blocking UI callbacks and worker-thread targets that appear to touch UI directly
- `tk_ui_event_map`
  - maps callback edges from commands, binds, protocol handlers, schedulers, and thread starts
- `tk_ui_layout_audit`
  - flags mixed geometry use, global binds, manual sash placement, and hard-coded sizing
- `tk_ui_test_scaffold`
  - generates unittest smoke-test scaffolds for discovered UI classes

### Recommended next

- `tk_ui_render_probe`
  - headless or semi-headless widget tree instantiation probe for smoke-checking complex windows
- `tk_ui_state_flow`
  - map how UI state objects move between panes, dialogs, and callbacks
- `tk_ui_command_surface`
  - summarize user-triggerable commands, shortcuts, faux-button surfaces, and menu actions

### Guidance on parser choice

- Start with Python AST when the goal is portability and fast implementation.
- Introduce Tree-sitter later when stronger structural querying and incremental parsing are worth the extra dependency.
- If Tree-sitter is added, keep the mechanical contract identical and make it an internal implementation detail, not a separate tool contract.

## Notes For The Next Creator

- Resist the urge to add one-off project-specific tools unless they are clearly reusable.
- If a tool solves only one repo's conventions, keep it outside this reusable base pack.
- Prefer small composable tools over one giant "understand everything" tool.
- If a tool needs many helper functions, promote those helpers into `common.py` or a future `lib/` folder instead of copying logic between scripts.
- Prefer writing artifacts that later tools can consume.
- If you must break the contract, update this file and `tool_manifest.json` in the same change.

## Notes For The User Of This Toolkit

- Start with `workspace_audit` when dropped into a new repo.
- Use `data_shape_inspector` for unknown local files.
- Use `python_risk_scan` before and after edits in Python-heavy projects.
- Use `structured_patch` when you want mechanical, replayable changes instead of ad hoc editing.
- Prefer `--input-file` job JSON for automation and MCP-backed flows.

## Suggested Archive Shape

If you want to zip and reuse this folder across projects, this is the intended stable shape:

- `.final-tools/README.md`
- `.final-tools/BUILDER_GUIDE.md`
- `.final-tools/STRANGLER_MAP.md`
- `.final-tools/tool_manifest.json`
- `.final-tools/common.py`
- `.final-tools/mcp_server.py`
- `.final-tools/smoke_test.py`
- `.final-tools/tools/`
- `.final-tools/jobs/`
- `.final-tools/artifacts/`
- `.final-tools/drop-bin/`
