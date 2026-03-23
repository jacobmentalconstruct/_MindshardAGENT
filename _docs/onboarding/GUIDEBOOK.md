# MindshardAGENT — System Guidebook

A complete guide to every subsystem in MindshardAGENT. Give this to any agent
or person who needs to understand the application.

**What this app is:** A local desktop chatbot agent shell built with Python/Tkinter
that uses Ollama for inference. It has a sandboxed tool execution system, multi-model
routing, tiered memory, and an extensible MCP tool layer.

**What it runs on:** Windows 10/11, Python 3.10+, Ollama at localhost:11434.
Stdlib-only core (urllib, sqlite3, tkinter). Optional: psutil for resource monitoring.

---

## 1. Composition Tree

```
app.py (composition root — wiring and app state only)
  |
  +-- Engine (src/core/engine.py)
  |     Runtime coordinator. Owns all backend subsystems.
  |     |
  |     +-- SandboxManager
  |     |     PathGuard (path containment)
  |     |     CLIRunner (command execution)
  |     |     AuditLog (operation logging)
  |     |
  |     +-- FileWriter (atomic file read/write)
  |     +-- PythonRunner (disposable Python execution under .mindshard/runs/)
  |     |
  |     +-- ToolCatalog (3 builtins + sandbox-discovered tools)
  |     +-- ToolRouter (parse tool_call blocks, dispatch to handlers)
  |     |
  |     +-- ResponseLoop (streaming + tool round-trips)
  |     |     Planner stage (optional, uses planner model)
  |     |     Context gatherer (workspace scan, no model)
  |     |     Probe stage (micro-questions via fast probe model)
  |     |     Budget guard (token budget enforcement)
  |     |     STM window (sliding window of recent turns)
  |     |     Evidence bag adapter (falloff ingestion + summary)
  |     |     Two-pass retrieval (uncertainty -> deeper evidence)
  |     |
  |     +-- LoopManager
  |     |     ResponseLoop (default — full tool agent)
  |     |     DirectChatLoop (no tools, just chat)
  |     |     PlannerOnlyLoop (planner without execution)
  |     |     ThoughtChainLoop (self-talk spirals)
  |     |
  |     +-- KnowledgeStore (session-scoped RAG, SQLite + all-minilm embeddings)
  |     +-- EvidenceBagAdapter (manifold NodeStore for fallen-off STM turns)
  |     +-- TokenizerAdapter (adaptive per-model chars/token learning)
  |     +-- OllamaClient (chat streaming + embeddings)
  |     +-- MindshardVCS (local git repo in .mindshard/vcs/)
  |     +-- ActionJournal (structured event log for agent orientation)
  |
  +-- StateRegistry (in-memory graph-semantic registry)
  +-- SessionStore (SQLite session persistence)
  +-- ActivityStream (runtime event feed -> UI)
  +-- EventBus (internal pub/sub)
  |
  +-- MainWindow (src/ui/gui_main.py)
        ChatPane (scrollable transcript with streaming resize)
        ActivityLogPane (runtime terminal showing engine events)
        CLIPane (direct sandbox CLI access)
        ControlPane (model picker, sessions, resources, input, buttons)
          SessionPanel, SandboxPanel, WatchPanel, DockerPanel
          ResourceMonitor (CPU/RAM/GPU polling)
```

---

## 2. Multi-Model Routing

The app has 7 model role slots. Each can be a different Ollama model:

| Role | Default | Purpose |
|------|---------|---------|
| PRIMARY_CHAT | (user selected) | Main conversation model |
| PLANNER | (falls back to primary) | Execution planning before turns |
| RECOVERY_PLANNER | (falls back to planner) | Replanning after failures |
| CODING | (falls back to primary) | Code generation tasks |
| REVIEW | (falls back to primary) | Code review tasks |
| FAST_PROBE | qwen2.5:1.5b | Micro-questions (intent, relevance, language) |
| EMBEDDING | all-minilm:latest | RAG embeddings (384-dim vectors) |

Individual probe tasks (intent, relevance, language, summary) can each use a
different model via `probe_models` config dict.

Models are validated before promotion using the `validate_model_slot` MCP tool
with role-specific eval fixtures in `jobs/role_evals/`.

---

## 3. Tiered Memory Architecture

### STM Sliding Window
- Last N turns (default 10) kept verbatim in the prompt
- Provides temporal/causal coherence — what the model *thinks with*
- Config: `stm_window_size`

### Evidence Bag (Falloff Destination)
- Turns that fall off the window are ingested into a manifold NodeStore
- Full text is NEVER deleted — only the view changes
- A compact summary (~128 tokens) is injected into the prompt every turn
- The model knows it can request specifics
- Config: `evidence_bag_enabled`, `evidence_bag_summary_budget`

