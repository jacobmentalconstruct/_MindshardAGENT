# AgenticTOOLBOX Architecture

## Overview

A lean Tkinter desktop chatbot shell for a local Ollama-backed agent with sandboxed CLI tool execution. Designed as a single-user local agent workbench.

## Runtime Model

```
app.py (composition root)
  ├── Engine (runtime coordinator)
  │     ├── SandboxManager → PathGuard + CLIRunner
  │     ├── ToolCatalog (builtin + sandbox-local tools)
  │     ├── ToolRouter (parse + dispatch tool calls)
  │     ├── ResponseLoop (streaming + tool round-trips)
  │     └── OllamaClient (chat streaming)
  ├── StateRegistry (lean in-memory graph-semantic registry)
  ├── SessionStore (SQLite persistence)
  ├── ActivityStream (runtime event feed)
  ├── EventBus (internal pub/sub)
  └── MainWindow (Tkinter GUI)
        ├── ChatPane (scrollable transcript)
        ├── ActivityLogPane (runtime terminal)
        ├── CLIPane (direct sandbox CLI)
        └── ControlPane (model picker, resources, input, buttons)
```

## Key Design Decisions

1. **Stdlib-first**: No heavy dependencies. Ollama client uses urllib, sessions use sqlite3, UI uses tkinter. Only psutil is optional.

2. **Sandbox boundary**: All tool/CLI execution is path-guarded. The PathGuard validates every path resolves within sandbox root.

3. **Registry-minded**: In-memory StateRegistry with typed NodeRecord, FacetRecord, RelationRecord. Designed for mechanical promotion to richer graph backend.

4. **Streaming**: Model responses stream token-by-token via background thread → root.after() → UI update. Input is disabled during streaming.

5. **Agent loop**: ResponseLoop handles multi-round tool use. Model can emit ```tool_call blocks, which are extracted, validated, executed, and fed back.

6. **Context protection**: num_ctx capped at 8192 to protect VRAM on 8GB GPU.

## File Layout

- `src/app.py` — composition root, lifecycle
- `src/core/engine.py` — runtime coordinator
- `src/core/config/` — central config (JSON-persisted)
- `src/core/registry/` — lean state registry
- `src/core/sessions/` — SQLite session persistence
- `src/core/ollama/` — model scanning, chat client, tokenizer adapter
- `src/core/runtime/` — logging, event bus, activity stream, resource monitor
- `src/core/sandbox/` — sandbox manager, path guard, CLI runner, tool catalog
- `src/core/agent/` — prompt builder, response loop, tool router
- `src/core/utils/` — IDs, clock, text metrics
- `src/ui/` — Tkinter GUI (theme, panes, widgets)
