# MindshardAGENT External System Atlas

This atlas is the external-facing system map for MindshardAGENT.

It is designed for:
- fresh AI agents that need orientation without a full repo dump
- humans creating explainers, videos, diagrams, or onboarding material
- technical readers who need architecture and lifecycle clarity without prior project history

This atlas is not:
- the builder contract
- the app journal
- the full codebase
- an internal-only shorthand note set

It is a translation layer from the running system into a structured, externally comprehensible map.

## How To Read This Atlas

Start here:
1. `00_SYSTEM_OVERVIEW.md`
2. `10_ARCHITECTURE_MAP.md`
3. `20_RUNTIME_LIFECYCLE.md`

Use these for navigation:
- `30_SUBSYSTEM_CATALOG.md`
- `40_FILE_TREE_GUIDE.md`
- `50_GLOSSARY.md`
- `60_INTEGRATION_SEAMS.md`
- `70_STORAGE_AND_TRUTH_MODEL.md`
- `80_OPERATOR_WORKFLOWS.md`
- `90_VIDEO_OVERVIEW_PROMPT.md`
- `95_OVERVIEW_CODE_SAMPLER.txt`

Machine-readable navigation lives in:
- `atlas_registry.json`

Helper tooling for media handoff lives here too:
- `build_overview_code_sampler.py`

## Current System Position

At the time this atlas was written, MindshardAGENT includes:
- a stabilized main desktop app
- an agent runtime with loop-based execution and tool routing
- project-local sandbox and sidecar state
- Prompt Lab as a separate subsystem for prompt/execution design and evaluation
- MCP surfaces for the main agent, UI bridge, and Prompt Lab
- SQLite-backed builder memory via the app journal

Prompt Lab is integrated and operational, but its first real authored prompt/execution packages are still the next product phase.

## Atlas Scope

This atlas prioritizes:
- system shape
- subsystem ownership
- runtime flow
- storage model
- integration seams
- navigation guidance

It intentionally does not try to reproduce every implementation detail in the repo.
