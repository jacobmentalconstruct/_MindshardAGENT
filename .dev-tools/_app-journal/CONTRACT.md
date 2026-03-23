# Contract

This subproject exists to keep project notes durable, queryable, and shared between humans and agents.

## Builder Pledge

- Keep the folder isolated and portable.
- Keep the MCP path primary for agent use.
- Keep the SQLite schema explicit and stable.
- Keep UI and tool behavior unified through one shared store layer.
- Prefer additive schema changes over destructive churn.
- Keep exports readable and mechanical.

## Standard Tool Contract

Every tool in `tools/` should:

- include a clear header block
- export `FILE_METADATA`
- export `run(arguments)`
- support `metadata`
- support `run --input-json`
- support `run --input-file`
- return a stable JSON envelope

## Journal Contract

The package should preserve these concepts explicitly:

- project root
- database path
- entry uid
- created time
- updated time
- kind
- source
- status
- title
- body
- tags
- metadata

It should also preserve enough manifest data for an agent to orient itself from the database alone:

- embedded package manifest
- embedded DB manifest
- project root
- initialized time
- schema version
- migration history

## UI Contract

- The Tkinter manager must use the same store code as the MCP tools.
- The UI must remain optional; the package must still be usable headlessly.

## Project-Local Convention

Default locations:

- `_docs/_journalDB/app_journal.sqlite3`
- `_docs/_AppJOURNAL/journal_config.json`
- `_docs/_AppJOURNAL/exports/`
