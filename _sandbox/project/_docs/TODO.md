# TODO — MindshardAGENT

## High Priority

- [x] Wire session store into app.py (save/load/new/delete/branch through UI)
- [x] Add session management UI (list, select, rename, branch, delete)
- [x] Wire StateRegistry into engine for runtime node tracking
- [x] Install psutil into venv for resource monitor to work
- [x] Add sandbox root folder picker dialog in UI

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
- [ ] Tab breakout into standalone columns (left or right of app)
- [ ] Panel and column resizability (PanedWindow sash tuning)
- [ ] Dark theme refinement and DPI scaling
- [ ] Keyboard shortcuts (Ctrl+Enter submit already works)

## Low Priority / Future

- [ ] Sandbox-authored tool creation (agent creates tools under _tools/)
- [ ] Cannibalistic Thought Chains (agent self-talk spiral → task list generation)
- [ ] Official toolbox root configuration and external tool loading
- [ ] Per-session command policy customization

## Deferred by Blueprint

- ~~Multiple built-in tools beyond CLI sandbox tool~~ (write_file + read_file shipped)
- ~~Multi-tab workspaces~~ (tabbed control pane shipped; breakout columns pending)
- Full plugin marketplace behavior
- Persistent graph database backend
- Deep resource telemetry beyond basic polling
- ~~Agent self-editing outside sandbox~~ (Load Self + Sync Back shipped)
- BDVecEmbed offline fallback embedder (requires local corpus training first)
