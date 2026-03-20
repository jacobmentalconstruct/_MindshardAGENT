# DEV_LOG — MindshardAGENT

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

---

## 2026-03-17 — FEAT-002: Medium Priority Sweep + RAG + Rename

### Summary
Burned through entire medium priority TODO list. Added session-scoped RAG with
Ollama all-minilm embeddings, tool discovery, model chain pipelines, adaptive
tokenizer, streaming auto-resize. Renamed project from AgenticTOOLBOX to
MindshardAGENT across all source files.

### Files Created
- `src/core/ollama/embedding_client.py` — Ollama /api/embeddings client (embed_text, embed_batch, check_embedding_model)
- `src/core/sessions/knowledge_store.py` — Session-scoped RAG knowledge base (SQLite + cosine similarity)
- `src/core/sandbox/tool_discovery.py` — Scans _tools/ for Python scripts with docstring metadata
- `src/core/agent/model_chain.py` — Sequential model pipeline (ChainStep → ChainArtifact)
- `tests/test_tool_roundtrip.py` — Headless tool-use test suite (39 tests initially)

### Files Modified
- `src/core/sessions/sqlite_schema.py` — Added knowledge table for RAG embeddings
- `src/core/config/app_config.py` — RAG config fields (embedding_model, rag_enabled, top_k, min_score, chunk_size)
- `src/core/agent/prompt_builder.py` — RAG context injection, MindshardAGENT rename
- `src/core/agent/response_loop.py` — RAG retrieval before prompt, RAG storage after completion
- `src/core/engine.py` — RAG wiring, tool discovery, adaptive tokenizer learning
- `src/core/ollama/tokenizer_adapter.py` — Rewritten with EMA-based adaptive learning
- `src/ui/widgets/chat_message_card.py` — Streaming content update with auto-resize
- `src/app.py` — KnowledgeStore wiring, embedding check, tokenizer sync, streaming resize
- 10 files renamed AgenticTOOLBOX → MindshardAGENT

### Testing
- 39/39 tool round-trip tests passed (including live qwen3.5:2b)

---

## 2026-03-17 — FIX-001: write_file/read_file Tools + Prompt Overhaul

### Summary
First real GUI tool-use test revealed that models (qwen3.5:4b) cannot create
multi-line files through Windows cmd.exe. Five consecutive tool rounds all
failed — echo with single quotes, python -c with triple quotes, cat (not on
Windows), python3 (blocked). Root cause was twofold: no file creation tool
existed, and the system prompt was actively teaching the wrong approach.

### The Bug (Self-Contradicting Prompt)
`os_knowledge.py` contained shell-based file creation examples:
```
echo Hello, this is my file content > newfile.txt
echo print("Hello from Python!") > hello.py
```
While `prompt_builder.py` later said "use write_file to create files." The
model followed the concrete demonstrated pattern (echo), not the abstract
directive (use write_file). The OS knowledge section was undermining the tool
instructions.

### Files Created
- `src/core/sandbox/file_writer.py` — Direct file creation/reading within sandbox. PathGuard containment, extension blocklist (.exe/.bat/.cmd/.ps1), size limits (512KB write, 1MB read), audit logging.

### Files Modified
- `src/core/sandbox/tool_catalog.py` — Registered WRITE_FILE and READ_FILE as built-in tools
- `src/core/agent/tool_router.py` — Added dispatch handlers for write_file and read_file
- `src/core/agent/prompt_builder.py` — Complete rewrite of tool section. Added decision table, NEVER/ALWAYS rules, few-shot examples matching real use cases. Replaced polite "PREFERRED" with aggressive routing.
- `src/core/agent/os_knowledge.py` — Removed all echo/type examples. Every file operation now references write_file/read_file tool by name.
- `src/core/agent/transcript_formatter.py` — Custom formatting for file tool results
- `src/core/engine.py` — FileWriter created in set_sandbox(), passed to ToolRouter
- `src/core/sandbox/sandbox_manager.py` — Exposed audit property

