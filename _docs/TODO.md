# TODO — AgenticTOOLBOX

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
- [ ] Sandbox-authored tool creation (agent creates tools under _tools/)
- [ ] Tool catalog discovery of sandbox-local tools at startup
- [ ] Resource monitor polling for GPU VRAM stats
- [ ] Streaming text height auto-resize during token delivery
- [x] Save-on-close session persistence
- [x] Autosave debounce after turn completion

## Security / Containment

- [x] Command allowlist policy (36 commands, pattern escape detection)
- [x] OS knowledge module for agent teaching
- [x] User confirmation modal for destructive commands (del, rm, rmdir)
- [x] Command audit log (persistent JSON-lines at _sandbox/_logs/audit.jsonl)
- [ ] Docker containerized sandbox (v2 containment upgrade)
- [ ] Per-session command policy customization

## Low Priority / Future

- [ ] Agent-to-agent chaining experiments (spawn sub-instances)
- [ ] Model chain workflows (Model A → file → Model B)
- [ ] Tool-use round-trip testing with small models (qwen3.5:2b, 4b)
- [ ] Official toolbox root configuration and external tool loading
- [ ] Full tokenizer integration for exact model-specific counts
- [ ] Dark theme refinement and DPI scaling
- [ ] Keyboard shortcuts (Ctrl+Enter submit already works)

## Deferred by Blueprint

- Multiple built-in tools beyond CLI sandbox tool
- Full plugin marketplace behavior
- Persistent graph database backend
- Deep resource telemetry beyond basic polling
- Multi-tab workspaces
- Agent self-editing outside sandbox
- BDVecEmbed offline fallback embedder (requires local corpus training first)
