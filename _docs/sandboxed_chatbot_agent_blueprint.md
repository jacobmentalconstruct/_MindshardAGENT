# Sandboxed Chatbot Agent Blueprint

## Purpose

Build a **lean local chatbot agent shell** with one real baked-in capability:

- **CLI tool use inside a user-selected sandbox folder**

The application is intentionally narrow.
It is **not** a general agent platform, not a multi-tool sprawl box, and not a full autonomous builder swarm.
It is a **single-user local agent workbench** whose first job is:

1. chat with a locally selected Ollama model
2. expose one default tool for sandboxed CLI operations
3. allow the agent to create and organize additional tools **inside the sandbox only**
4. preserve sessions and conversation state cleanly
5. surface internal activity clearly to the user

The system must remain compatible with the existing builder contract and the lean prototype-registry direction already established.

---

# 1. Core Product Definition

## 1.1 What this app is

A **desktop Tkinter chatbot shell** for a local Ollama-backed agent that can:

- run in a bounded sandbox
- use CLI commands only within that sandbox
- display rich internal runtime/logging activity
- save and load session memory from SQLite
- branch and manage sessions
- optionally allow the agent to author new sandbox-local tools

## 1.2 What this app is not

This first version is **not**:

- a full IDE
- a full terminal emulator
- a multi-agent orchestration framework
- a global system shell
- a filesystem-wide automation tool
- a browser / network automation platform
- a production-grade graph backend

It should stay lean and disciplined.

---

# 2. Design Principles

## 2.1 Narrow first capability

The application should begin with exactly one real built-in tool:

- **sandboxed CLI operations**

Everything else is secondary.

## 2.2 Tool growth remains sandbox-bounded

If the agent creates tools, those tools must:

- be created **inside the selected sandbox**
- live in a clearly named sandbox-local tools area
- include clean metadata / docstring / usage notes
- remain callable only within the app’s allowed tool execution path

## 2.3 Registry-minded but lean

The app should use the **prototype registry state graph mindset**, but not require a heavy graph backend.

That means:

- typed records
- stable IDs
- event and action recording
- clear ownership
- serializable state
- future upgrade path to richer graph/state machinery

## 2.4 Strong boundaries

The tool layer must never quietly escape the sandbox root.

The user selects:

- **sandbox root**
- **official toolbox root**

The agent may:

- read and write within the sandbox root
- call approved tools from the configured official toolbox
- create new sandbox-local tools under the sandbox’s tool area

The agent may not:

- write outside the sandbox root without explicit user approval
- run arbitrary CLI commands against the whole machine
- silently import external project runtime dependencies

---

# 3. Product Scope for Version 1

## 3.1 Required capabilities

### Chat
- local Ollama model selection
- send prompt
- receive streamed assistant response
- show response metadata under each assistant message

### Tool use
- one built-in tool: sandboxed CLI execution
- verbose activity stream in a lower log panel
- tool calls recorded into runtime state

### Session management
- new session
- save session
- load session
- delete session
- branch session
- auto-save on close optional

### Runtime visibility
- terminal/log window that streams internal activity
- display current model
- display approximate token counts
- display inference timing where available

### UI shell
- title bar/header
- left conversation column
- lower runtime/log column
- right control column
- model picker
- user input box
- submit button
- reserved faux-button panel

---

## 3.2 Explicitly deferred

For the prototype release, defer:

- multiple built-in tools beyond CLI sandbox tool
- full plugin marketplace behavior
- persistent graph database backend
- deep resource telemetry beyond basic polling
- full tokenizer-accurate live counts for every model family
- multi-tab workspaces
- agent self-editing outside sandbox
- approval workflow complexity beyond basic confirmation boundaries

---

# 4. Recommended Folder Structure

This stays aligned with the existing scaffold and contract.

