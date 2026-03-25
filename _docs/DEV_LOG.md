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

---

## 2026-03-21 — TUNE-001: Architecture Inspection Guidance Tightened

### Summary
While the UI was being tested, I used the diagnostic lab for a quick agent
tuning pass against `qwen3.5:4b`.

Two concrete improvements landed:

1. architecture-understanding guidance now pushes the model toward
   `list_files -> read docs -> read entry points` instead of reaching for
   `run_python_file` too early
2. the probe scorer no longer falsely penalizes answers that correctly warn
   against fake prefixes like `project/src/app.py`

### Files Modified
- `_docs/agent_prompt/20_intent_interpretation.md`
  - architecture requests now explicitly prefer structure/doc/entry-point reads
  - narrow questions now tell the model to stay within the requested scope
- `_docs/agent_prompt/40_response_style.md`
  - reinforces tight scope matching for small factual/tooling answers
- `_docs/agent_prompt/50_tool_usage_preferences.md`
  - clarifies that `run_python_file` is for verification, not early architecture exploration
- `src/core/agent/probe_scorer.py`
  - made invented-prefix detection context-aware so negative examples are not treated as failures

### Measured Effect
- architecture-inspection direct-model probe improved from:
  - `overall_score 0.793 -> 0.813`
  - still `accuracy_score 1.0`
  - slightly better efficiency via lower token footprint
- workspace-rules probe now scores correctly after the false-positive fix:
  - `accuracy_score 1.0`
  - `overall_score 0.811` on the latest rerun

### Notes
- This was a conservative tuning pass: no planner logic changed, only prompt-doc guidance and benchmark scoring accuracy
- The remaining efficiency work is mostly about reducing unnecessary explanation volume while preserving correctness

### Testing
- direct diagnostic-lab reruns of the two core direct-model understanding probes using `qwen3.5:4b`
- `py -3.10 -m compileall src/core/agent/probe_scorer.py`

---

## 2026-03-21 — FEAT-013: Modular Loop Manager And Response Modes

### Summary
The app's execution lifecycle had become strong but too centralized:
`Engine.submit_prompt()` effectively routed into one main loop with planner
behavior layered inside it, while other behaviors like thought chains lived
beside the main path instead of inside a loop system.

This pass extracts a first-class loop-management seam so the app can evolve
multiple response modes without letting `Engine` or `ResponseLoop` greedily own
all orchestration behavior.

### Files Added
- `src/core/agent/loop_types.py`
- `src/core/agent/loop_selector.py`
- `src/core/agent/loop_manager.py`
- `src/core/agent/direct_chat_loop.py`
- `src/core/agent/planner_only_loop.py`
- `src/core/agent/thought_chain_loop.py`

### Files Modified
- `src/core/agent/response_loop.py`
  - now exposes `loop_id = tool_agent`
  - adds a generic `run(request)` adapter so it can be managed like any other loop
  - returns `loop_mode` in result metadata
- `src/core/engine.py`
  - now owns a `LoopManager`
  - rebuilds loop registry from current runtime state
  - dispatches user turns through the loop manager instead of hardcoding one path
  - records selected loop ids in runtime activity
- `_docs/TODO.md`
  - marks the loop-manager extraction complete
  - adds follow-up items for loop diagnostics, loop controls, and graph-based thought chains

### Default Loop Modes
- `direct_chat`
  - lightweight conversational turns
- `tool_agent`
  - current main agent loop with planner + tools
- `planner_only`
  - short structured planning responses
- `thought_chain`
  - task-decomposition planning loop

### Architectural Notes
- Loop selection now has its own seam in `loop_selector.py`
- Loop dispatch now has its own registry in `loop_manager.py`
- `Engine` is reduced to orchestration and runtime wiring
- The existing tool-agent loop remains intact as the strongest default mode,
  but it no longer owns the whole lifecycle concept
- Graph-based thought chains are intentionally deferred as the next evolution
  of planning loops, not mixed into this extraction pass

### Testing
- `py -3.10 -m compileall src`

---

## 2026-03-21 — FIX-003: Startup / Shutdown UI Thread Safety Pass

### Summary
Live testing exposed two stability issues:

1. the app could appear hung during startup just after session restore
2. closing the window could crash if late timers or background callbacks touched Tk after teardown

Root cause was a thread-safety mismatch: background work was still able to
drive UI callbacks directly in a few places, and some repeating timers were
not cancelled on shutdown.

### Files Modified
- `src/ui/gui_main.py`
  - marshals activity-stream UI updates onto the Tk main thread
  - ignores late activity events after close
  - guards against double-close races
- `src/app.py`
  - routes more worker-thread completions through `_safe_ui(...)`
  - adds finer startup trace logging for deferred bootstrap stages
  - cancels autosave and stream-flush timers during shutdown
  - hardens close flow against repeated teardown calls

### Behavior Changes
- Startup should no longer freeze because a background event hit Tk directly
- Close should be more reliable even with active timers / worker callbacks
- Startup logs now make it clearer whether the app is:
  - refreshing prompt inspector
  - loading session list
  - restoring a prior session
  - creating a fresh session

### Testing
- `py -3.10 -m compileall src/app.py src/ui/gui_main.py`

---

## 2026-03-21 — FEAT-010: Diagnostic Lab Version History Loop Closed

