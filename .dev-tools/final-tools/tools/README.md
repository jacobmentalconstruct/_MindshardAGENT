# Tools Folder

This folder contains the actual user-facing tools.

## Rules For Every Tool File

- Include a clear header block at the top.
- Export `FILE_METADATA`.
- Export `run(arguments)`.
- End with `standard_main(FILE_METADATA, run)`.
- Return the standard JSON envelope defined in `common.py`.

## Current Tools

- `workspace_audit.py`
- `data_shape_inspector.py`
- `structured_patcher.py`
- `python_risk_scan.py`
- `tk_ui_map.py`
- `tk_ui_thread_audit.py`
- `tk_ui_event_map.py`
- `tk_ui_layout_audit.py`
- `tk_ui_test_scaffold.py`