```text
_AgenticTOOLBOX/
├── README.md
├── LICENSE.md
├── requirements.txt
├── setup_env.bat
├── run.bat
├── _docs/
│   ├── builder_constraint_contract.md
│   ├── prototype_registry_state_graph.md
│   ├── ARCHITECTURE.md
│   ├── DEV_LOG.md
│   └── TODO.md
├── _sandbox/
│   ├── README.md
│   ├── _tools/
│   ├── _sessions/
│   ├── _outputs/
│   └── _logs/
└── src/
    ├── app.py
    ├── ui/
    │   ├── gui_main.py
    │   ├── panes/
    │   │   ├── chat_pane.py
    │   │   ├── activity_log_pane.py
    │   │   ├── control_pane.py
    │   │   └── input_pane.py
    │   ├── widgets/
    │   │   ├── chat_message_card.py
    │   │   ├── metadata_tag_row.py
    │   │   ├── model_picker.py
    │   │   ├── status_light.py
    │   │   └── faux_button_panel.py
    │   └── ui_state.py
    └── core/
        ├── engine.py
        ├── config/
        │   └── app_config.py
        ├── registry/
        │   ├── state_registry.py
        │   ├── records.py
        │   └── session_registry.py
        ├── sessions/
        │   ├── session_store.py
        │   └── sqlite_schema.py
        ├── ollama/
        │   ├── ollama_client.py
        │   ├── model_scanner.py
        │   └── tokenizer_adapter.py
        ├── runtime/
        │   ├── event_bus.py
        │   ├── runtime_logger.py
        │   └── activity_stream.py
        ├── sandbox/
        │   ├── sandbox_manager.py
        │   ├── path_guard.py
        │   ├── cli_runner.py
        │   ├── tool_catalog.py
        │   └── tool_scaffold.py
        ├── agent/
        │   ├── prompt_builder.py
        │   ├── response_loop.py
        │   ├── tool_router.py
        │   └── transcript_formatter.py
        └── utils/
            ├── ids.py
            ├── clock.py
            └── text_metrics.py
```

---

# 5. Core Runtime Model

## 5.1 Runtime shape

Use a **lean app-root + engine + registry + UI** model.

### `src/app.py`
- composition root
- app startup/shutdown
- config bootstrap
- registry bootstrap
- engine bootstrap
- UI bootstrap

### `src/core/engine.py`
- main runtime coordinator
- owns the active session context
- receives UI actions
- routes them to model/tool/session subsystems
- pushes structured activity events back to the UI

### `src/core/registry/state_registry.py`
- lean in-memory app state registry
- typed records
- no heavy graph backend yet
- tracks sessions, prompts, responses, tool runs, sandbox state, model state

This preserves your strangler path into richer graph/state later.

---

# 6. Main State Domains

## 6.1 App state

Tracks:
- selected model
- selected sandbox root
- selected toolbox root
- current session ID
- UI status flags
- current resource snapshot

## 6.2 Session state

Tracks:
- conversation turns
- branch lineage
- save timestamps
- title/label
- summary/notes if later added

## 6.3 Runtime activity state

Tracks:
- tool invocation start/finish
- CLI command events
- model request start/finish
- token estimates
- errors/warnings
- sandbox path violations blocked

## 6.4 Sandbox state

Tracks:
- sandbox root
- local sandbox tool folder
- allowed command execution root
- optional generated outputs/logs

## 6.5 Model state

Tracks:
- available Ollama models
- selected model
- model status
- latest latency
- last token estimate
- memory availability snapshot

---

# 7. Session Storage Model

## 7.1 SQLite persistence

Use SQLite for session persistence.

### Store at least:
- sessions
- messages
- branches
- tool invocations
- runtime events (optional compact subset)

## 7.2 Required session operations

- **New Session**
- **Save Session**
- **Load Session**
- **Delete Session**
- **Branch Session**

## 7.3 Save strategy

Support both:
- manual save
- save-on-close

Optional later:
- autosave debounce after turn completion

## 7.4 Branch semantics

A branch should:
- copy message history reference forward
- record parent session ID
- optionally mark branch point message ID
- preserve lineage cleanly

---

# 8. Sandbox and Tool Model

## 8.1 User-configured roots

The app should allow the user to choose:

- **Sandbox Root**
- **Official Toolbox Root**

These should be shown in UI and persisted in config.

## 8.2 Default built-in tool

### Tool name
`cli_in_sandbox`

### Purpose
Execute a CLI command **only within the sandbox root**.

### Responsibilities
- enforce working directory inside sandbox
- block path escape attempts
- capture stdout/stderr
- record exit code
- log command start and finish
- stream events into activity window

## 8.3 Future sandbox-authored tools

If the agent creates tools, they must be placed under something like:

```text
<sandbox_root>/_tools/
```

Each created tool should include:
- filename
- purpose header
- usage header
- constraints header
- generated-by metadata

No hidden dumping of random scripts into the sandbox root.

## 8.4 Tool catalog behavior

The app should maintain a simple tool catalog with:
- built-in tools
- official external toolbox references
- sandbox-local generated tools

But version 1 only needs **one real executable built-in tool**.

---

# 9. Agent Behavior Model

## 9.1 Agent loop

The agent loop is intentionally simple:

1. user submits prompt
2. prompt builder constructs system + session + tool instructions
3. model responds
4. if tool call is requested, tool router validates it
5. CLI tool runs in sandbox
6. tool output is appended into the turn flow
7. model continues if needed
8. final assistant response is stored