### Summary
The prompt-tuning backend was already in place, but the diagnostic lab still
stopped short of a safe workflow. This pass finishes the human-visible history
loop so prompt versions and benchmark runs can be inspected, compared, and
restored directly from the utility before promoting changes into the main app.

### Files Modified
- `_utils/agent_diagnostic_lab/src/diaglab/view.py`
  - finished the History tab controls
  - added restore confirmation
  - added comparison / history messaging
  - included history actions in busy-state handling
- `_utils/agent_diagnostic_lab/src/diaglab/controller.py`
  - wired prompt history refresh at startup
  - added restore + benchmark comparison actions
  - added restore/comparison formatting for the History tab
- `_utils/agent_diagnostic_lab/README.md`
  - documented version history, restore, and comparison workflow
- `_docs/TODO.md`
  - updated remaining tuning follow-up items

### Behavior Changes
- The diagnostic lab now exposes:
  - recent prompt versions from `.prompt-versioning/`
  - recent benchmark runs from `prompt_eval.db`
  - restore by prompt version id
  - benchmark comparison by run id
- Restore now writes the selected prompt snapshot back into the live prompt
  asset surface:
  - global prompt docs
  - project prompt overrides
  - project meta state
- Comparison output now shows:
  - aggregate score deltas
  - token deltas
  - round deltas
  - per-case regressions / improvements

### Testing
- `py -3.10 -m compileall src _utils\\agent_diagnostic_lab\\src`
- diagnostic service smoke:
  - listed prompt versions
  - listed benchmark runs
  - compared benchmark runs
- Tk smoke:
  - instantiated `DiagnosticView` + `DiagnosticController`
- restore smoke:
  - restored the latest prompt version successfully

---

## 2026-03-21 — BENCH-001: Agent Understanding Baseline Snapshot

### Summary
Ran a live diagnostic benchmark against the current app using the diagnostic lab
and `qwen3.5:4b` to establish a real pre-tuning baseline for agent
understanding. This is the first explicit "how smart is it right now?" snapshot
recorded in the dev log.

### Configuration
- Model: `qwen3.5:4b`
- Suite: `default` / `Default Understanding Suite`
- Base URL: `http://localhost:11434`
- Sandbox root: repo root (`_AppBIN/_work_in_progress/_AgenticTOOLBOX`)
- Docker mode: off
- Temperature: `0.7`
- Context tokens: `8192`
- Benchmark run id: `3`

### Measured Result
- Average overall score: `0.737`
- Average accuracy score: `0.917`
- Average efficiency score: `0.318`
- Total tokens: `18702`
- Total rounds: `4`
- Duration: `73608.8 ms`
- Status counts:
  - `ok = 3`

### Case Breakdown
- `intent_first_tools`
  - overall `0.801`
  - accuracy `1.000`
  - efficiency `0.337`
  - tokens `5561`
  - rounds `0`
  - probe run `9`
- `reality_workspace_rules`
  - overall `0.670`
  - accuracy `0.800`
  - efficiency `0.367`
  - tokens `5613`
  - rounds `0`
  - probe run `10`
- `context_architecture_summary`
  - overall `0.740`
  - accuracy `0.950`
  - efficiency `0.250`
  - tokens `7528`
  - rounds `4`
  - probe run `11`
  - first summary line still begins with:
    - `I'll start by exploring the project structure to understand the architecture.`

### Assessment
- Current agent understanding is solid in intent and context:
  - it generally picks the right tool-first strategy
  - it mostly respects workspace semantics and valid tool names
  - it can complete a real architecture inspection without failing
- Main weakness is not raw correctness, but efficient correctness:
  - architecture inspection still burns too many tokens
  - it remains slightly over-narrative before or during exploration
  - the reality/workspace case is competent but not yet fully precise
- Working benchmark verdict:
  - smart enough to be genuinely useful
  - not yet tuned enough to be reliably lean
  - strongest next target is reducing exploratory waste without losing accuracy

### Comparison To Previous Stored Run
- Compared against benchmark run `2`:
  - overall score improved from `0.734` -> `0.737`
  - accuracy stayed flat at `0.917`
  - efficiency improved from `0.308` -> `0.318`
  - total tokens dropped from `19112` -> `18702`
  - total rounds increased from `3` -> `4`
- Interpretation:
  - recent prompt changes made the agent slightly leaner overall
  - but architecture exploration is still the place where extra round churn shows up

### Testing
- live benchmark run through `DiagnosticService.run_benchmark_suite(...)`
- live comparison against stored benchmark run `2`

---

## 2026-03-21 — BENCH-002: Planner Slot Candidate Check

### Summary
Tested several local models specifically for planner-slot duty rather than
general worker duty. The question was not "which model is biggest," but "which
model produces a compact, reliable plan under the current app constraints."

### Result
- Current planner baseline: `qwen3.5:4b`
- Current primary chat baseline: `qwen3.5:4b`
- Recovery planner: intentionally disabled for now

### Findings
- `qwen3.5:4b`
  - passed compact planner prompts consistently
  - produced the requested `GOAL / FIRST_STEPS / RISKS / DONE_WHEN` structure
  - remained the most reliable planner candidate in the current environment
- `qwen2.5:7b`
  - timed out or failed under planner-style requests
  - not promoted to big planner
- `qwen3.5:9b`
  - failed repeated planner checks with timeout / disconnect / HTTP 500 behavior
  - also destabilized Ollama enough to make it a poor slot candidate for now
