# MindshardAGENT — Roadmap & Next Steps

## Context

This session delivered tiered memory (STM + evidence bag), a token budget guard, and
multi-pass infrastructure. But the audit revealed that integration work has caused
domain boundary violations — response_loop.py is now an 8-domain mega-manager, and
app_commands.py dispatches across 6+ domains. Before adding more features, we need
to stabilize the architecture per the builder constraint contract.

This plan covers: what's done, what needs cleanup, what's next, and the order to do it.

---

## Phase 1: Architectural Cleanup (Do First)

The builder contract says: components = single domain, managers = max 2-3 domains,
orchestrators = bounded to UI or CORE side, app.py = wiring only.

### 1.1 Split ResponseLoop (CRITICAL)

**Problem:** response_loop.py handles 8 domains: planner, probes, context gathering,
STM window, evidence bag, RAG, budget guard, tool dispatch, streaming, two-pass.

**Fix:** Extract into focused components:

| New Module | Responsibility | Domain |
|-----------|----------------|--------|
| `src/core/agent/turn_assembler.py` | STM windowing, evidence bag ingest/summary, budget guard, message assembly | memory + context |
| `src/core/agent/response_loop.py` | Streaming + tool round-trips only (calls turn_assembler before inference) | agent |
| `src/core/agent/evidence_pass.py` | Two-pass detection + retrieval (called after main loop) | memory |

ResponseLoop becomes thin: it calls turn_assembler to build messages, runs the
streaming loop, then calls evidence_pass for pass-2 if needed. Each piece stays
under 200 lines.

**Files to modify:**
- `src/core/agent/response_loop.py` — extract ~150 lines
- `src/core/agent/turn_assembler.py` — NEW
- `src/core/agent/evidence_pass.py` — NEW

### 1.2 Clean Engine State Access (HIGH)

**Problem:** engine.py directly mutates response_loop private state (`_vcs`, `_active_project`, `_project_meta`).

**Fix:** Add proper setter methods on ResponseLoop:
```python
def set_workspace(self, vcs, active_project, project_meta): ...
```

**Files to modify:**
- `src/core/engine.py`
- `src/core/agent/response_loop.py`

### 1.3 Slim app_commands.py (HIGH)

**Problem:** `handle_faux_click` is a 150+ line multi-domain dispatcher.
`on_sandbox_pick` touches 7 domains.

**Fix:** These are orchestration functions. They should live in focused orchestrators,
not a flat callback file. Extract:
- `src/core/project/project_loader.py` — "Attach Self", sandbox picking, project metadata
- `src/core/project/project_syncer.py` — "Sync to Source" (may already exist partially)

app_commands.py becomes thin shims that call orchestrators.

**Files to modify:**
- `src/app_commands.py` — extract
- `src/core/project/project_loader.py` — NEW or extend existing
- `src/core/project/project_syncer.py` — NEW or extend existing

### 1.4 Self-Awareness Gating

**Problem:** `55_self_architecture.md` loads into every prompt — token waste.

**Fix:** Add `self_awareness_enabled: bool = False` to AppConfig. Prompt builder
skips `55_*.md` files when disabled.

**Files to modify:**
- `src/core/config/app_config.py`
- `src/core/agent/prompt_builder.py` (or wherever prompt docs are loaded/filtered)

---

## Phase 2: Evidence Bag — Agent Interface (Design Work)

These are the user's ideas for how agents should interact with the bag.
Build after Phase 1 cleanup.

### 2.1 Self-Discoverable Bag Manifest

The bag should ship with a machine-readable manifest so any agent can discover
how to use it without a custom adapter.

**Design:**
```json
{
  "name": "evidence_bag",
  "version": "1.0",
  "description": "Reversible evidence store. Full text preserved, query-driven assembly.",
  "capabilities": ["ingest", "query", "reconstruct", "set_goal"],
  "api": {
    "ingest_turn": {"params": ["text", "source", "source_role"], "returns": "document_id"},
    "window": {"params": ["query", "token_budget"], "returns": "evidence_slice"},
    "set_goal": {"params": ["goal_text"]},
    "close": {}
  },
  "warning": "Supplement only. Requires STM window for causal coherence."
}
```

**Files to create:**
- `.dev-tools/drop-bin/_manifold-mcp/sdk/manifest.json`
- Update `evidence_package.py` to expose manifest

### 2.2 Structural Layer (Tree + Manifest + Viewport)

Instead of dumping text, the bag presents three layers to the agent:

1. **Tree**: Structural map showing node types, topic clusters, exploration state
2. **Manifest**: Item inventory with IDs, kinds, char counts, explored/unexplored flags
3. **Viewport**: Navigable cursor — agent can focus on a node, traverse edges, widen/narrow

**Implementation approach:**
- Add `inspect()` method to EvidencePackage returning structured tree + manifest
- Add `focus(node_id)` method for viewport navigation
- Expose via MCP tool (`bag_navigate`)
- Prompt section shows tree, not raw text

**Files to create/modify:**
- `.dev-tools/drop-bin/_manifold-mcp/sdk/evidence_package.py` — add inspect/focus methods
- `.dev-tools/drop-bin/_manifold-mcp/tools/bag_navigate.py` — NEW MCP tool
- `src/core/sessions/evidence_adapter.py` — expose tree/manifest/viewport

