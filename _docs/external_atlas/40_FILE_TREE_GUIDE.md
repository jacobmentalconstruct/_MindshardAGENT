# 40 File Tree Guide

## Purpose

This is a curated tree, not a full dump.
It highlights the files most useful for understanding the system.

## Top-Level Tree

```text
README.md
app_config.json

src/
  app.py
  app_bootstrap.py
  app_lifecycle.py
  app_state.py
  app_streaming.py
  app_prompt.py
  app_prompt_lab.py
  app_session.py
  app_commands.py
  app_docker.py
  app_ui_bridge.py

  core/
    engine.py
    agent/
    sandbox/
    project/
    prompt_lab/
    sessions/
    runtime/
    config/
    vcs/
    vault/

  ui/
    gui_main.py
    ui_facade.py
    ui_state.py
    panes/
    widgets/
    dialogs/

  prompt_lab/
    main.py
    cli.py
    mcp_server.py
    workbench.py

  mcp/
    server.py
    ui_bridge_server.py

prompt_lab/
  README.md
  STORAGE_DOCTRINE.md

_docs/
  builder_constraint_contract.md
  ARCHITECTURE.md
  ENGINEERING_NOTES.md
  external_atlas/
  _journalDB/

.mindshard/
.prompt-versioning/
tests/
```

## Read-First Files By Topic

### If you want the main app entry flow
- `src/app.py`
- `src/app_bootstrap.py`
- `src/app_lifecycle.py`

### If you want runtime behavior
- `src/core/engine.py`
- `src/app_streaming.py`
- `src/core/agent/response_loop.py`
- `src/core/agent/loop_manager.py`

### If you want prompt-building logic
- `src/core/agent/prompt_builder.py`
- `src/core/agent/prompt_sources.py`
- `src/core/agent/prompt_tuning_store.py`
- `src/ui/panes/prompt_workbench_tabs.py`

### If you want project attach/detach behavior
- `src/core/project/project_command_handler.py`
- `src/core/project/project_lifecycle.py`
- `src/core/project/project_meta.py`

### If you want sandbox/tool behavior
- `src/core/sandbox/cli_runner.py`
- `src/core/sandbox/tool_discovery.py`
- `src/core/sandbox/tool_catalog.py`
- `src/core/sandbox/command_policy.py`

### If you want Prompt Lab
- `src/core/prompt_lab/contracts.py`
- `src/core/prompt_lab/services.py`
- `src/core/prompt_lab/storage.py`
- `src/core/prompt_lab/runtime_loader.py`
- `src/prompt_lab/main.py`
- `src/prompt_lab/workbench.py`

### If you want the UI composition
- `src/ui/gui_main.py`
- `src/ui/ui_facade.py`
- `src/ui/panes/control_pane.py`
- `src/ui/panes/prompt_workbench.py`
- `src/ui/panes/prompt_workbench_tabs.py`

## Important Folder Meaning

### `src/`
Application code.

### `src/core/`
Runtime and domain logic.

### `src/ui/`
Tkinter interface and visual composition.

### `src/prompt_lab/`
Prompt Lab entrypoints and dedicated workbench shell.

### `prompt_lab/`
Prompt Lab subsystem docs/assets root.

### `.mindshard/`
Project-local sidecar state.

### `_docs/_journalDB/`
SQLite builder/project memory journal.

### `.prompt-versioning/`
Prompt tuning/evaluation persistence related to prompt versioning.

## Practical Reading Order For Fresh Agents

1. `README.md`
2. `src/app.py`
3. `src/app_bootstrap.py`
4. `src/core/engine.py`
5. this atlas:
   - `10_ARCHITECTURE_MAP.md`
   - `20_RUNTIME_LIFECYCLE.md`
   - `60_INTEGRATION_SEAMS.md`
6. whichever subsystem files match the task