- DeepSeek R1 Distill 7B
  - can answer short planner-shaped prompts
  - but the current execution-planner request shape still triggers intermittent
    HTTP 500 failures, so it remains experimental

### Operational Decision
- `app_config.json` is now pinned to:
  - `primary_chat_model = qwen3.5:4b`
  - `planner_model = qwen3.5:4b`
  - `recovery_planning_enabled = false`
- The app now logs active model roles at startup and after settings changes so
  slot usage is visible in the runtime feed.

### Testing
- direct planner-prompt comparisons for:
  - `qwen3.5:4b`
  - `qwen2.5:7b`
  - `qwen3.5:9b`
- live main-pipeline planner-stage invocation with planner metadata and fallback
  behavior verified

---

## 2026-03-21 — FEAT-012: Planner Prompt Tightening

### Summary
The first planner-stage pass worked, but the output was still too generic and
too willing to suggest non-app-native commands like `tree` or IDE-driven
exploration. This tuning pass tightened the planner prompt, reduced planner
context/temperature, and normalized the output so the worker receives a shorter,
tool-native plan.

### Files Modified
- `src/core/agent/execution_planner.py`

### Behavior Changes
- Planner prompt now explicitly biases toward built-in structured tools:
  - `list_files`
  - `read_file`
  - `write_file`
  - `run_python_file`
- Planner now avoids suggesting:
  - `tree`
  - `ls`
  - `dir`
  - `cat`
  - `type`
  - `pip`
  - generic IDE exploration
  unless the user explicitly asks for them
- Planner output is now sanitized:
  - strips `<think>` blocks when present
  - extracts and normalizes `GOAL / FIRST_STEPS / RISKS / DONE_WHEN`
  - trims each section to a small bounded size
- Added a model-family compatibility branch so DeepSeek-style planner models can
  use a user-heavy prompt shape instead of the default system+user layout

### Measured Result
- `qwen3.5:4b` planner output improved from generic guidance to a compact,
  app-native plan:
  - `GOAL: Identify the Python app's top-level architecture...`
  - `FIRST_STEPS: list_files ... read_file ...`
- DeepSeek planner remained unstable / inconsistent in this pass and was not
  promoted beyond experimental status

### Testing
- `py -3.10 -m compileall src/core/agent/execution_planner.py`
- direct planner-stage smoke with:
  - `qwen3.5:4b`
  - DeepSeek R1 Distill 7B

---

## 2026-03-21 — FEAT-011: Model Role Slots And Planner Foundation

### Summary
Started the multi-model orchestration phase by replacing the implicit
"one dropdown = one model" assumption with explicit model-role slots. This
lays the groundwork for using a planner model up front, a deeper recovery
planner when the worker gets stuck, and specialist model routing without
smearing model ownership across the app.

### Files Added
- `src/core/agent/model_roles.py`

### Files Modified
- `src/core/config/app_config.py`
- `src/core/agent/thought_chain.py`
- `src/core/agent/response_loop.py`
- `src/core/engine.py`
- `src/ui/dialogs/settings_dialog.py`
- `src/app.py`
- `_docs/TODO.md`

### Behavior Changes
- Added explicit role slots to config:
  - `primary_chat_model`
  - `planner_model`
  - `recovery_planner_model`
  - `coding_model`
  - `review_model`
  - `fast_probe_model`
  - `embedding_model` remains explicit and now participates in role resolution
- Added model-role normalization so older `selected_model` usage stays compatible
  while the app moves toward role-based routing
- Added a `Models` tab in Settings so users can assign model slots directly
- Added explicit planning toggles in Settings:
  - `planning_enabled`
  - `recovery_planning_enabled`
- The existing thought-chain planner now uses the `planner_model` slot instead of
  always reusing the primary chat model
- The main execution path now resolves the primary chat role explicitly, which
  gives future planner/recovery hooks a clean seam

### Notes
- This pass is the foundation, not the full planner loop:
  - initial planner-before-execution is still TODO
  - repeated-failure recovery replanning is still TODO
- The design intent is now explicit:
  - planner models decide approach
  - worker models execute
  - the app orchestrates and records which role was used

### Testing
- `py -3.10 -m compileall src`
- config/model-role smoke:
  - verified primary role resolution from legacy `selected_model`
  - verified planner and recovery planner role overrides
  - verified seven role slots resolve cleanly
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

---

## 2026-03-20T19:10 — SAFETY-004: Structured Python Runner + GUI HITL Gate

### Summary
Added a dedicated `run_python_file` tool so the agent can test Python scripts without leaning on raw CLI. Local Tkinter / GUI launches are now governed by settings-backed policy (`deny | ask | allow`) with a human approval dialog, while Docker mode blocks GUI windows outright.

### Files Created
- `src/core/sandbox/python_runner.py` — structured sandbox-local Python execution with path validation, timeout control, Docker support, audit logging, and GUI gating
- `src/ui/dialogs/gui_launch_dialog.py` — approval modal with `Allow Once`, `Always Allow`, and `Deny`