### Prompt Engineering Changes
- Added tool selection decision table (Task → Correct Tool → Wrong approach)
- Added capitalized NEVER/ALWAYS rules for tool routing
- Added anti-patterns with markdown strikethrough (~~echo ... > file~~)
- Changed few-shot example to a tkinter app (matches common first task)
- Removed all echo-based file creation from OS knowledge module
- Every "create file" reference now points to write_file tool

### Testing
- 70/70 tests passed (31 new tests for file tools, router dispatch, prompt verification)

### Design Notes
- The write_file tool bypasses cmd.exe entirely — JSON `\n` → real newlines → direct disk write
- File content encoding: model produces JSON with `\n` escapes, Python json.loads() decodes, file_writer writes with newline="\n"
- Extension blocklist is defense-in-depth — prevents model from creating executable files even inside sandbox
- Auto-mkdir: parent directories created automatically within sandbox boundary

### Key Lesson
When teaching a model new tools, EVERY instructional reference must be updated.
A single leftover `echo content > file` example in any section of the prompt
will override explicit tool routing instructions. The demonstrated pattern
always wins over the described pattern for small models.

---

## 2026-03-17 — FEAT-003: Docker Containerized Sandbox

### Summary
Full Docker sandbox integration — v2 containment upgrade. The agent's CLI
commands now execute inside a Linux Docker container instead of Windows
subprocess. The container IS the security boundary: `--network none`, memory
and CPU limits, disposable. PathGuard and CommandPolicy become redundant in
Docker mode — the container handles containment.

### Architecture
```
Host (Windows)                    Container (Linux)
├─ Tkinter GUI                    ├─ python:3.10-slim
├─ Ollama (GPU)                   ├─ bash, tree, git
├─ Engine                         ├─ /sandbox (volume mount)
│   ├─ FileWriter (host-side)     └─ tail -f /dev/null (keepalive)
│   └─ DockerRunner ──docker exec──►
└─ DockerManager (user-only)
```

- **Host runs**: GUI, Ollama (GPU), Engine, FileWriter
- **Container runs**: CLI commands only (via `docker exec`)
- **Sandbox dir**: mounted as volume — files synced bidirectionally
- **FileWriter**: always writes on host side (volume mount keeps container in sync)
- **Agent**: never sees or controls Docker — just gets Linux bash instead of Windows cmd

### Files Created
- `docker/Dockerfile` — python:3.10-slim with tree, git. `tail -f /dev/null` keepalive.
- `src/core/sandbox/docker_manager.py` — Container lifecycle: build, create, start, stop, destroy, status, exec. USER ONLY — never agent-accessible.
- `src/core/sandbox/docker_runner.py` — Drop-in CLIRunner replacement. Same `.run()` interface, same result dict shape. Uses `docker exec` instead of `subprocess.run()`.
- `src/ui/widgets/docker_panel.py` — Docker control panel: status light, enable/disable toggle, Build/Start/Stop/Nuke buttons, info line.
- `_docs/AGENT_CONTRACT.md` — Behavioral contract for the local agent.
- `_docs/ENGINEERING_NOTES.md` — Hard-won lessons and technical reference.

### Files Modified
- `src/core/config/app_config.py` — Added docker_enabled, docker_memory_limit, docker_cpu_limit
- `src/core/engine.py` — Dual-mode set_sandbox(): DockerRunner when Docker available, CLIRunner fallback. Passes docker_mode to ResponseLoop.
- `src/core/agent/response_loop.py` — Added docker_mode parameter, passes through to build_system_prompt()
- `src/core/agent/prompt_builder.py` — Added docker_mode parameter. Conditional env block (Linux vs Windows), conditional list command (ls -la vs dir), Docker OS knowledge injection.
- `src/core/agent/os_knowledge.py` — Added DOCKER_FUNDAMENTALS section, updated get_os_knowledge() and get_command_teaching() with docker_mode parameter.
- `src/ui/panes/control_pane.py` — Added DockerPanel between Resources and Prompt Preview
- `src/ui/gui_main.py` — Passed Docker callbacks through to ControlPane
- `src/app.py` — Docker callback implementations: toggle (re-init sandbox), build (background thread), start (background thread + re-init), stop, destroy (with confirmation dialog). Docker status polling every 10s. Initial status check on startup.

