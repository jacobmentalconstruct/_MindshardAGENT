# Vendoring

This folder is designed to be copied or zipped as a standalone tool project.

## What To Vendor

Vendor the whole `_app-journal` folder, not individual scripts.

Required contents:

- `tools/`
- `lib/`
- `ui/`
- `common.py`
- `mcp_server.py`
- `launch_ui.py`
- `tool_manifest.json`
- `README.md`
- `CONTRACT.md`
- `smoke_test.py`

Optional but recommended:

- `jobs/`
- `templates/`
- `ROADMAP.md`
- `drop-bin/`

## Project Behavior

When pointed at a project root, the package creates:

- `_docs/_journalDB/app_journal.sqlite3`
- `_docs/_AppJOURNAL/`

## Verification After Vendoring

Run:

```powershell
python _app-journal\smoke_test.py
```