### Files Modified
- `src/core/sandbox/gui_launch_guard.py` — now detects GUI/Tkinter scripts directly, not just CLI commands
- `src/core/sandbox/cli_runner.py` — local GUI launches from raw CLI now respect GUI policy and return better structured-tool suggestions on blocked commands
- `src/core/sandbox/sandbox_manager.py` — passes GUI policy/callback plumbing into the local CLI runner
- `src/core/sandbox/tool_catalog.py` — registers builtin `run_python_file`
- `src/core/agent/tool_router.py` — dispatches `run_python_file`
- `src/core/engine.py` — creates and wires `PythonRunner` in both local and Docker modes
- `src/app.py` — app-owned GUI approval callback persists `Always Allow` back into config
- `src/core/agent/prompt_builder.py` — prompt now teaches `run_python_file` as the preferred Python execution lane
- `src/core/agent/os_knowledge.py` — OS teaching now demotes CLI for routine inspection/testing
- `_docs/agent_prompt/50_tool_usage_preferences.md` — preference doc now nudges toward structured tools for Python testing
- `src/core/agent/transcript_formatter.py` — clearer formatting for `run_python_file` results
- `tests/test_tool_roundtrip.py` — added structured runner and router coverage

### Design Notes
- `run_python_file` only accepts sandbox-local `.py` / `.pyw` files; no inline code, shell chaining, or arbitrary interpreter flags
- GUI detection is intentionally heuristic and Tkinter-focused for now
- Docker mode blocks GUI launch attempts with an explicit explanation because desktop windows will not render meaningfully there
- Raw CLI remains available for advanced shell-native tasks, but the prompt now steers the model toward structured file and Python tools first

---

## 2026-03-20T20:05 — SAFETY-005: Disposable Run Workspaces

### Summary
Promoted Python execution into a disposable run lane. `run_python_file` now defaults to snapshotting the sandbox into `.mindshard/runs/<run_id>/workspace/` before execution, so experiments and test runs happen against a throwaway copy instead of the live project tree.

### Files Created
- `src/core/sandbox/run_workspace.py` — creates disposable execution snapshots and persists run manifests/results

### Files Modified
- `src/core/sandbox/python_runner.py` — defaults `run_python_file` to `workspace="run_copy"` and records `run_root`, `workspace_root`, and persisted stdout/stderr/result artifacts
- `src/core/sandbox/sandbox_manager.py` — provisions `.mindshard/runs/`
- `src/core/engine.py` — provisions `.mindshard/runs/` on workspace init
- `src/core/sandbox/tool_catalog.py` — documents the new `workspace` parameter
- `src/core/agent/tool_router.py` — passes the `workspace` option through
- `src/core/agent/prompt_builder.py`, `src/core/agent/os_knowledge.py`, `_docs/agent_prompt/50_tool_usage_preferences.md` — teach disposable run-copy behavior as the default execution lane
- `src/core/agent/transcript_formatter.py` — includes run-workspace metadata in tool results
- `tests/test_tool_roundtrip.py` — verifies disposable run-copy behavior and persisted run artifacts

### Design Notes
- Direct live-project execution is still available via `workspace: "sandbox"` when the user explicitly intends it
- Disposable snapshots intentionally exclude `.mindshard/`, `.git/`, `venv/`, `.venv/`, `node_modules/`, and `__pycache__/`
- Each run stores `manifest.json`, `stdout.txt`, `stderr.txt`, and `result.json` under the run root for inspection
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

---

## 2026-03-20 — FEAT-005: Prompt Docs Externalization + Tkinter Workbench Refactor

### Summary
Completed the next architecture step for MindshardAGENT in two connected parts:

1. **Prompt behavior externalization** — prompt semantics, response style, and interpretation guidance now load from editable docs instead of being trapped in hardcoded Python strings.
2. **Workbench UI refactor** — the overloaded right-side control stack was replaced with a three-region workstation shell: workspace rail, interaction center, and prompt workbench, plus a runtime strip.

This closes the first major usability loop: behavior is now editable, inspectable, and much easier to reason about in the UI.

### Files Created
- `src/core/agent/prompt_sources.py` — ordered prompt-doc loader with override precedence, diagnostics, and source fingerprinting
- `_docs/agent_prompt/00_identity.md`
- `_docs/agent_prompt/10_workspace_semantics.md`
- `_docs/agent_prompt/20_intent_interpretation.md`
- `_docs/agent_prompt/30_file_listing_rules.md`
- `_docs/agent_prompt/40_response_style.md`
- `_docs/agent_prompt/50_tool_usage_preferences.md`
- `_docs/agent_prompt/90_local_notes.md`
- `src/ui/dialogs/detach_project_dialog.py` — detach confirmation dialog with keep-sidecar option
- `tests/test_prompt_sources.py` — prompt source loader coverage

### Files Modified
- `src/core/agent/prompt_builder.py` — prompt composition rewritten around layered prompt sources + runtime sections
- `src/core/agent/response_loop.py` — prompt bundle/preview integration and source fingerprint tracking
- `src/core/engine.py` — prompt preview method and detach keep-sidecar support
- `src/core/project/project_meta.py` — brief form helpers and prompt override scaffold support
- `src/ui/dialogs/project_brief_dialog.py` — editable `display_name` + edit flow support
- `src/ui/panes/control_pane.py` — rebuilt as workstation shell with:
  - left notebook: `Session`, `Sandbox`, `Git`
  - center notebook: `Compose`, `Sandbox CLI`
  - right notebook: `Prompt`, `Sources`, `Inspect`, `Tools`
  - summary cards for session/project/prompt state
  - structured source-layer cards in `Sources`
  - inline source editor with `New`, `Load`, `Save`, `Save As`, `Edit`, and folder-open actions
  - startup sash stabilization and pane minimum sizes
