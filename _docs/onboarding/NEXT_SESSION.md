# Next Session — Start Here

**Last updated:** 2026-03-25
**Current phase:** core stabilization and live-test hardening before returning to builder-contract alignment

---

## Read This First

- [SESSION_2026-03-25_HANDOFF.md](/C:/Users/jacob/Documents/_UsefulAgenticBuilderSANDBOX/Claude-Code/_MindshardAGENT/_docs/onboarding/SESSION_2026-03-25_HANDOFF.md)
- [TODO.md](/C:/Users/jacob/Documents/_UsefulAgenticBuilderSANDBOX/Claude-Code/_MindshardAGENT/_docs/TODO.md)
- latest `STAB-001` section in [DEV_LOG.md](/C:/Users/jacob/Documents/_UsefulAgenticBuilderSANDBOX/Claude-Code/_MindshardAGENT/_docs/DEV_LOG.md)

---

## What To Do First

### 1. Re-open the app and verify session preservation
Confirm these two saved sessions still appear:
- `Bridge UI Smoke — BRIDGE_OK round-trip`
- `Bridge UI Smoke — Planner stop verification`

### 2. Fix the visible stop/unwind path
The last live `Plan` run accepted a real stop request but never returned to
`Ready`. Solve this before running more long thought-chain tests.

### 3. Add Plan/thought-chain prompt anchoring
The planner interpreted "bridge lab workspace" as a physical bridge inspection
problem because the thought-chain prompt is not grounded in the attached
software project context.

### 4. Add small-model Plan guardrails
At minimum:
- per-round timeout
- first-token latency logging
- heartbeat/progress telemetry
- output caps for long planning rounds

### 5. Persist Plan/thought-chain results into session history
Live UI messages were visible, but the later Plan runs were not recoverable from
the session DB. Fix that before the next visible long-form test pass.

---

## What Not To Do Yet

- Don’t resume builder-contract cleanup yet.
- Don’t delete prep docs for TODO or north-star work.
- Don’t run more long `Plan` tests on `qwen3.5:4b` until stop/unwind and guardrails are improved.

---

## Reference

- Live test workspace:
  `C:\Users\jacob\Documents\_UsefulHelperAPPS\_MindshardBridgeLab`
- App journal entry:
  `journal_c07d3c1f67db`
