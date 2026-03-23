# TODO — MindshardAGENT

## High Priority

- [x] Internal diagnostic lab utility for prompt/model/engine probes under `_utils/`
- [x] Hybrid prompt tuning history (`.prompt-versioning/` Git + SQLite probe tracking)
- [x] Repeatable benchmark runner with token-aware scoring exposed in the diagnostic lab
- [x] Wire session store into app.py (save/load/new/delete/branch through UI)
- [x] Add session management UI (list, select, rename, branch, delete)
- [x] Wire StateRegistry into engine for runtime node tracking
- [x] Install psutil into venv for resource monitor to work
- [x] Add sandbox root folder picker dialog in UI

- [x] Add cross-run comparison views and version rollback UI on top of prompt tuning history
- [ ] Standardize diagnostic event schema so probe exports can be reused across apps
- [ ] Expand benchmark suites beyond the initial intent / reality / architecture core
- [x] Add cross-run comparison views to the diagnostic lab
- [x] Add explicit model-role slots and settings UI for planner / recovery / coding / review / probe routing
- [x] Route initial execution planning through the planner model before non-trivial agent loops
- [x] Extract loop manager / selector seam so response modes are modular instead of hardcoded
- [ ] Expose active loop mode and per-loop benchmark results in the diagnostic lab
- [ ] Trigger recovery replanning after repeated failure patterns
- [ ] Expose model-role usage and per-role benchmark results in the diagnostic lab
- [ ] Add prompt-version diff views and richer restore previews in the diagnostic lab
- [ ] Add user-visible loop mode controls / overrides for testing specific response modes
- [ ] Design graph-based thought-chain loop for branching plan exploration and merge-back

## Medium Priority

- [x] Session-scoped RAG knowledge store (SQLite + cosine similarity)
- [x] Ollama embedding client (all-minilm 384-dim via /api/embeddings)
- [x] RAG context injection into system prompt
- [x] Auto-embed chat turns into knowledge base after each exchange
- [x] Save-on-close session persistence
- [x] Autosave debounce after turn completion
- [x] Model chain workflows (Model A → file → Model B)
- [x] Tool catalog discovery of sandbox-local tools at startup
- [x] Resource monitor polling for GPU VRAM stats
- [x] Streaming text height auto-resize during token delivery
- [x] Full tokenizer integration (adaptive per-model chars/token ratio)

- [x] Tool-use round-trip testing with small models (39/39 passed, qwen3.5:2b live verified)
- [x] Built-in write_file/read_file tools (solves multi-line file creation on Windows cmd)
- [x] Project sync-back mechanism (sandbox/project/ → real source with diff preview)
- [x] Action journal for agent orientation (structured event log injected into prompt)
- [x] "Load Self" / "Sync Back" action buttons replacing placeholder faux buttons
- [x] Streaming chat fix (canvas scrollregion update on card resize)

## Security / Containment

- [x] Command allowlist policy (36 commands, pattern escape detection)
- [x] OS knowledge module for agent teaching
- [x] User confirmation modal for destructive commands (del, rm, rmdir)
- [x] Command audit log (persistent JSON-lines at _sandbox/_logs/audit.jsonl)
- [x] Disposable run workspace for Python execution under `.mindshard/runs/`

- [x] Docker containerized sandbox (v2 containment upgrade)
  - Dockerfile, DockerManager, DockerRunner, dual-mode engine, Docker-aware prompt builder
  - UI Docker panel: status light, enable toggle, Build/Start/Stop/Nuke buttons
  - Integration tested: volume mount, exec, network isolation, blocked commands
- [ ] Per-session command policy customization

## UX / UI

- [x] Tabbed control pane (Session / Sandbox / Watch tabs)
- [x] Last Response preview in Watch tab (scrollable)
- [x] Session auto-naming with timestamps (no more generic "New Session")
- [x] Empty session purge on startup (cleans orphaned skeletons)
- [x] Delete-active-session loads next available instead of creating new
- [x] Tab breakout into standalone columns (right-click tab → pop out left/right, Dock button to return)
- [x] Panel and column resizability (visible sashes on all PanedWindows, raised relief, 6px grab area)
- [ ] Dark theme refinement and DPI scaling
- [ ] Keyboard shortcuts (Ctrl+Enter submit already works)

## Tiered Memory / Evidence Bag

- [x] STM sliding window (configurable window size, default 10 turns)
- [x] Evidence bag falloff (turns that leave window → ingested into manifold NodeStore)
- [x] Bag summary injection into prompt (~128 tokens, every turn)
- [x] Two-pass evidence retrieval (uncertainty detection → deeper retrieval → re-generate)
- [x] Evidence adapter (thin wrapper around manifold SDK)
- [x] `bag_inspect` MCP tool (observe bag contents + what agent sees)
- [x] Config fields: `stm_window_size`, `evidence_bag_enabled`, `evidence_bag_summary_budget`, `evidence_bag_retrieval_budget`
- [ ] UI evidence bag explorer tab (browse/expand bag contents)
- [ ] CIS staleness handling (invalidate embedded summary when bag contents change)
- [ ] NDJSON/Content-Length protocol adapter for MCP servers
- [ ] App-wide highlight→ask context menu (right-click → ask in isolation or inject into chat)
- [ ] Dev tools → agent tools pipeline (share tooling between dev and runtime)

## Context Budget / Multi-Pass

- [x] Token budget guard (priority-ordered trimming before model inference)
- [x] Budget instrumentation (per-turn token breakdown in response metadata)
- [x] Multi-pass config fields pre-installed (`multipass_enabled`, `multipass_strategy`)
- [ ] Multi-pass prompt splitter (planner breaks oversized prompt into sub-tasks)
- [ ] Iterative build strategy (sequential sub-prompts, build response incrementally)
- [ ] Synthesize strategy (parallel sub-prompts, merge responses)
- [ ] Multi-pass vs budget-guard comparison data collection

## Low Priority / Future

- [ ] Teach agent project tidiness (folder structures, naming conventions, not dumping everything flat in sandbox root)
- [ ] Sandbox-authored tool creation (agent creates tools under _tools/)
- [x] Cannibalistic Thought Chains (agent self-talk spiral → task list generation)
  - 3-round spiral: brainstorm → refine → concrete task list
  - Each round's prompt demands more specificity than previous
  - Task parser extracts numbered items with complexity tags
  - "Plan" button triggers dialog → rounds shown in chat → final task list
- [ ] Official toolbox root configuration and external tool loading
- [ ] Per-session command policy customization
- [ ] Loop family expansion:
  - recovery-agent loop
  - benchmark loop
  - review/judge loop
  - model-chain loop routing by intent

## Deferred by Blueprint

- ~~Multiple built-in tools beyond CLI sandbox tool~~ (write_file + read_file shipped)
- ~~Multi-tab workspaces~~ (tabbed control pane shipped; breakout columns pending)
- Full plugin marketplace behavior
- Persistent graph database backend
- Deep resource telemetry beyond basic polling
- ~~Agent self-editing outside sandbox~~ (Load Self + Sync Back shipped)
- BDVecEmbed offline fallback embedder (requires local corpus training first)