- `src/ui/gui_main.py` — vertical shell/root composition updated to match the new workstation layout
- `src/app.py` — prompt inspector wiring, prompt/response mirror updates, workspace tab cycling, brief/prompt edit actions
- `tests/test_project_lifecycle.py` — project brief + detach retention coverage
- `tests/test_tool_roundtrip.py` — prompt bundle expectations updated
- `_docs/TKINTER_UI_TREE.md` — implementation status and current-shell notes added

### Behavior Changes
- Global prompt defaults now live in `_docs/agent_prompt/`
- Project-specific prompt overrides now live in `.mindshard/state/prompt_overrides/`
- Effective prompt sources are visible in the UI and reloadable without code edits
- Project brief can be edited after attach
- Detach can preserve the full `.mindshard/` sidecar when requested
- The old cluttered `Watch` stack has been replaced by a dedicated prompt workbench

### Testing
- `py -3 -m compileall src tests`
- Python smoke tests for:
  - prompt override precedence
  - prompt bundle generation
  - prompt override scaffold creation
  - detach with `keep_sidecar=True`
- Tk smoke tests for:
  - notebook counts / shell initialization
  - startup pane widths after sash stabilization

### Notes For Continuation
- The architectural UI phases are complete; future work is polish and interaction refinement, not shell redesign.
- `Sources` now has a structured layer view, but source toggles/diffing are still deferred.
- `Sources` also now supports direct prompt-doc editing for file-backed layers; runtime layers remain read-only by design.
- Tab breakout behavior was intentionally not carried forward into the new notebook shell.

---

## 2026-03-21 — FEAT-009: Benchmark Runner And Token-Aware Scoring

### Summary
The diagnostic lab could run single probes, but it still lacked a repeatable,
human-visible tuning workflow. This pass adds a benchmark layer that is exposed
to people in the utility UI while remaining structured enough for agents to use
programmatically.

### Files Added
- `_docs/benchmark_suite.json`
- `src/core/agent/benchmark_loader.py`
- `src/core/agent/benchmark_runner.py`
- `src/core/agent/probe_scorer.py`

### Files Modified
- `src/core/agent/prompt_tuning_store.py`
- `_utils/agent_diagnostic_lab/src/diaglab/models.py`
- `_utils/agent_diagnostic_lab/src/diaglab/reporting.py`
- `_utils/agent_diagnostic_lab/src/diaglab/services.py`
- `_utils/agent_diagnostic_lab/src/diaglab/controller.py`
- `_utils/agent_diagnostic_lab/src/diaglab/view.py`
- `_utils/agent_diagnostic_lab/README.md`

### Behavior Changes
- Benchmark suites now live in editable JSON under `_docs/benchmark_suite.json`
- Added a core loader + runner so benchmark ownership sits outside the utility UI
- Added token-aware scoring:
  - `accuracy_score`
  - `efficiency_score`
  - `overall_score`
  - numeric `tokens_in_num`, `tokens_out_num`, `total_tokens`
- Added benchmark persistence:
  - `benchmark_runs`
  - `benchmark_run_items`
- The diagnostic lab now exposes:
  - benchmark suite selection
  - `Run Suite`
  - benchmark summaries in a dedicated results tab
  - score readout in the top metrics strip

### Notes
- The lab still exports single probes and benchmark suites separately
- The benchmark suite is intentionally small for now:
  - intent
  - workspace reality
  - architecture understanding
- Findings/scoring live in `probe_scorer.py`, not in the UI or the store

### Testing
- `py -3.10 -m compileall src _utils\\agent_diagnostic_lab\\src`
- direct-model probe smoke:
  - `overall_score=0.808`
  - `total_tokens=5526`
  - `probe_run_id=5`
- benchmark suite smoke:
  - `default`
  - `average_overall_score=0.734`
  - `case_count=3`
  - `benchmark_run_id=2`

---

## 2026-03-21 — FEAT-008: Hybrid Prompt Tuning History

### Summary
Prompt tuning had become effectively destructive: editing a prompt doc overwrote
the old state, and probe runs had no durable link back to the exact prompt
version that produced them. This pass adds a hybrid history layer:

- `.prompt-versioning/` as a local Git-backed prompt snapshot repo
- `prompt_eval.db` as a SQLite store for probe runs, findings, and scores

This gives agents and humans a real tuning memory instead of relying on the
current working files and Git for everything.

### Files Added
- `src/core/agent/prompt_tuning_store.py`

### Files Modified
- `src/app.py`
- `src/ui/gui_main.py`
- `src/ui/panes/control_pane.py`
- `_utils/agent_diagnostic_lab/src/diaglab/services.py`

### Behavior Changes
- Saving a prompt doc from the in-app Sources editor now snapshots the current
  effective prompt sources into `.prompt-versioning/` and commits them in a
  local Git repo
- Project brief edits and prompt override scaffold creation also snapshot prompt
  state because they change the effective prompt seen by the agent
- Diagnostic Lab probes now:
  - snapshot prompt state before recording results
  - write probe runs into SQLite
  - attach simple heuristic findings
  - compute a first-pass score
  - link exports back to the stored probe run
- Probe metadata now carries:
  - `prompt_version_id`
  - `prompt_version_commit`
  - `probe_run_id`
  - `score`

### Stored Artifacts
- `.prompt-versioning/`
  - local Git working tree of:
    - `global_agent_prompt/`
    - `project_prompt_overrides/`
    - `project_meta/`
    - `manifest.json`