## 9.2 Tool instruction policy

The system prompt should instruct the model that:

- it may only use registered tools
- CLI operations are sandbox-bound
- any tool it creates must be placed under the sandbox tool area
- created tools must be cleanly named and documented
- it should prefer existing official tools first when appropriate
- it must not assume filesystem access outside the sandbox

## 9.3 Initial tool-use discipline

Keep this basic:
- structured tool call envelope
- single built-in tool route
- tool results marshaled back into transcript
- full logging in activity panel

No need for complex agent-planner architecture yet.

---

# 10. UI Blueprint

## 10.1 Main window layout

### Top bar
A simple title/status area.

Suggested contents:
- app title
- active model label
- sandbox root summary
- session name
- save state indicator

---

## 10.2 Left main column

### Top: chat history view
This is the main transcript display.

Each message card should show:
- role (user / assistant / tool if needed)
- message body
- low-contrast metadata row beneath assistant responses

Suggested metadata tags:
- model name
- estimated tokens in/out
- inference time
- tool count for turn
- timestamp

### Bottom: runtime activity / terminal log view
This is a separate scrollable pane under the chat history.

Purpose:
- show verbose internal runtime activity
- registry/event stream visibility
- model request lifecycle
- tool execution lifecycle
- sandbox enforcement messages
- warnings/errors

This should look like a low-level terminal/log viewer, not like chat.

---

## 10.3 Right column

### Top block: model picker and model status

Required:
- dropdown/list of local Ollama models
- refresh button
- current model indicator
- model availability state

Also display:
- CPU / RAM usage summary
- GPU / VRAM usage summary
- green/red status indicator
- used / available memory numbers

This can be basic polling, not high-precision telemetry.

### Middle block: last prompt preview

Show the last active prompt envelope or last user prompt context.

For version 1 this can simply display:
- the last user message
- optionally the final model prompt preview if available cheaply

### Lower middle: user input box

A text entry area where the user types.

Prefer:
- multi-line text widget
- live approximate token estimate while typing
- submit button below

### Lower block: reserved button panel

A visual panel below the submit area reserved for future actions.

For now the buttons may be faux/inert except for visual response.

Example placeholders:
- Plan
- Tools
- Files
- Session
- Sandbox
- Branch

These do not need real behavior in version 1.

---

# 11. Token Count Strategy

## 11.1 Requirement

The user wants a live running token count or close approximation while typing.

## 11.2 Recommended prototype approach

Do **not** block the design on exact per-model tokenizer parity.

Use a pluggable adapter strategy:

### Preferred order
1. exact model tokenizer if cheaply available
2. fallback tokenizer approximation
3. rough text heuristic if no tokenizer available

## 11.3 UI behavior

Display this as:
- `Approx tokens: N`

Do not overclaim exactness unless exact tokenizer support is truly active.

---

# 12. Resource Status Strategy

## 12.1 Requirement

Right column should show CPU/RAM and GPU/VRAM usage with red/green light.

## 12.2 Recommended prototype behavior

Implement a simple polling monitor that updates every few seconds.

Display:
- CPU %
- RAM used / total
- GPU presence
- VRAM used / total if available

If GPU metrics are unavailable on a machine, show:
- `GPU metrics unavailable`

Do not make version 1 depend on fragile vendor-specific telemetry.

---

# 13. Suggested Internal Modules

## 13.1 `ollama_client.py`
Responsibilities:
- list models
- run chat request
- stream responses
- normalize response payloads

## 13.2 `model_scanner.py`
Responsibilities:
- discover local Ollama models
- refresh list on demand

## 13.3 `tokenizer_adapter.py`
Responsibilities:
- estimate live token count
- model-specific adapter hook later

## 13.4 `sandbox_manager.py`
Responsibilities:
- store selected sandbox root
- validate paths
- expose standard sandbox folders

## 13.5 `path_guard.py`
Responsibilities:
- normalize paths
- confirm all tool execution remains under sandbox root
- reject traversal escapes

## 13.6 `cli_runner.py`
Responsibilities:
- execute subprocess safely in sandbox
- capture stdout/stderr/exit code
- emit runtime activity events

## 13.7 `tool_catalog.py`
Responsibilities:
- registry of built-in, official, and sandbox-local tools
- tool metadata and lookup

## 13.8 `tool_scaffold.py`
Responsibilities:
- create new sandbox-local tools with clean headers
- enforce placement under sandbox `_tools/`

## 13.9 `prompt_builder.py`
Responsibilities:
- compose system prompt
- include tool policy
- include sandbox policy
- include selected model/tool/session context