### Two-Pass Retrieval
- After the model responds, heuristic checks for uncertainty markers
- If detected, deeper evidence (512 token budget) is retrieved from the bag
- Model re-generates with the additional context
- Config: `evidence_bag_retrieval_budget`

### RAG Knowledge Store
- Session-scoped SQLite with 384-dim embeddings (all-minilm via Ollama)
- Every turn is embedded after the exchange
- Retrieved by cosine similarity when relevant to current query
- Injected into system prompt as RAG context

**Critical design principle:** The evidence bag is a SUPPLEMENT to STM, never a
replacement. Without temporal flow, models produce disconnected snippets. The
window is the story; the bag is the footnotes.

### Token Budget Guard
- Before inference, all prompt components are registered with trim priorities
- If total exceeds `max_context_tokens * 0.85`, components are trimmed in order:
  RAG context (6) -> bag summary (5) -> stage context (4) -> STM window (3) -> planner (2)
- System prompt (priority 0) is never trimmed
- Logs whether multi-pass would have been beneficial (>30% trimmed)
- Source: `src/core/agent/context_budget.py`

---

## 4. Per-Turn Pipeline

When the user sends a message, this sequence runs:

```
1. PLANNER (optional)
   Uses planner model to generate execution guidance
   Output: plan text injected as system message

2. CONTEXT GATHERER (no model)
   Scans workspace for file tree, key files, project metadata
   Output: stage context injected as system message

3. PROBE STAGE (optional, fast probe model)
   Runs micro-questions: intent classification, file relevance, language detection
   Output: probe results merged into stage context

4. STM WINDOW + EVIDENCE BAG
   Compute sliding window (last N turns)
   Ingest falloff turns into evidence bag
   Build compact bag summary

5. BUDGET GUARD
   Register all components with trim priorities
   If over budget, trim lowest-priority components first
   Log budget report

6. MESSAGE ASSEMBLY
   System prompt + planner + stage context + bag summary + STM window + user message

7. MODEL INFERENCE (streaming)
   Stream tokens from Ollama to UI in real-time

8. TOOL LOOP (up to max_tool_rounds)
   If model emits ```tool_call blocks:
   Parse -> validate -> execute -> format result -> append to messages -> loop

9. TWO-PASS CHECK
   If model response has uncertainty markers AND bag has content:
   Retrieve deeper evidence -> re-generate once

10. RAG STORAGE
    Embed user query + assistant response into knowledge store

11. RESULT DELIVERY
    Final response + metadata (model, tokens, timing, budget report) -> UI
```

---

## 5. Tool System

### Built-in Tools
| Tool | Purpose |
|------|---------|
| `cli_in_sandbox` | Execute shell commands within sandbox boundary |
| `write_file` | Atomic file creation/overwrite (JSON-escaped content) |
| `read_file` | Read file contents with size limit |
| `list_files` | Directory listing |
| `run_python_file` | Execute Python in disposable workspace |

### Tool Call Format
Model emits tool calls as JSON inside triple-backtick `tool_call` fences.
ToolRouter parses, validates, dispatches, and formats results.

### Sandbox-Local Tools
Discovered at startup from `_sandbox/_tools/`. Each tool has a `tool.json` manifest.

### Security Layers
1. CommandPolicy: 36 allowlisted commands, pattern escape detection
2. PathGuard: all paths must resolve within sandbox root
3. Extension blocklist: blocks .exe, .bat, .cmd, .ps1, etc.
4. Size limits: 512KB write, 1MB read
5. User confirmation for destructive ops (del, rm, rmdir)
6. Audit log: every operation recorded to audit.jsonl

---

## 6. MCP Tool Layer

Three MCP servers expose development tools to external agents (Claude Desktop, etc.):

### mindshard (.dev-tools/mcp_server.py)
Agent introspection tools: preview_prompt, get_status, run_cli, list_tools, etc.

### ollama-prompt-lab (.dev-tools/drop-bin/_ollama-prompt-lab/)
Model evaluation: run prompts against models, compare results, validate model slots
with role-specific fixtures.

### manifold-mcp (.dev-tools/drop-bin/_manifold-mcp/)
Evidence bag operations: ingest text, query corpus, extract evidence, inspect bag
contents (bag_inspect tool).

---

## 7. Session Management

- Sessions stored in SQLite at `.mindshard/sessions/sessions.db`
- Each session has: ID, name, chat history, metadata, creation/update timestamps
- Session operations: new, select, rename, delete, branch
- Auto-save on close, autosave debounce after turn completion
- Session-scoped RAG (knowledge store entries are per-session)

---

## 8. Project Structure

### Source Layout
```
src/
  app.py                    Composition root
  app_commands.py           UI callback handlers
  app_docker.py             Docker lifecycle callbacks
  app_prompt.py             Prompt inspection callbacks
  app_session.py            Session management callbacks
  app_state.py              AppState dataclass
  app_streaming.py          Submit/streaming callbacks
  core/
    agent/                  Response loop, prompt builder, planner, probes, tool routing
    config/                 AppConfig (JSON-persisted)
    engine.py               Runtime coordinator
    ollama/                 Chat client, embeddings, model scanner, tokenizer
    project/                Project metadata, syncer
    registry/               In-memory state registry
    runtime/                Logger, event bus, activity stream, resource monitor, action journal
    sandbox/                Sandbox manager, path guard, CLI runner, file writer, tool catalog
    sessions/               Session store, knowledge store, evidence adapter
    utils/                  IDs, clock, text metrics
    vault/                  Memory vault (cross-project index)
    vcs/                    Local git VCS
  ui/
    gui_main.py             MainWindow
    theme.py                Visual theme
    panes/                  ChatPane, ActivityLogPane, CLIPane, ControlPane
    widgets/                Reusable UI components
    dialogs/                Settings, project brief, prompt overrides
