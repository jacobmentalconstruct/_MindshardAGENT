# Project Tidiness

You are responsible for keeping the sandbox tidy. Messy workspaces make it
harder to orient yourself and harder for the user to review your work.
Apply these rules whenever you create or move files.

## Folder Structure

Always organise files into purposeful subdirectories — never dump files flat
in the sandbox root unless they are top-level project artefacts (README, config,
entry-point scripts).

Preferred layout:
```
<sandbox_root>/
  src/           — source code (subdirs by domain/module)
  tests/         — test files mirroring src/ structure
  docs/          — user-facing documentation
  data/          — input data or fixtures
  scripts/       — one-off helper scripts
  output/        — generated artefacts (logs, reports, exports)
  .mindshard/    — agent state (sessions, runs, logs) — do not edit directly
```

Adapt this to the project's existing conventions. If the project already has
a layout, follow it rather than imposing a new one.

## Naming Conventions

- Use `snake_case` for Python modules and files: `my_module.py`, `test_parser.py`
- Use `kebab-case` for shell scripts and config files: `run-tests.sh`, `docker-compose.yml`
- Prefix temporary or draft files with `_tmp_` or `_draft_`: `_tmp_analysis.txt`
- Prefix generated outputs with the generating tool or date: `2026-03-23_report.md`
- Never use spaces in filenames

## Before Creating a File

1. Check whether a file with the same purpose already exists (`list_files` or `read_file`)
2. If a similar file exists, extend it rather than creating a duplicate
3. Choose the correct subdirectory before writing — do not create the file and move it later
4. If a new directory is needed, create it explicitly before writing into it

## Cleaning Up After Yourself

- Delete temporary files and test outputs when the task is complete
- If you created scratch files under a temp path (e.g. `.mindshard/runs/`), leave them
  — these are managed automatically
- If you generated an intermediate file to pass data between steps, delete it when done
  unless the user asked to keep it

## When in Doubt

If you are unsure where a file belongs, ask the user before creating it. A short
clarifying question is cheaper than reorganising a messy directory tree later.
