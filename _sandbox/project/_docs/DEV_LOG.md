# DEV_LOG — AgenticTOOLBOX

Append-only execution ledger.

---

## 2026-03-16T19:20 — INIT-001: Full V1 Build

### Summary
Built the complete V1 sandboxed chatbot agent shell from blueprint in a single session. All 6 phases implemented.

### Files Created

**Package structure (13 `__init__.py` files)**
- `src/__init__.py`, `src/core/__init__.py`, `src/ui/__init__.py`
- `src/core/{utils,runtime,config,registry,sessions,ollama,sandbox,agent}/__init__.py`
- `src/ui/{panes,widgets}/__init__.py`

**Core utilities**
- `src/core/utils/ids.py` — stable ID generation with prefix + timestamp + uuid4
- `src/core/utils/clock.py` — UTC timestamps, stopwatch
- `src/core/utils/text_metrics.py` — heuristic token estimation

**Runtime infrastructure**
- `src/core/runtime/runtime_logger.py` — structured logging (file + console)
- `src/core/runtime/event_bus.py` — synchronous pub/sub
- `src/core/runtime/activity_stream.py` — UI-facing activity feed
- `src/core/runtime/resource_monitor.py` — CPU/RAM/GPU polling via psutil + nvidia-smi

**Configuration**
- `src/core/config/app_config.py` — central config with JSON persistence, num_ctx=8192

**Engine**
- `src/core/engine.py` — runtime coordinator with sandbox, tool routing, chat streaming

**Ollama integration**
- `src/core/ollama/ollama_client.py` — streaming chat via urllib (stdlib only)
- `src/core/ollama/model_scanner.py` — model discovery via /api/tags
- `src/core/ollama/tokenizer_adapter.py` — pluggable token estimator

**Session persistence**
- `src/core/sessions/sqlite_schema.py` — sessions, messages, tool_runs tables
- `src/core/sessions/session_store.py` — full CRUD + branch + tool run storage

**Sandbox security**
- `src/core/sandbox/path_guard.py` — path containment enforcement
- `src/core/sandbox/cli_runner.py` — subprocess execution with boundary checks
- `src/core/sandbox/sandbox_manager.py` — sandbox root + standard folder structure
- `src/core/sandbox/tool_catalog.py` — tool registry with cli_in_sandbox builtin
- `src/core/sandbox/tool_scaffold.py` — scaffold new sandbox-local tools