### 2.3 CIS Staleness Handling (Step 8 from prior plan)

When bag contents change, embedded CIS in RAG becomes stale.

**Recommended approach:** Option A — delete old `source="evidence_bag"` rows before
re-embedding. Simple, correct, minimal code.

**Files to modify:**
- `src/core/agent/response_loop.py` (or turn_assembler after Phase 1 split)

---

## Phase 3: Multi-Pass Prompt Splitting

Infrastructure is pre-installed (config fields, budget report data). Build the
actual splitter after Phase 1-2.

### 3.1 Iterative Build Strategy

When budget guard trims >30% of content:
1. Planner decomposes the query into sub-tasks that each fit in budget
2. Each sub-task runs as a separate inference cycle
3. Results are stitched sequentially (each pass sees prior pass output)

### 3.2 Synthesize Strategy

Alternative: run sub-tasks in parallel, merge responses with a final synthesis pass.
Better for independent sub-queries, worse for sequential reasoning.

### 3.3 Data Collection

Budget report already logs `would_benefit_from_multipass`. Collect this data over
real usage to determine threshold tuning before building the splitter.

**Files to create:**
- `src/core/agent/multipass_splitter.py` — NEW (planner integration + sub-task routing)

---

## Phase 4: Remaining TODO Items

Grouped by priority within builder contract compliance.

### P4.1 — Security / Containment
- [ ] Per-session command policy customization

### P4.2 — UX / UI
- [ ] Dark theme refinement and DPI scaling
- [ ] Keyboard shortcuts beyond Ctrl+Enter
- [ ] UI evidence bag explorer tab (tree view of bag contents)
- [ ] App-wide highlight→ask context menu (right-click → ask in isolation or inject)

### P4.3 — Diagnostics
- [ ] Standardize diagnostic event schema for cross-app reuse
- [ ] Expose active loop mode and per-loop benchmark results in diagnostic lab
- [ ] Expose model-role usage and per-role benchmark results
- [ ] Prompt-version diff views and richer restore previews

### P4.4 — Agent Capabilities
- [ ] Trigger recovery replanning after repeated failure patterns
- [ ] Graph-based thought-chain loop for branching plan exploration
- [ ] User-visible loop mode controls / overrides

### P4.5 — Infrastructure
- [ ] NDJSON/Content-Length protocol adapter for MCP servers
- [ ] Dev tools → agent tools pipeline (how to share tooling between dev and runtime)
- [ ] Official toolbox root configuration and external tool loading
- [ ] Decompose control_pane.py (56KB — largest single file)

### P4.6 — Model Validation (Maintain)
- [ ] Set qwen3.5:9b as default planner model (validated at 93.3%)
- [ ] Model-aware timeouts (scale with model size: 0.5B→10s, 4B→60s, 9B→120s)
- [ ] Expand role eval fixtures for coding and review roles

---

## What's Done (This Session)

| Item | Status |
|------|--------|
| STM sliding window (10 turns) | DONE |
| Evidence bag falloff + ingestion | DONE |
| Bag summary injection (~128 tokens) | DONE |
| Two-pass evidence retrieval | DONE |
| Evidence adapter (thin wrapper) | DONE |
| bag_inspect MCP tool | DONE |
| Token budget guard (priority trimming) | DONE |
| Budget instrumentation in metadata | DONE |
| Multi-pass config pre-install | DONE |
| Self-architecture prompt doc (55_) | DONE (needs gating) |
| Project cleanup (__pycache__, old logs) | DONE |
| DEV_LOG entries | DONE |
| TODO.md updated | DONE |

---

## NEXT STEPS (When You Return)

**Start here:**

1. **Phase 1.1** — Split response_loop.py into turn_assembler + evidence_pass.
   This is the single highest-impact cleanup. It makes everything else easier
   and prevents the mega-manager from growing further.

2. **Phase 1.2** — Clean engine state access (quick win, 15 min).

3. **Phase 1.4** — Gate self-awareness doc behind config flag (quick win).

4. **Test the evidence bag live** — have a 15+ turn conversation, watch the
   activity stream for "Ingested N turns" and "Budget: X/Y tokens" messages.

5. **Phase 2.1** — Design the bag manifest (decision: JSON schema vs MCP tool
   description vs both).

**Don't start Phase 3 (multi-pass) until Phase 1 cleanup is done.** Adding more
complexity to an already-coupled response_loop would make the split harder.

---

## Verification

After Phase 1 cleanup:
- `py_compile` all modified files
- Run existing test suite (`tests/test_tool_roundtrip.py`)
- 15-turn conversation test (verify STM window + bag + budget guard)
- `preview_prompt` MCP tool to inspect assembled prompt
- Import analysis: response_loop.py should import from ≤4 packages

After Phase 2:
- `bag_inspect` shows tree + manifest structure
- `bag_navigate` MCP tool works from Claude Desktop
- Agent correctly identifies what's in the bag when asked

After Phase 3:
- Over-budget prompt triggers multi-pass instead of aggressive trimming
- Budget report shows `multipass_used: true` in metadata
- Compare iterative vs synthesize results on same query