## 13.10 `tool_router.py`
Responsibilities:
- parse model tool intent
- validate tool name and payload
- call only approved tools

## 13.11 `response_loop.py`
Responsibilities:
- manage one user turn
- stream partial model output
- perform tool round-trip if requested
- finalize assistant turn record

## 13.12 `runtime_logger.py`
Responsibilities:
- structured logging
- no print statements
- write to file and stream sink

## 13.13 `activity_stream.py`
Responsibilities:
- UI-facing append-only activity events
- simple subscription/observer behavior

## 13.14 `session_store.py`
Responsibilities:
- save/load/delete/branch SQLite session data

---

# 14. Registry-State Fit

This app should use the **lean prototype registry** model rather than a full graph backend.

Recommended tracked records:

- AppNode
- SessionNode
- MessageNode
- ToolRunNode
- SandboxStateNode
- ModelStateNode
- Facet-like records for metadata if desired

But keep implementation registry-based:
- dataclasses
- dictionaries
- sqlite persistence
- typed relations only where helpful

Do not force token graphing or heavy provenance for the chatbot prototype.

---

# 15. Logging and Diagnostics

## 15.1 Logging rule

Use proper structured logging only.
No `print()` debugging in app runtime.

## 15.2 Log destinations

- rolling file log
- activity panel feed
- optional sandbox-local logs if tool actions require them

## 15.3 What should be logged

- app startup/shutdown
- session load/save/new/delete/branch
- model scans
- model request start/finish
- tool route decisions
- CLI command start/finish
- path-guard rejections
- recoverable errors

---

# 16. Session Schema Sketch

## `sessions`
- `session_id`
- `title`
- `parent_session_id`
- `created_at`
- `updated_at`
- `active_model`
- `sandbox_root`

## `messages`
- `message_id`
- `session_id`
- `role`
- `content`
- `created_at`
- `model_name`
- `token_in_est`
- `token_out_est`
- `inference_ms`
- `tool_count`

## `tool_runs`
- `tool_run_id`
- `session_id`
- `message_id`
- `tool_name`
- `command_text`
- `cwd`
- `stdout`
- `stderr`
- `exit_code`
- `started_at`
- `finished_at`

---

# 17. User Flow

## 17.1 First-run flow

1. launch app
2. choose sandbox root
3. choose official toolbox root
4. refresh Ollama models
5. select model
6. start new session
7. chat

## 17.2 Normal prompt flow

1. user types in input box
2. token estimate updates live
3. user submits
4. prompt enters chat history immediately
5. engine builds model request
6. assistant response streams into chat
7. metadata tags settle after completion
8. runtime activity panel logs everything beneath

## 17.3 Tool-use flow

1. model requests CLI action
2. tool router validates request
3. path guard enforces sandbox root
4. command executes
5. stdout/stderr logged to runtime panel
6. tool output fed back into turn
7. assistant completes answer

---

# 18. Recommended Version 1 Milestones

## Phase 1 — Shell
- root app window
- layout panes
- faux controls
- logging backbone

## Phase 2 — Model integration
- Ollama model scan
- model picker
- chat streaming
- response metadata

## Phase 3 — Session persistence
- SQLite schema
- save/load/new/delete/branch
- save-on-close

## Phase 4 — Sandboxed CLI tool
- sandbox root selection
- path guard
- CLI runner
- tool routing
- runtime activity stream

## Phase 5 — Sandbox-local tool scaffolding
- `_tools/` creation in sandbox
- generated script template
- metadata headers

## Phase 6 — Refinement
- token estimate while typing
- right-panel telemetry polish
- faux button panel responsiveness
- cleanup and documentation

---

# 19. Strong Recommendation on Scope

Do **not** let version 1 absorb:
- full graph backend ambitions
- many tools
- autonomous planning trees
- large approval systems
- deep file browsers
- heavy token analytics

The strongest prototype is:

- one chat shell
- one model picker
- one sandboxed tool
- one clean session system
- one visible runtime activity panel

That is enough to create a serious and extensible base.

---

# 20. Final Summary

Build a **lean Tkinter local agent shell** that:

- uses Ollama locally
- chats in a left transcript pane
- shows internal runtime activity in a lower log pane
- uses a right control pane for model selection, status, prompt context, input, and reserved controls
- persists sessions in SQLite
- supports new/save/load/delete/branch session actions
- exposes one real built-in tool: sandboxed CLI execution
- allows future tool growth only inside the selected sandbox
- keeps strict path boundaries and strong logging
- stays registry-minded and strangler-friendly without overcommitting to the full graph backend yet