**Agent loop**
- `src/core/agent/prompt_builder.py` — system prompt with tool definitions
- `src/core/agent/tool_router.py` — parse ```tool_call blocks, validate, dispatch
- `src/core/agent/response_loop.py` — multi-round streaming + tool execution
- `src/core/agent/transcript_formatter.py` — format tool results for model

**State registry**
- `src/core/registry/records.py` — NodeRecord, FacetRecord, RelationRecord
- `src/core/registry/state_registry.py` — in-memory registry with graph semantics
- `src/core/registry/session_registry.py` — session/message node registration

**UI — cyberpunk theme**
- `src/ui/theme.py` — dark neon color palette, fonts
- `src/ui/ui_state.py` — transient UI state
- `src/ui/gui_main.py` — main window compositor
- `src/ui/panes/chat_pane.py` — scrollable chat transcript
- `src/ui/panes/activity_log_pane.py` — runtime terminal viewer
- `src/ui/panes/cli_pane.py` — direct sandbox CLI panel
- `src/ui/panes/input_pane.py` — multi-line input with token estimate
- `src/ui/panes/control_pane.py` — right column (model picker, resources, input, buttons)
- `src/ui/widgets/chat_message_card.py` — styled message cards with role colors
- `src/ui/widgets/metadata_tag_row.py` — inline metadata tags
- `src/ui/widgets/model_picker.py` — dropdown with refresh
- `src/ui/widgets/status_light.py` — colored dot indicator
- `src/ui/widgets/faux_button_panel.py` — reserved action buttons

**Root files**
- `src/app.py` — composition root with full wiring
- `run.bat` — launcher script
- `requirements.txt` — psutil dependency
- `_docs/ARCHITECTURE.md` — this architecture doc
- `_docs/DEV_LOG.md` — this log
- `_docs/TODO.md` — next steps

### Design Notes
- All model calls constrained to num_ctx=8192 to protect 8GB VRAM
- Sandbox path guard blocks traversal, symlinks, absolute escapes
- Cyberpunk dark neon theme (cyan/magenta/green accents on dark base)
- CLI panel added for direct sandbox command access and testing
- Models auto-refresh on startup
- Resource monitor polls every 5 seconds

### Testing
- All core imports verified
- Model scanner confirmed 21 Ollama models
- Session store CRUD + branching tested
- Path guard escape blocking confirmed
- CLI runner sandbox execution confirmed
- GUI instantiation test passed
- Full app launched and verified live

---

## 2026-03-16T19:50 — SEC-001: Command Security Policy + OS Knowledge

### Summary
Addressed critical security gap: CLI runner was only path-guarded, not command-guarded. Added allowlist-based command policy and OS knowledge teaching module for the agent.

### Security Problem
The original CLIRunner only validated that working directories stayed inside the sandbox. But the agent could execute arbitrary shell commands (powershell, curl, net user, reg, etc.) that bypass path containment entirely. This is not a sandbox — it's an open door with a sign.

### Files Created
- `src/core/sandbox/command_policy.py` — Allowlist-based command validation with 36 approved commands, explicit blocklist (powershell, curl, pip, net, reg, ssh, etc.), and escape-pattern detection (command chaining via ;, &, |, backticks, subshells, absolute paths)
- `src/core/agent/os_knowledge.py` — Teaches the agent OS fundamentals: what filesystems are, what directories/files are, how terminals work, path syntax, and common task patterns

### Files Modified
- `src/core/sandbox/cli_runner.py` — Now validates all commands through CommandPolicy before execution
- `src/core/agent/prompt_builder.py` — Injects OS knowledge + allowed command reference into system prompt
- `src/core/agent/response_loop.py` — Passes command_policy to prompt builder
- `src/core/engine.py` — Creates and wires CommandPolicy on sandbox initialization

### Testing
- 19/19 policy validation tests passed (allowed + blocked commands)
- CLI runner enforcement confirmed: powershell, curl, pip all blocked
- Command chaining escape patterns (&, |, ;, backticks, subshells) all caught
- Absolute path outside sandbox blocked

### Design Notes
- 36 allowlisted commands organized by category (navigation, file_read, file_write, execution, text, info, version_control)
- Each command has usage, description, and notes — this doubles as agent teaching material
- Docker/WASM noted as future containment upgrade path but not needed for v1
- OS knowledge module written specifically for small models (2B-4B) that may lack implicit OS understanding

---

## 2026-03-16T21:00 — FEAT-001: Session Management, Registry, Security, UX

### Summary
Burned through the entire high-priority TODO list in one session. Added full session management UI, wired the state registry, sandbox folder picker, destructive command confirmation, command audit trail, psutil venv, auto-save, and fixed input clearing.

### Files Created
- `src/ui/widgets/session_panel.py` — Session list with NEW/Rename/Branch/Delete controls, listbox with selection, cyberpunk-styled
- `src/core/sandbox/audit_log.py` — Append-only JSON-lines audit trail for all command attempts (executed, blocked, cancelled, timeout, error)
- `venv/` — Python 3.10 venv with psutil 7.2.2 installed

### Files Modified
- `src/app.py` — Full rewrite of composition root:
  - Session lifecycle: auto-create first session, load/switch/save/delete/branch
  - State registry wired: sessions and messages registered as nodes
  - Destructive command confirmation via thread-safe messagebox dialog
  - Autosave with 3-second debounce after turn completion
  - Save-on-close persistence
  - Sandbox picker via filedialog (re-initializes session store for new sandbox)
  - Messages persisted to session store on send and receive
- `src/ui/panes/control_pane.py` — Added SessionPanel widget, sandbox picker button, expanded constructor with session/sandbox callbacks
- `src/ui/gui_main.py` — Added session/sandbox callback parameters, passed through to ControlPane
- `src/ui/panes/input_pane.py` — Fixed input clearing: now clears BEFORE callback (prevents stuck text if callback throws)
- `src/core/engine.py` — Added on_confirm_destructive callback pass-through
- `src/core/sandbox/sandbox_manager.py` — Creates AuditLog, passes to CLIRunner with confirm callback
- `src/core/sandbox/cli_runner.py` — Added destructive confirmation hook, audit log recording for all outcomes
- `src/core/sandbox/command_policy.py` — Added DESTRUCTIVE_COMMANDS set and is_destructive() method
- `run.bat` — Updated to find venv/ directory (was looking for .venv/)
- `_docs/TODO.md` — Marked all completed items

### Design Notes
- Session panel uses Listbox with ► prefix for active session
- Audit log is JSON-lines format at `_sandbox/_logs/audit.jsonl` — easy to grep, parse, review
- Destructive confirmation uses threading.Event for cross-thread sync (CLI runs in background thread, dialog must show on main thread)
- Autosave uses root.after() debounce — resets 3-second timer on each turn completion
- State registry nodes are created for sessions and messages, with parent-child relationships

### Testing
- All imports verified clean
- Audit log write/read confirmed (2 entries: executed + cancelled)
- Destructive detection: del=True, dir=False, rm=True
- App launches successfully with session panel visible