- `.prompt-versioning/prompt_eval.db`
  - `prompt_versions`
  - `probe_runs`
  - `probe_findings`

### First-Pass Findings Heuristics
- unknown tool names
- invented `project/` path prefixes
- `pip install tkinter` suggestions
- high round counts
- narrated tool-preface behavior

### Testing
- `git --version`
- `py -3.10 -m compileall src _utils\\agent_diagnostic_lab\\src`
- smoke script:
  - created a prompt snapshot
  - ran a Prompt Probe through the diagnostic lab
  - recorded `probe_run_id=1`
  - exported the report bundle
  - confirmed latest prompt version lookup

---

## 2026-03-21 — FEAT-007: Agent Diagnostic Lab Utility

### Summary
The project needed a way to inspect and tune the agent more surgically than the
main chat shell allows. This pass adds a standalone internal utility app under
`_utils/agent_diagnostic_lab/` that can probe prompt assembly, direct model
streaming, and the full engine turn loop while exporting reports for later
comparison.

### Files Added
- `_utils/agent_diagnostic_lab/README.md`
- `_utils/agent_diagnostic_lab/run.bat`
- `_utils/agent_diagnostic_lab/src/app.py`
- `_utils/agent_diagnostic_lab/src/diaglab/models.py`
- `_utils/agent_diagnostic_lab/src/diaglab/services.py`
- `_utils/agent_diagnostic_lab/src/diaglab/reporting.py`
- `_utils/agent_diagnostic_lab/src/diaglab/controller.py`
- `_utils/agent_diagnostic_lab/src/diaglab/view.py`
- `_utils/agent_diagnostic_lab/src/diaglab/components/section_frame.py`
- `_utils/agent_diagnostic_lab/src/diaglab/components/metric_card.py`
- `_utils/agent_diagnostic_lab/src/diaglab/components/log_panel.py`

### Behavior Changes
- Added an isolated diagnostics bench with a themed Tk UI matching the main app
- Added three first-pass probes:
  - `Prompt Probe` for effective system prompt inspection
  - `Direct Model Probe` for raw `chat_stream(...)` timing and response capture
  - `Engine Turn Probe` for full-engine activity tracing without the main app UI
- Added export bundles under `_utils/agent_diagnostic_lab/outputs/`:
  - `report.json`
  - `report.md`
  - `prompt.txt`
  - `response.txt`
  - `events.jsonl`
- Resource polling and model scanning are surfaced directly in the utility
- Probe runs can be stopped cooperatively through the lab UI

### Notes
- The utility imports real core modules from the main app by bootstrapping the
  main project root onto `sys.path`
- The lab defaults its sandbox path to the current project root so the app can
  inspect itself immediately
- GUI launch policy is forced to `deny` for engine probes in the lab to keep
  diagnostics safe and predictable

### Testing
- `py -3.10 -m compileall _utils\\agent_diagnostic_lab\\src`
- prompt-probe smoke script:
  - imports `diaglab.services`
  - builds a live prompt bundle against the current repo
  - confirms prompt text and event capture are returned

---

## 2026-03-20 — FEAT-006: Compact Tool Transcript + Configurable Tool Loop Limit

### Summary
Testing exposed two pain points in agentic exploration turns:

1. tool-call transcripts were being preserved as verbose fenced JSON blocks
2. the response loop had a hardcoded 5-round tool limit with no user control

This pass makes tool-heavy turns much easier to inspect and manage.

### Files Modified
- `src/core/config/app_config.py` — added persisted `max_tool_rounds`
- `src/core/agent/transcript_formatter.py` — added compact tool-call transcript formatting:
  - raw fenced `tool_call` JSON becomes a concise `TOOL_CALLS: ...` summary
- `src/core/agent/response_loop.py` — now uses configurable tool round limits, appends a clear note when the round cap is hit, and supports stop requests
- `src/core/ollama/ollama_client.py` — added cooperative stream stop hook
- `src/core/engine.py` — added `request_stop()` passthrough
- `src/ui/panes/control_pane.py` — added Tools-tab loop controls (`Max Tool Rounds` + apply/status)
- `src/ui/gui_main.py` — passed tool loop settings wiring through to the control pane
- `src/app.py` — saves tool loop settings, updates UI status, and sends Escape stop requests into the live response loop
- `_docs/TKINTER_UI_TREE.md` — noted the Tools-tab loop controls

### Behavior Changes
- Tool-heavy assistant turns now save/display compact summaries such as:
  - `TOOL_CALLS: read_file(path:src/app.py, start:0, end:20000), ...`
- The max tool round limit is now adjustable in the `Tools` tab instead of hardcoded in code
- Escape now requests a real stop on the active response loop rather than only halting the UI flush timer

### Testing
- `py -3 -m compileall src tests`
- direct compact-transcript smoke test
- Tk smoke test for Tools-tab round-limit callback wiring

---

## 2026-03-20 — FIX-002: Legacy Root Folders Removed From Sandbox Layout

### Summary
User testing revealed that the app was still creating the pre-`.mindshard/`
root folders (`_tools`, `_sessions`, `_outputs`, `_logs`) even though the
new sidecar architecture had already moved those concerns under `.mindshard/`.

Root cause: `SandboxManager` had not been migrated with the rest of the
architecture and was still initializing the old root-level structure.