### Container Configuration
- `--network none` — no network access
- `--memory 512m` — configurable via app_config
- `--cpus 1.0` — configurable via app_config
- Volume mount: `sandbox_root:/sandbox`
- Minimal blocklist inside container: reboot, shutdown, halt, init
- Destructive confirmation still active: rm, rmdir, del

### Testing
- 70/70 unit tests pass (docker_mode defaults to False, all existing callers unaffected)
- Docker integration test: 13/13 passed
  - Docker available, image exists, container create+start
  - Host→container file sync (wrote on host, cat inside container)
  - Container→host file sync (echoed inside container, read on host)
  - Python3 execution inside container
  - DockerRunner.run() returns correct dict shape
  - Blocked commands (reboot) rejected
  - Container destroy + status verification

### UI Panel
- Status light: green=running, amber=stopped, dim=no container, red=Docker N/A
- Enable checkbox: toggles docker_enabled in config, re-initializes sandbox
- Build button: builds image from docker/Dockerfile (background thread)
- Start button: creates and starts container with volume mount
- Stop button: stops container, falls back to local subprocess
- Nuke button: destroys container with confirmation dialog
- Info line: contextual status message
- Polls every 10 seconds to stay current

---

## 2026-03-17 — FEAT-004: Project Sync-Back + Action Journal

### Summary
Two features enabling the agent self-improvement loop:

1. **Project sync-back** — diffs sandbox/project/ against real source tree,
   shows a summary, and applies changes back with user confirmation. Logged
   to `_sandbox/_logs/sync_log.jsonl`.

2. **Action journal** — structured event log recording every significant
   operation (project load, sync, tool use, session switch, docker events,
   agent turns). Injected into the agent's system prompt so it can orient
   itself between turns or after context loss.

### Self-Improvement Loop
```
User clicks "Load Self"
  → project_loader copies source → sandbox/project/
  → journal records: project_load

Agent reads/modifies files in sandbox/project/
  → journal records: file_write, tool_exec per operation

User clicks "Sync Back"
  → project_syncer diffs sandbox vs real source
  → user confirms via dialog (diff summary shown)
  → changes applied to real source tree
  → journal records: project_sync
  → sync_log.jsonl records file-level details
```

### Files Created
- `src/core/sandbox/project_syncer.py` — Diff and apply sandbox→source changes.
  Uses `filecmp.cmp()` for content comparison. Never syncs venv/__pycache__/.git.
  Deletions require explicit `apply_deletes=True` (default: off for safety).
  Writes sync manifest to `_sandbox/_logs/sync_log.jsonl`.
- `src/core/runtime/action_journal.py` — Append-only JSON-lines event log.
  Categories: project_load, project_sync, file_write, file_read, tool_exec,
  session_start, session_switch, config_change, docker_event, agent_turn.
  Queryable by type, recency. `summary_since(n)` returns human-readable text
  suitable for prompt injection.

### Files Modified
- `src/core/engine.py` — Creates ActionJournal on sandbox init. Records
  CONFIG_CHANGE on set_sandbox, AGENT_TURN on response completion.
  Passes journal to ResponseLoop.
- `src/core/agent/response_loop.py` — Accepts journal parameter. Calls
  `journal.summary_since(10)` before each turn and passes to prompt builder.
- `src/core/agent/prompt_builder.py` — Added `journal_context` parameter.
  Injected as "Recent Workspace Activity" section in system prompt.
- `src/app.py` — Rewired action buttons: "Load Self" (loads project + journals),
  "Sync Back" (diffs + confirms + applies + journals), "Clear" (clears chat).
  Added journal recording for session new/switch, docker toggle.
  Fixed streaming display: added scrollregion update after card resize.
- `src/ui/widgets/faux_button_panel.py` — Updated button labels:
  Load Self, Sync Back, Tools, Plan, Branch, Clear.

### Streaming Fix
The chat pane wasn't updating during streaming because `_update_stream` only
called `canvas.update_idletasks()` without refreshing the scrollregion. After
a card's Text widget resized, the canvas still thought the inner frame was the
old size. Fix: explicitly call `canvas.configure(scrollregion=canvas.bbox("all"))`
after each streaming update.

### Testing
- 70/70 unit tests pass
- All new imports verified clean
