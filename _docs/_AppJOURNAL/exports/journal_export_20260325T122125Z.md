# App Journal Export

## Devlog — Agent Tool Testing, MCP Wiring, Malformed Tool Call Fix
- entry_uid: `journal_cd0431953451`
- kind: `devlog`
- source: `agent`
- status: `closed`
- updated_at: `2026-03-24T16:05:19Z`
- tags: `bug-fix, tool-router, mcp, testing, agent-loop`

## Session Summary — Mar 24 2026

### Context
Continued from prior session. All TODO items were complete. Session opened with orientation on current functional state of MindshardAGENT, followed by architectural discussion on the Living Graph and 4th-vertex FFN routing concept.

---

### 4th Vertex / Neural Dock (External)
A parallel builder (BDNeuralTranslationSUITE) implemented a Universal Neural Dock on the hypernode emitter. Each emitted node now carries `verbatim`, `structural`, `vector`, and a new `neural_dock` object with a bootstrap FFNN routing profile: `primary_route`, `route_confidence`, `route_scores`, `hidden_state`, `active_layers`, and the feature vector. The SQLite scribe persists the dock. Verification passed.

This is external tooling working toward an MCP layer. MindshardAGENT already speaks MCP (NDJSON, 3 servers). When the neural translation suite's MCP layer stabilises, it registers as another server — no changes needed on this side until then.

Integration seam to watch: `src/core/sessions/evidence_adapter.py` — if manifold SDK starts ingesting nodes with `neural_dock` data, the adapter will need to either pass it through or expose it.

---

### Bug Found and Fixed — Malformed Tool Call Silent Failure

**Symptom:** User tested the agent on a real project scaffold task. The agent planned correctly, then produced `TOOL_CALLS: malformed_tool_call, malformed_tool_call` in its response transcript, but then *claimed the files were created* and the project folder remained empty.