### Files Modified
- `src/core/sandbox/sandbox_manager.py`
  - moved managed directories to `.mindshard/{logs,outputs,sessions,state,tools,parts,ref,vcs}`
  - moved audit log path to `.mindshard/logs/audit.jsonl`
  - added safe cleanup of empty legacy root folders
  - warns when non-empty legacy folders are still present outside `.mindshard/`

### Testing
- `py -3 -m compileall src`
- temporary sandbox smoke test confirming:
  - `.mindshard/` subdirs are created
  - empty legacy root folders are removed
  - audit log path resolves to `.mindshard/logs/audit.jsonl`

---

## 2026-03-23T12:00 — TIERED-MEM-001: STM Sliding Window + Evidence Bag Integration

### Summary
Implemented tiered memory architecture: chat history now has a sliding window (STM) with
falloff turns ingested into a reversible evidence bag (manifold NodeStore). Prompt carries
a compact bag summary every turn. Two-pass retrieval fires when the model signals uncertainty,
pulling deeper evidence and re-generating. Added `bag_inspect` MCP tool for observability.

**Critical design principle (empirically validated):** The evidence bag is NOT a replacement
for STM or RAG. Without temporal flow from the sliding window, models produce factually-referenced
but causally disconnected output — snippets, not scripts. The window is what the model *thinks with*;
the bag is what it *looks up*.

### Architecture
```
Turn N arrives
  ├─ Sliding Window: last W turns kept verbatim (STM — causal flow)
  ├─ Falloff: turns older than W → ingested into Evidence Bag (full text, never destroyed)
  ├─ Bag Summary: ~128 token summary of bag contents, always in prompt
  └─ Pass 2 (conditional): if model response has uncertainty markers,
     retrieve deeper evidence (512 token budget) and re-generate once
```

### Files Created
- `src/core/sessions/evidence_adapter.py` — thin adapter wrapping manifold SDK EvidencePackage
- `.dev-tools/drop-bin/_manifold-mcp/tools/bag_inspect.py` — MCP tool: inspect bag contents + what agent sees

### Files Modified
- `src/core/config/app_config.py`
  - added `stm_window_size` (default 10), `evidence_bag_enabled` (default True)
  - added `evidence_bag_summary_budget` (128), `evidence_bag_retrieval_budget` (512)
- `src/core/agent/response_loop.py`
  - sliding window: `chat_history[-window_size:]` kept verbatim, older turns → falloff
  - falloff ingested into evidence bag via `EvidenceBagAdapter.ingest_falloff()`
  - bag summary injected as system message after planner/stage context
  - two-pass detection: `_needs_evidence_dive()` checks 11 uncertainty markers
  - pass-2: retrieves deeper evidence, appends to messages, re-generates once
  - metadata: `stm_window_size`, `stm_falloff_count`, `evidence_bag_active`
- `src/core/engine.py`
  - creates `EvidenceBagAdapter` during `set_sandbox()` if enabled
  - passes to ResponseLoop constructor
  - added `set_evidence_bag()` method for late attachment
- `.dev-tools/drop-bin/_manifold-mcp/mcp_server.py`
  - registered `bag_inspect` tool in TOOL_REGISTRY

### External Dependency
- Manifold SDK at `.dev-tools/drop-bin/_manifold-mcp/sdk/evidence_package.py`
  - Lexical token-overlap scoring (no embedding dependency)
  - JSON-based corpus storage, fully reversible
  - Built by external agent, vendored into project

### Testing
- Evidence adapter: ingest, summary, retrieval, dedup, lifecycle — all pass
- Config fields: defaults correct, JSON serialization roundtrip clean
- Two-pass heuristic: 11 uncertainty markers detected, zero false positives
- bag_inspect MCP tool: returns corpus stats, agent summary slice, pass-2 retrieval view
- All 4 modified files: `py_compile` passes

### Cleanup (same session)
- Removed all `__pycache__` directories outside `.venv/`
- Removed stale project mapper artifacts from `_logs/`

### Open TODOs (logged, not built)
- NDJSON/Content-Length protocol adapter for MCP servers (manifold server uses Content-Length)
- UI evidence bag explorer tab (browse bag contents, expand individual nodes)
- App-wide highlight→ask context menu (right-click → ask in isolation or inject into chat)
- CIS staleness: when bag contents change, embedded summary in RAG becomes stale (Step 8 in plan)

---

## 2026-03-23T13:00 — BUDGET-001: Token Budget Guard + Multi-Pass Infrastructure

### Summary
Added a token budget guard that prevents OOM by trimming prompt components in priority
order before hitting the model. Also pre-installed config and interfaces for future
multi-pass prompt splitting (disabled by default, fallback to budget guard).

Token analysis showed typical turns use ~2,935/8,192 tokens (safe), but worst-case
scenarios (9B model + RAG + journal + VCS + long window + tool rounds) exceed budget
by ~1,015 tokens. The guard catches this automatically.

### Architecture
```
Before model inference:
  ContextBudgetGuard registers all prompt components with trim priorities:
    priority 0: system prompt (never trim)
    priority 2: planner guidance
    priority 3: STM window (drops oldest messages)
    priority 4: stage context
    priority 5: bag summary
    priority 6: RAG context (trimmed first)

  If total > (max_context * 0.85):
    Trim highest-priority-number components first
    Log all trim actions for data gathering
    Flag if multi-pass would have been better (>30% trimmed)
```

### Files Created
- `src/core/agent/context_budget.py` — ContextBudgetGuard, BudgetSlot, BudgetReport

