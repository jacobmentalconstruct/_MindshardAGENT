# Final Tools

This folder is a vendable, headless, agent-first local tooling project.

It is designed to be copied or zipped into future workspaces and extended over time without losing a predictable mechanical contract.

## Folder Layout

- `tools/`
  - the actual user-facing tools
- `jobs/`
  - example JSON inputs for running tools mechanically
- `artifacts/`
  - intended home for generated indexes, summaries, and maps
- `drop-bin/`
  - staging area for random scripts or rough tools that still need to be converted
- `lib/`
  - internal shared analysis helpers used by the tool family
- `common.py`
  - shared runtime and CLI contract
- `mcp_server.py`
  - MCP stdio wrapper over the toolset
- `smoke_test.py`
  - portable self-test after copying or unzipping
- `tool_manifest.json`
  - machine-readable manifest for the project
- `BUILDER_GUIDE.md`
  - builder contract, roadmap, and extension notes
- `VENDORING.md`
  - instructions for zipping, storing, and reusing the folder
- `STRANGLER_MAP.md`
  - legacy-to-final mapping

## Core Rules

- No UI.
- Every tool follows the same file structure.
- Every tool exposes the same entrypoints.
- Every tool returns the same JSON envelope.
- MCP calls the same `run(arguments)` used by CLI execution.

## Standard CLI Contract

All tool scripts support:

```powershell
python .final-tools\tools\<tool>.py metadata
python .final-tools\tools\<tool>.py run --input-json "{...}"
python .final-tools\tools\<tool>.py run --input-file path\to\job.json
```

## MCP

Run:

```powershell
python .final-tools\mcp_server.py
```

## Included Tools

- `workspace_audit`
- `data_shape_inspector`
- `structured_patch`
- `python_risk_scan`
- `tk_ui_map`
- `tk_ui_thread_audit`
- `tk_ui_event_map`
- `tk_ui_layout_audit`
- `tk_ui_test_scaffold`

## Portability Goal

This folder should stay safe to:

- zip and archive
- copy into new projects
- extend with additional tools
- expose through MCP without per-tool glue code