```

### Data Layout
```
.mindshard/                 Sidecar directory (per-project)
  sessions/                 Session DB + evidence bag storage
  vcs/                      Local git repo
  logs/                     Audit log
  tools/                    Sandbox-local tool storage
  state/                    Project metadata, prompt overrides
  runs/                     Disposable Python execution workspace
  outputs/                  Agent output files
  parts/                    Referenced parts
  ref/                      Reference materials

.dev-tools/                 Development tooling
  mcp_server.py             Mindshard MCP server
  drop-bin/                 Experimental tool suites
    _manifold-mcp/          Evidence bag / manifold store
    _ollama-prompt-lab/     Model evaluation lab

_docs/                      Documentation
  agent_prompt/             Agent identity/behavior prompt files (numbered, sorted)
  onboarding/               Session onboarding docs (this folder)

_sandbox/                   Execution sandbox
  project/                  Agent's working copy (sync-back to real source)
```

---

## 9. Configuration

All settings live in `app_config.json` (gitignored). Key fields:

| Category | Fields |
|----------|--------|
| Models | `primary_chat_model`, `planner_model`, `fast_probe_model`, etc. |
| Context | `max_context_tokens` (8192), `temperature` (0.7) |
| RAG | `rag_enabled`, `rag_top_k` (5), `rag_min_score` (0.3) |
| Memory | `stm_window_size` (10), `evidence_bag_enabled`, `evidence_bag_summary_budget` |
| Budget | `budget_reserve_ratio` (0.15), `multipass_enabled` (False) |
| Tools | `max_tool_rounds` (12), `planning_enabled`, `probe_enabled` |
| Docker | `docker_enabled`, `docker_memory_limit`, `docker_cpu_limit` |

---

## 10. Domain Boundaries (Builder Contract)

The app follows strict layering from the builder constraint contract:

| Layer | Scope | Example |
|-------|-------|---------|
| app.py | Wiring + state management ONLY | Creates Engine, wires callbacks |
| Orchestrators | Bounded to UI or CORE side | Engine (core), MainWindow (UI) |
| Managers | Bridge max 2-3 domains | SandboxManager, ToolRouter |
| Components | Single domain only | PathGuard, FileWriter, OllamaClient |

**Current violations (known, pending cleanup):**
- response_loop.py bridges 8 domains (planned split in Phase 1.1)
- app_commands.py dispatches across 6+ domains (planned slim in Phase 1.3)
- engine.py directly mutates response_loop private state (planned fix in Phase 1.2)

---

## 11. Key Design Principles

1. **Stdlib-first**: No heavy dependencies. urllib, sqlite3, tkinter only.
2. **Sandbox boundary**: All execution path-guarded within sandbox root.
3. **Evidence bag is supplement, not replacement**: Without STM temporal flow,
   models produce snippets not scripts. Window = story, bag = footnotes.
4. **Small model steering**: Repetition, decision tables, anti-patterns with
   strikethrough, few-shot examples. Polite suggestions don't work.
5. **Reversible storage**: Evidence bag never deletes — falloff is a view filter,
   not data destruction. Raise the budget or change the query, content resurfaces.
6. **Model slot validation**: Every role is a swappable slot. Candidates must pass
   eval fixtures before promotion. No model goes live untested.