**Root cause chain:**
1. Model emitted ` ```tool_call ` blocks with invalid JSON
2. `tool_router.extract_tool_calls()` failed to parse → silently dropped the call, returned empty list
3. `has_tool_calls()` still returned `True` (regex matched the block wrapper)
4. `execute_all([])` returned `[]`
5. `format_all_results([])` returned `""` — empty string
6. Pipeline sent `[Tool Results]\n` with nothing after it to the model
7. Model received blank result → assumed success → hallucinated file creation

**Fix — `src/core/agent/tool_router.py`:**
- `extract_tool_calls()` now returns a sentinel dict `{"tool": "__malformed__", "_raw": ..., "_error": ...}` instead of silently dropping bad calls
- `execute()` detects the `__malformed__` sentinel and returns an explicit error result with a message telling the model exactly what went wrong and how to fix it: *"Your tool call could not be parsed (invalid JSON). Ensure the tool call block contains only valid JSON..."*
- This error now flows through `format_all_results()` → `format_tool_result()` → back to the model as `[Tool 'tool_call' failed: ...]`
- Recovery planner can now also detect these as error rounds and trigger replanning

**Fix — `_docs/agent_prompt/50_tool_usage_preferences.md`:**
- Added explicit section on `write_file` directory creation: no mkdir needed, parent dirs are auto-created by writing any file at a nested path
- Added tool call format rules: valid JSON only, fix and retry on parse error, check results before narrating success

---

### MCP / Sandbox Sync Issue Discovered

**Symptom:** MCP status reported `sandbox_root: _TestApp` even after UI was switched to `_FirsthomeCALC`. `history_turns: 0` after submit attempt. Submit timed out (300s). Top bar showed `model: (none)`.

**Findings:**
- MCP server state does not sync with UI engine state after sandbox changes — they may be separate instances or MCP status is cached at connection time
- `mindshard_run_cli` blocks absolute Windows paths by design (correct security behaviour)
- `history_turns: 0` after submit = request never registered, likely because no model was selected in the session

**Root cause of submit failure:** Model picker showed `(none)` in the session — without a model, the engine has nothing to call and the request hangs until timeout.

**Resolution needed:**
- User must select a model in the Session tab before submitting; top bar must show a model name (not `(none)`) to confirm
- MCP ↔ UI sandbox sync gap should be investigated — either MCP reads live engine state or there needs to be a refresh mechanism

**Action taken:** Stopped, cleaned up 2 files written prematurely (engine.py, ui.py). Folder restored to empty. Waiting for model selection confirmation before retesting agent build.

---

### Next Steps
1. Confirm model selection works (top bar shows model name, not `(none)`)
2. Resubmit calculator build request via MCP to `_FirsthomeCALC`
3. Investigate MCP status stale-read on sandbox_root
4. Consider adding a `mindshard_set_sandbox` MCP tool or a status refresh endpoint

## Session 6 Work Log — North Star + TODO Completion Pass
- entry_uid: `journal_bef773c7e9fe`
- kind: `log`
- source: `agent`
- status: `open`
- updated_at: `2026-03-24T01:38:53Z`
- tags: `session-log, todo, cis-staleness, diagnostic-lab, evidence-bag, diff`

## Work Completed This Session

### North Star Recorded (journal entry 18)
Living Graph as Main Brain for 4-9B models — full technical blueprint persisted as
importance=5 vision entry. Graph = persistent typed cognition; model = bounded operator
on subgraphs. Preconditions (domain boundaries 1B/1C, manifold store, evidence bag) now
satisfied. Next steps documented.

### TODO.md — Phase 2 Bag Items Marked Complete
Bag manifest, structural layer (inspect/focus), and bag_navigate MCP tool were completed
last session but TODO still showed them open. Closed.

### CIS Staleness Handling (turn_pipeline.py + knowledge_store.py)
**Problem:** Evidence bag summary injected into every prompt was also useful in RAG,
but as the bag grows each new summary makes old ones stale. No invalidation existed.

**Fix (3 files):**
- `knowledge_store.py` — added `delete_by_source(session_id, source) -> int`
- `turn_pipeline._store_rag()` — now accepts `bag_summary: str` param; before embedding
  new bag summary, calls `knowledge.delete_by_source(sid, "evidence_bag")` to purge stale
  CIS chunks. Then embeds with `source="evidence_bag"`, `source_role="system"`.
- `turn_pipeline.run()` — passes `bag_summary=assembled.bag_summary` to `_store_rag()`

**Also fixed:** `evidence_adapter.py` had stale path pointing to `drop-bin/_manifold-mcp`;
updated to `.dev-tools/_manifold-mcp` (the promoted location from session 5).

### Diagnostic Lab — Loop Mode + Model Role Exposure (3 files)
- `benchmark_runner.py` — suite metadata now includes: `loop_mode_counts`,
  `loop_mode_avg_scores`, `chat_models_used`, `planner_models_used`,
  `cases_with_planning`, `cases_budget_trimmed`
- `services.py` — engine probe now snapshots model role assignments
  (`chat_model`, `planner_model`, `fast_probe_model`, `coding_model`, `review_model`)
  from the probe config and spreads them into probe metadata alongside `**result_meta`
- `view.py` — `_format_benchmark_cases()` now shows per-case: loop_mode, models used,
  planning_used, probes_run, STM window, budget status (with TRIMMED flag)
- `reporting.py` — benchmark markdown now includes Loop Mode Breakdown section and
  Model Roles Used section above case list; per-case adds loop_mode, planner_model,
  planning_used, probes_run, budget

### Prompt Version Diff Feature (4 files)
Added end-to-end git diff between two prompt version snapshots.

- `prompt_tuning_store.py` — `diff_prompt_versions(left_id, right_id)` runs
  `git diff --stat` + `git diff` between the two commits; returns structured dict with
  both sides' metadata and the combined diff text
- `services.py` — `diff_prompt_versions()` delegation
- `view.py` — new "Diff Prompt Versions" UI row in Last Probe section; two version ID
  entry fields + "Diff" button; `get_history_inputs()` returns two new keys;
  `diff_versions_btn` in set_busy list
- `controller.py` — `diff_prompt_versions()` action; `"history_diff"` drain handler;
  `_format_version_diff()` formatter showing left/right metadata + unified diff output

## Compile Status
All 9 modified files pass `python -m py_compile` with zero errors.

## Open TODO Items (Remaining)
- Trigger recovery replanning after repeated failure patterns
- Add user-visible loop mode controls / overrides
- Design graph-based thought-chain loop (deferred — north star territory)
- Per-session command policy customization
- Dark theme + DPI scaling
- Keyboard shortcuts (beyond Ctrl+Enter)
- UI evidence bag explorer tab
- App-wide highlight→ask context menu
- Dev tools → agent tools pipeline (design only)
- Multi-pass prompt splitter (Phase 3 — data-gated)
- Loop family expansion (recovery, benchmark, review, model-chain loops)
- Official toolbox root configuration

## North Star: Living Graph as the Main Brain for 4-9B Models
- entry_uid: `journal_c8956949854f`
- kind: `vision`
- source: `agent`
- status: `open`
- updated_at: `2026-03-24T01:28:02Z`
- tags: `north-star, architecture, living-graph, intelligence-decomposition, 4-9b, manifold`

## The Core Insight

4-9B models are **capable local operators but poor global thinkers**. They can reason well over a bounded subgraph. They cannot hold large global context or multi-step plans in their activation window. The solution is not a bigger model — it's a smarter substrate.

**The inversion:** Don't use the model as the brain with a graph as memory. Use the **graph as the brain** — persistent structured cognition — and the model as a **bounded fast operator** on subgraphs.

---

## What This Means in Practice

```
TRADITIONAL:
  Model (holds everything) → outputs

