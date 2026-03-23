# Tools

Stable prompt-lab tools live here.

## Current Tools

- `ollama_prompt_lab.py`

## Rules For Every Tool File

- include a clear header block at the top
- export `FILE_METADATA`
- export `run(arguments)`
- end with `standard_main(FILE_METADATA, run)`
- return the standard JSON envelope defined in `common.py`
