# Tools

Stable manifold tools live here.

## Current Tools

- `manifold_ingest.py`
- `manifold_query.py`
- `manifold_extract.py`

## Rules

- include a clear header block
- export `FILE_METADATA`
- export `run(arguments)`
- end with `standard_main(FILE_METADATA, run)`
- return the standard JSON envelope defined in `common.py`