### Files Modified
- `src/core/agent/response_loop.py`
  - message assembly now goes through budget guard
  - budget report metrics added to response metadata
  - activity stream logs budget status every turn
- `src/core/config/app_config.py`
  - added `budget_reserve_ratio` (0.15), `multipass_enabled` (False), `multipass_strategy` ("iterative")

### Data Gathering
Response metadata now includes:
- `budget_total_before`: tokens before any trimming
- `budget_total_after`: tokens after trimming
- `budget_available`: max tokens minus output reserve
- `budget_trimmed`: whether trimming occurred
- `budget_multipass_recommended`: whether >30% was trimmed (multi-pass would help)

### Testing
- Under budget: passes through clean, no trimming
- Over budget: trims in correct priority order (RAG first, then stage, then window)
- Impossible budget (system prompt alone exceeds): trims everything possible, warns
- Multi-pass flag: correctly triggers when >30% of content is trimmed
- All files: `py_compile` passes

### Multi-Pass Infrastructure (pre-installed, not active)
Config fields ready: `multipass_enabled`, `multipass_strategy` ("iterative" vs "synthesize").
Budget report's `would_benefit_from_multipass` flag will drive the decision when enabled.
The iterative strategy builds response incrementally across sub-prompts; synthesize
merges parallel sub-responses. Both record which strategy was used for comparison data.

---

## 2026-03-25T14:42 — STAB-001: Core Stabilization, UI Bridge, Live Verification

### Summary
Focused on core stabilization before returning to builder-contract alignment.
This pass closed the active runtime defects from the bug/frailty sweep, restored
trustworthy automated tests, and made the visible Tk app directly drivable for
live end-to-end verification.

### Core Runtime Fixes Landed
- Windows sandbox/local tool execution no longer relies on fragile shell quoting
- assistant persistence no longer fails silently on stream finalization
- session store access is serialized with an `RLock`
- shutdown now drains worker loops before DB close, including standalone and
  loop-managed thought-chain paths
- VCS init/detach race was closed by tracking the async init thread and waiting
  before snapshot/archive
- discovered toolbox tools now preserve their real script path/source and reload
  correctly across sandbox switches
- planner/thought-chain stop handling now propagates honestly instead of only
  changing UI state

### UI Control Bridge Added
Built a localhost-only in-process control bridge for the running Tk app:
- `src/app_ui_bridge.py` — local HTTP bridge
- `src/mcp/ui_bridge_server.py` + `mcp_ui_bridge_server.py` — MCP proxy
- `src/ui/ui_facade.py` — expanded with visible-control intent methods

Supported visible actions now include:
- attach project
- start new session
- set input text / submit
- set loop mode
- click faux buttons / run Plan
- request stop
- reload tools / prompt docs
- query live UI state

### Live Verification
Visible testing was run against:
- `C:\Users\jacob\Documents\_UsefulHelperAPPS\_MindshardBridgeLab`

Confirmed live behaviors:
- bridge can control the visible app window
- model label/startup sync repaired
- direct-chat path succeeded (`BRIDGE_OK`)
- planner-only stop path succeeded and recorded `[Stopped by user request.]`
- thought-chain/Plan path completes visibly through all rounds and posts a final
  task list

### Bridge-State Hardening
A real visibility bug showed up during Plan testing: the bridge treated the app
as idle immediately because it only watched `ui_state.is_streaming`.

Fixes:
- added shared busy-operation tracking in `UIState` / `AppState`
- `thought_chain_command_handler` now marks Plan runs busy and clears busy on
  completion/error
- `app_streaming` now tracks busy mode for direct-chat / planner-only /
  thought-chain submit paths
- Escape/request-stop now marks the app as stopping instead of lying about
  immediate idle
- bridge state now exposes `is_busy`, `busy_kind`, and `stop_requested`
- `wait_until_idle` now waits on busy state, not streaming-only state

### Test Results
- `python -m pytest -q` -> 40 passed
- `python -m tests.test_tool_roundtrip` -> 92 passed
- regression coverage added for toolbox execution/source retention, stop
  behavior, and bridge idle detection

### New Hardening TODOs From Live Testing
1. Plan/thought-chain domain anchoring
   The planner interpreted "bridge lab workspace" as a physical/civil-engineering
   scenario because the thought-chain prompt is generic and not grounded in the
   attached software project.
2. Plan performance guardrails for 4B models
   Current live run showed very slow round timings: round 1 ~88.8s, round 2
   ~177.1s, round 3 still in progress when logged. Needs per-round timeout,
   first-token latency logging, heartbeat/progress telemetry, and output caps.
3. Bridge sequencing discipline
   Dependent UI bridge actions like attach-project then new-session must be sent
   sequentially, not in parallel.

### Status
Core runtime stability is materially better, automated tests are green, and the
app is visibly testable again. Immediate next work should stay in stabilization:
finish live-testing hardening (prompt anchoring + planner performance
guardrails), then continue through the remaining bug/frailty list before
resuming builder-contract alignment.

### Late-Session Note
A later live `Plan` run on `qwen3.5:4b` accepted a real stop request but did not
return to `Ready`; the window remained stuck in `Stop requested`. The app was
hard-closed after preserving records. Session cleanup afterward kept only the
two meaningful saved sessions:
- `Bridge UI Smoke — BRIDGE_OK round-trip`
- `Bridge UI Smoke — Planner stop verification`