LIVING GRAPH:
  Graph (persistent typed cognition) ← model operates on subgraph → writes back
  ↑                                                                        ↓
  [Task nodes] [Hypothesis nodes] [Decision nodes] [Evidence nodes] ←────┘
```

### Node Types (Typed Graph)
- **Task nodes** — what needs to be done; linked to subtasks, blocked-by, depends-on
- **Hypothesis nodes** — candidate explanations; scored, updated as evidence arrives
- **Decision nodes** — committed choices with rationale and alternatives considered
- **Evidence nodes** — facts, spans, retrieved chunks (already: manifold store)
- **Plan nodes** — structured execution plans (already: execution planner)

### The Model's Role
- Given a **subgraph** (focused context, not the whole graph) → do one bounded operation
- Operations: classify, score, expand, resolve, generate, critique
- Write result **back to the graph** as new nodes or edge updates
- Many small passes ∝ one giant pass

### The Navigation Policy
- An outer loop decides **which subgraph** to hand to the model next
- Uses edge weights, node states (open/pending/resolved), and a goal anchor
- This is the "attention" layer — but implemented as graph traversal, not softmax

---

## What's Already Built (Partial Implementations)

| Component | What It Is | Missing Piece |
|-----------|-----------|---------------|
| Manifold store | Hypergraph (nodes, edges, evidence spans) | Write-back protocol from model output |
| Evidence bag | Query-driven retrieval from graph | Task/hypothesis/decision node types |
| Execution planner | Plan nodes, subtask decomposition | Persistence to graph; step status updates |
| Probe stage | Bounded model pass before main turn | Hook to write probe result back to graph |
| STM window | Recent causal thread | Needs linking to graph nodes |

---

## What's Missing

1. **Task/Goal/Hypothesis node types** in manifold schema — extend `build_corpus_bundle` node kinds
2. **Write-back protocol** — model output → parse → create/update graph nodes
3. **Navigation policy** — subgraph selector: given current graph state + goal, pick next subgraph
4. **Multi-pass coordinator** — outer loop calling model N times on N subgraphs, accumulating graph writes
5. **Graph-grounded prompt builder** — instead of text assembly, build prompt from typed node selection

---

## Why This Works for 4-9B Models

- Each model call sees a **small, coherent, typed subgraph** → fits in context
- The model doesn't need to remember the whole session — the graph does
- Progress accumulates in the graph between turns, not in the model's "memory"
- Any model that can do a bounded text operation can participate (including quantized 4-9B)
- The graph can be **inspected, edited, and debugged** — unlike activation state

---

## Preconditions (Now Satisfied)

- Clean domain boundaries (1B/1C complete) — each component callable without system-wide knowledge
- Manifold store + evidence bag — graph substrate exists
- Structural layer (`inspect()`, `focus()`) — graph is navigable
- Self-discoverable bag manifest — components can describe themselves to agents

---

## Next Steps (When TODO List Is Done)

1. Extend manifold node schema with Task/Hypothesis/Decision types
2. Build `GraphOperator` — thin wrapper: given a subgraph + operation type → model call → parsed result
3. Build navigation policy (start simple: BFS on open nodes, goal-anchored scoring)
4. Wire write-back: parsed model output creates new nodes in the graph
5. Replace the current single-pass `TurnPipeline` with a multi-pass graph loop for complex tasks

---

## The Vision

A 7B model that can hold 30 sequential reasoning steps because each step is one bounded graph operation, with the graph accumulating the work. The model is fast, cheap, and local. The graph is the intelligence.

"We won't get a 300B...nor a 70B...so how do we do it with 4-9B is what I gotta figure out. I think we need a living graph instead of a model as the main brain."

## Domain Boundary Audit — Session 5 Results (After 1C)
- entry_uid: `journal_b2c22d9681ea`
- kind: `audit`
- source: `agent`
- status: `open`
- updated_at: `2026-03-24T00:54:51Z`
- tags: `domain-audit, refactoring, session-5`

Domain boundary audit run after Phase 1B facade gap fill + Phase 1C completion.
Tool: .dev-tools/final-tools/tools/domain_boundary_audit.py
Thresholds: component_max=1, manager_max=3

SUMMARY
  Files scanned:        127  (was 116 at baseline, +11 new files created)
  Over threshold:        25
  Functions over:        68
  Deep access:          361  (was 442 at baseline)
  Total violations:     454  (was 565 at baseline, -111 = -19.6%)

PROGRESS BY PASS
  Baseline (session 4):      565 violations  116 files
  After 1B hotspot passes:   543 violations  124 files
  After 1B facade gap fill:  462 violations  124 files
  After 1C:                  454 violations  127 files

TOP OFFENDERS (after 1C)
  8 domains  engine.py          [agent, config, ollama, project, runtime, sandbox, sessions, vcs]
  8 domains  control_pane.py    [agent, config, project, ui, ui.chat_pane, ui.input_pane, ui.model_picker, ui.vcs_panel]
  7 domains  app.py             [agent, config, engine, runtime, sandbox, sessions, ui]
  7 domains  app_commands.py    [agent, config, ollama, project, runtime, sandbox, ui]
  6 domains  app_state.py       [agent, config, engine, runtime, sessions, ui]
  6 domains  turn_pipeline.py   [agent, config, ollama, runtime, sandbox, sessions]
  6 domains  ui_facade.py       [ui, ui.chat_pane, ui.control_pane, ui.input_pane, ui.model_picker, ui.vcs_panel]
  5 domains  evidence_pass.py   [agent, config, ollama, runtime, sessions]
  5 domains  execution_planner.py [agent, config, ollama, runtime, sandbox]
  5 domains  response_loop.py   [agent, config, runtime, sandbox, sessions]

NOTES
  - turn_pipeline.py at 6 domains is expected and accepted: it IS the stage
    algorithm that must touch all layers. Single-responsibility CORE orchestrator.
  - ui_facade.py at 6 domains is expected and accepted: it is the intentional
    aggregation point for all UI intent operations. Its "domains" are all UI sub-modules.
  - engine.py import-level count unchanged at 8 (orchestrator holds references to
    all subsystems) but absorbed inline logic is gone from set_sandbox().
  - response_loop.py dropped from 6 → 5 domains (ollama removed).
  - control_pane.py (8 domains, 1534 lines) is the next major target — deferred
    widget surgery sprint (Phase 4 in roadmap).

NEW FILES CREATED THIS SESSION (all compile-clean)
  src/ui/panes/chat_pane.py         — streaming protocol added
  src/ui/ui_facade.py               — 12 new intent-level methods
  src/app_streaming.py              — full rewrite, zero direct widget access
  src/app_docker.py                 — facade delegation for docker panel
  src/core/sandbox/sandbox_runtime_factory.py  — NEW owner of backend selection
  src/core/ollama/embedding_service.py         — NEW owner of embed availability
  src/core/agent/turn_pipeline.py              — NEW owner of stage sequencing
  src/core/agent/response_loop.py             — stripped to threading wrapper

## Session 5 Work Log — 1B Facade Gap Fill + Phase 1C
- entry_uid: `journal_e652cb8557d3`
- kind: `log`
- source: `agent`
- status: `open`
- updated_at: `2026-03-24T00:54:15Z`
- tags: `session-5, devlog, progress, refactoring, phase-1b, phase-1c`

Session 5 (2026-03-23) — architectural boundary repair continuation.

═══ PHASE 1B — Facade Gap Fill ═══

Problem: audit still showed ui.chat_pane and ui.control_pane as direct domain
touches in app_streaming.py, app_docker.py, and project_command_handler.py.
_run_turn_sync was grabbing chat_pane._inner.winfo_children()[-1] and directly
manipulating _canvas scroll regions — deep internal access.

Changes:
1. chat_pane.py — added streaming protocol (begin_stream, update_stream, end_stream)
   ChatPane now OWNS the streaming card lifecycle. Callers never touch _stream_card,
   _inner, or _canvas directly. Card created, updated, and finalized through the protocol.

2. ui_facade.py — added 12 new intent-level methods:
   - post_user_message(text) — add user message + scroll
   - begin_chat_stream() / update_chat_stream(content) / end_chat_stream(content)
   - set_last_prompt(text) / set_last_response(content)
   - set_docker_status(status, docker_available, image_exists)
   - set_docker_enabled(enabled)
   All named in caller vocabulary, never widget-path mirrors.

3. app_streaming.py — full rewrite, zero direct widget access remaining.
   No more stream_card closure, no more _canvas.configure() calls.
   All chat + control interactions go through s.ui_facade.

4. app_docker.py — do_docker_probe() now uses s.ui_facade.set_docker_status()
   and s.ui_facade.set_docker_enabled() instead of control_pane.docker_panel.*

Audit after gap fill: 462 violations (was 502 after main 1B, 565 baseline).

═══ PHASE 1C — engine.py ═══

Issue A: set_sandbox() had 35-line if/else for Docker vs local backend selection.
Absorbed implementation — sandbox domain should own "which backend do I use."
Fix: extracted build_sandbox_runtime() → src/core/sandbox/sandbox_runtime_factory.py
  Returns SandboxRuntime(cli_runner, docker_runner, python_runner, command_policy)
  engine.set_sandbox() calls factory, stores result, shrinks to coordinator.

Issue B: set_evidence_bag() was writing response_loop._evidence_bag directly.
Fix: added set_evidence_bag() to ResponseLoop public API.

Issue C: _embed() and check_embeddings() had ollama logic embedded in engine.
Fix: extracted EmbeddingService → src/core/ollama/embedding_service.py
  Owns: check_embedding_model call, availability state, embed_text wrapping.
  engine.check_embeddings() becomes self.embedding_service.check().
  engine._embed() deleted; passes self.embedding_service.embed as callable.

New files: sandbox_runtime_factory.py (~75 lines), embedding_service.py (~65 lines)

═══ PHASE 1C — response_loop.py ═══

Issue: _run_turn_sync() was a 217-line mega-method owning full stage sequencing.
ResponseLoop was simultaneously: threading wrapper AND pipeline executor.

Fix: extracted TurnPipeline → src/core/agent/turn_pipeline.py (~270 lines)
  Owns: planner → context gather → probe → turn assembly → streaming+tool loop
        → evidence pass → RAG storage → metadata build → on_complete
  Also owns: _build_rag_context, _build_journal_context, _build_vcs_context helpers
             build_prompt() (formerly preview_prompt internals)
  Stateless per-turn: constructed fresh by ResponseLoop._make_pipeline()
  should_stop passed as lambda: self._stop_requested — no back-reference

ResponseLoop after extraction (~130 lines):
  Owns: threading (run_turn spawns worker), stop flag, workspace/RAG state
  _make_pipeline() constructs TurnPipeline with current state snapshot
  preview_prompt() delegates to _make_pipeline().build_prompt()
  ollama domain removed (chat_stream moved to TurnPipeline)
  Drops from 6 domains to 5.

═══ AUDIT DELTA ═══
Baseline (session 4 end):  565 violations  116 files
After 1B main passes:      543 violations  124 files
After 1B facade gap fill:  462 violations  124 files
After 1C:                  454 violations  127 files  (-111 total, -19.6%)

response_loop.py: 6 domains → 5 (ollama removed)
turn_pipeline.py: 6 domains (expected — it IS the stage algorithm)
engine.py: domain count stays 8 on imports (orchestrator) but set_sandbox()
  function-level violations eliminated (factory delegates the absorbed logic)

## Session 4 Work Log
- entry_uid: `journal_211f4e08ebe9`
- kind: `log`
- source: `agent`
- status: `active`
- updated_at: `2026-03-23T22:35:22Z`
- tags: `session-4, devlog, progress`

Session 4 (2026-03-23) completed:

1. Fixed 3 MCP servers (ollama-prompt-lab, manifold-mcp, app-journal) — Content-Length→NDJSON protocol fix
2. Phase 1.1: Split response_loop.py (589→471 lines) into turn_assembler.py (163) + evidence_pass.py (121)
3. Phase 1.2: Added set_workspace() to ResponseLoop, engine.py uses setter instead of private field access
4. Phase 1.4: Gated 55_self_architecture.md behind self_awareness_enabled config flag
5. Set qwen3.5:9b as default planner model (validated at 93.3%)
6. Built domain_boundary_audit tool in final-tools (AST-based, MCP-registered)
7. Ran full domain audit — 116 files, 565 violations identified
8. Installed app-journal into MindshardAGENT project
9. Ingested all _docs into journal DB (13 entries)

## Domain Boundary Audit — Session 4 Results
- entry_uid: `journal_1330fa175bd9`
- kind: `audit`
- source: `agent`
- status: `active`
- updated_at: `2026-03-23T22:35:14Z`
- tags: `domain-audit, refactoring, session-4`

Ran AST-based domain_boundary_audit tool on src/. 116 files scanned, 565 violations.

Top offenders:
- app_commands.py: 13 domains (worst — touches agent, config, ollama, project, runtime, sandbox, sessions, ui + 5 sub-ui domains)
- app.py: 11 domains (reaches into deep UI hierarchy)
- engine.py: 8 domains (expected high as orchestrator but still too many)
- control_pane.py: 7 domains (1534 lines, needs decomposition)
- app_session.py: 6 domains
- app_state.py: 6 domains
- response_loop.py: 6 domains (down from 8 after turn_assembler + evidence_pass extraction)

Builder contract thresholds: component_max=1, manager_max=3, depth_warn=3.
74 functions exceed component threshold. 19 files exceed manager threshold. 472 deep access violations.

## System Guidebook
- entry_uid: `journal_d112971b620e`
- kind: `guide`
- source: `agent`
- status: `active`
- updated_at: `2026-03-23T22:35:01Z`
- tags: `reference, subsystems, comprehensive`

Complete system reference guide explaining every subsystem and component in MindshardAGENT.

## Next Session Guide
- entry_uid: `journal_23ef3dbc0feb`
- kind: `guide`
- source: `agent`
- status: `active`
- updated_at: `2026-03-23T22:34:59Z`
- tags: `onboarding, next-steps`

Session start guide listing immediate actions and the highest-impact work to do first.

## Roadmap
- entry_uid: `journal_9c8459f9f482`
- kind: `planning`
- source: `agent`
- status: `active`
- updated_at: `2026-03-23T22:34:57Z`
- tags: `roadmap, planning, phases`

Current phase plan and next-steps roadmap with architectural cleanup priorities.

## Onboarding README
- entry_uid: `journal_c7a299bd70a1`
- kind: `guide`
- source: `agent`
- status: `active`
- updated_at: `2026-03-23T22:34:55Z`
- tags: `onboarding, index`

Index explaining the session-specific onboarding workflow and document structure for new agents.

## TODO List
- entry_uid: `journal_4ee1f592eeec`
- kind: `todo`
- source: `agent`
- status: `active`
- updated_at: `2026-03-23T22:34:52Z`
- tags: `todo, backlog, priorities`

High-priority and in-progress task list with checkmarks and feature backlog items.

## Dev Log
- entry_uid: `journal_4570627c94a0`
- kind: `log`
- source: `agent`
- status: `active`
- updated_at: `2026-03-23T22:34:50Z`
- tags: `devlog, history, sessions`

Append-only execution ledger documenting session builds, file creation, and implementation progress across all sessions.

## Tkinter UI Tree
- entry_uid: `journal_f08d299247c3`
- kind: `specification`
- source: `agent`
- status: `active`
- updated_at: `2026-03-23T22:34:47Z`
- tags: `ui, tkinter, layout`

Layout tree and implementation status of the redesigned workstation UI panes and sashes.

## Engineering Notes
- entry_uid: `journal_a39cc491cbb6`
- kind: `note`
- source: `agent`
- status: `active`
- updated_at: `2026-03-23T22:34:44Z`
- tags: `engineering, lessons-learned, prompt-engineering`

Hard-won design lessons and gotchas, especially around small model prompt engineering patterns.

## Prototype Registry State Graph
- entry_uid: `journal_1b72b00889db`
- kind: `specification`
- source: `agent`
- status: `active`
- updated_at: `2026-03-23T22:34:41Z`
- tags: `state, graph, registry`

Lightweight registry-with-graph-semantics for preserving app state identity and relations.

## Sandboxed Chatbot Agent Blueprint
- entry_uid: `journal_63438cc6cc91`
- kind: `specification`
- source: `agent`
- status: `active`
- updated_at: `2026-03-23T22:34:38Z`
- tags: `blueprint, founding-doc`

Original specification for a lean local chatbot agent with sandboxed CLI tool execution capability. The founding design doc.

## Agent Contract
- entry_uid: `journal_7aa84c9fc2cf`
- kind: `specification`
- source: `agent`
- status: `active`
- updated_at: `2026-03-23T22:34:35Z`
- tags: `agent, contract, behavior`

Operational behavior contract defining agent tool discipline, task execution patterns, and constraint boundaries.

## Architecture Overview
- entry_uid: `journal_da1be1a40c58`
- kind: `specification`
- source: `agent`
- status: `active`
- updated_at: `2026-03-23T22:34:32Z`
- tags: `architecture, system-design`

System architecture of MindshardAGENT's Tkinter desktop shell and component runtime model. Covers app.py → orchestrators → managers → components hierarchy.

## Builder Constraint Contract
- entry_uid: `journal_74db1e12f2f3`
- kind: `specification`
- source: `agent`
- status: `active`
- updated_at: `2026-03-23T22:34:26Z`
- tags: `architecture, contract, domains`

Defines sandbox/project domains, scopes, and operational constraints for the builder. Components=1 domain, managers≤3 domains, orchestrators bounded to UI or CORE side, app.py=wiring only.
