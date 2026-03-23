# Next Session — Start Here

**Last updated:** 2026-03-23
**Last session delivered:** Tiered memory (STM + evidence bag), token budget guard, multi-pass infrastructure

---

## What to Do First

### 1. Test the evidence bag live (10 min)
The bag integration is built and unit-tested but hasn't been tested in a real
conversation yet. Load the app, have a 15+ turn conversation, and watch the
activity stream for:
- `"Ingested N turns into evidence bag"` — confirms falloff is working
- `"Token budget: X/Y tokens"` — confirms budget guard is active
- `"Pass-2: retrieving deeper evidence"` — confirms two-pass fires on uncertainty

### 2. Phase 1.1: Split response_loop.py (1-2 hours)
This is the highest-impact cleanup. response_loop.py is an 8-domain mega-manager.
Extract into:
- `turn_assembler.py` — STM window, evidence bag, budget guard, message assembly
- `evidence_pass.py` — two-pass detection and retrieval
- `response_loop.py` — becomes thin: streaming + tool round-trips only

See ROADMAP.md Phase 1.1 for details.

### 3. Quick wins (30 min total)
- Phase 1.2: Add `set_workspace()` method to ResponseLoop (replace direct `_` access)
- Phase 1.4: Gate `55_self_architecture.md` behind `self_awareness_enabled` config flag

---

## What NOT to Do Yet

- Don't start multi-pass prompt splitting (Phase 3) until Phase 1 cleanup is done
- Don't build the bag UI explorer tab yet (Phase 4 — after bag agent interface is designed)
- Don't refactor app_commands.py yet (Phase 1.3 — do after response_loop split)

---

## Key Design Decisions Pending

1. **Bag manifest format**: JSON schema vs MCP tool description vs both?
2. **Bag structural layer**: How much tree/manifest/viewport do we expose in the prompt
   vs make available as tools the agent calls on demand?
3. **Multi-pass strategy**: Iterative build (sequential) vs synthesize (parallel merge)?
   Collect data from budget guard first.

---

## Files You'll Touch

| File | What | Why |
|------|------|-----|
| `src/core/agent/response_loop.py` | Extract ~150 lines | Phase 1.1 split |
| `src/core/agent/turn_assembler.py` | NEW | STM + bag + budget assembly |
| `src/core/agent/evidence_pass.py` | NEW | Two-pass retrieval |
| `src/core/engine.py` | Use setters | Phase 1.2 cleanup |
| `src/core/config/app_config.py` | Add self_awareness flag | Phase 1.4 |

---

## Reference Docs

- `_docs/onboarding/GUIDEBOOK.md` — full system guide (read if you need orientation)
- `_docs/onboarding/ROADMAP.md` — complete phase plan
- `_docs/builder_constraint_contract.md` — domain boundary rules
- `_docs/ARCHITECTURE.md` — composition tree
- `_docs/DEV_LOG.md` — what was built and when
