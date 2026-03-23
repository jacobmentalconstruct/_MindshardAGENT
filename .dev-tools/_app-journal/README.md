# App Journal

This folder is an isolated SQLite-backed journal package for app notes, development history, operator notes, and agent logs.

It is designed for two use paths:

- user-facing Tkinter manager UI
- agent-facing MCP tools and mechanical CLI tools

## Purpose

Use this package when you want one durable place for:

- design notes
- bug notes
- dev logs
- decisions
- TODOs
- user feedback
- operational notes

Instead of scattering `FOOFOOFOO.md` files everywhere, the notes live in one SQLite journal with a stable schema.

## Project-Local Convention

By default the package creates and uses:

- `_docs/_journalDB/app_journal.sqlite3`
- `_docs/_AppJOURNAL/`

Inside `_docs/_AppJOURNAL/` it stores:

- `journal_config.json`
- `exports/`

## Layout

- `tools/`
  - stable user-facing tools
- `lib/`
  - shared SQLite store and journal operations
- `ui/`
  - Tkinter manager UI
- `jobs/`
  - machine-run example jobs
- `templates/`
  - reusable examples and starter shapes
- `drop-bin/`
  - rough scripts awaiting conversion
- `common.py`
  - shared runtime and CLI contract
- `mcp_server.py`
  - MCP stdio entrypoint
- `launch_ui.py`
  - convenience launcher for the Tkinter manager
- `smoke_test.py`
  - portable verification
- `tool_manifest.json`
  - machine-readable manifest

## Current Tools

- `journal_init`
- `journal_manifest`
- `journal_write`
- `journal_query`
- `journal_export`

## UI Use

Run:

```powershell
python _app-journal\launch_ui.py --project-root C:\path\to\project
```

## MCP First

Run:

```powershell
python _app-journal\mcp_server.py
```

## Standard CLI Contract

```powershell
python _app-journal\tools\<tool>.py metadata
python _app-journal\tools\<tool>.py run --input-json "{...}"
python _app-journal\tools\<tool>.py run --input-file _app-journal\jobs\examples\<job>.json
```

## Design Rule

The UI and MCP tools must call the same SQLite store code so the journal behaves the same way for humans and agents.

## Self-Description

The vendored package describes itself in two places:

- on disk via `tool_manifest.json`
- inside each initialized journal via embedded manifest rows in `journal_meta`
- with schema tracking via `journal_migrations` and SQLite `user_version`

That gives agents two clean pickup paths:

- inspect the vendored folder to understand the package
- inspect the `.sqlite3` journal to understand what the database is and how it is meant to be used

That means the DB now carries:

- package manifest snapshot
- DB manifest
- schema version
- SQLite `user_version`
- migration history
