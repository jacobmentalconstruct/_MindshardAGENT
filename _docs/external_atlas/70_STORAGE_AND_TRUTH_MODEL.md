# 70 Storage and Truth Model

## Purpose

This document explains where different kinds of data live and which forms of truth the system distinguishes.

This is one of the most important parts of understanding MindshardAGENT.

## There Is Not One Kind Of Truth

The system separates several kinds of truth:
- builder/project memory truth
- runtime/project state truth
- prompt-lab design truth
- prompt-lab active runtime truth
- prompt-versioning/evaluation truth

If these are confused, the system becomes much harder to reason about.

## Builder / Project Memory Truth

Location:
- `_docs/_journalDB/app_journal.sqlite3`

This holds:
- dev log
- TODOs
- work logs
- doctrine
- specifications mirrored into journal entries
- onboarding and roadmap continuity

This is for:
- builders
- future agents
- project continuity

It is not runtime app state.

## Main Runtime / Project Sidecar Truth

Location:
- `.mindshard/`

This project-local sidecar holds operational state such as:
- sessions
- logs
- state records
- tools/ref/parts/output support folders

This is attached-project truth, not builder memory.

## Prompt Lab Design Truth

Primary root:
- `.mindshard/prompt_lab/`

Important subpaths:
- `prompt_profiles/`
- `execution_plans/`
- `bindings/`
- `drafts/`
- `published/`
- `active/`
- `build_artifacts/`
- `eval_runs/`
- `promotion/`

Prompt Lab also uses:
- `prompt_lab.sqlite3`
- `operations.jsonl`

### Canonical Formats

For Prompt Lab Phase 1/2:
- JSON is canonical for design objects
- SQLite is canonical for indexed history and related records

## Prompt Lab Runtime Truth

Prompt Lab runtime truth is narrower than Prompt Lab design truth.

The runtime is allowed to consume only:
- explicit active state
- explicit published package state

It is not supposed to consume:
- drafts
- arbitrary source edits
- UI state

This rule is enforced through:
- `src/core/prompt_lab/runtime_loader.py`

## Prompt Versioning / Evaluation Truth

Location:
- `.prompt-versioning/`

This holds prompt-tuning and evaluation related persistence outside the builder journal.

It is closer to app/system evaluation state than to builder continuity memory.

## Static Prompt Lab Assets

Location:
- `prompt_lab/`

This directory is not the mutable state store.
It is the subsystem’s asset/doc root.

Think of it as:
- docs
- doctrine
- static templates and descriptive artifacts

not:
- the live mutable project-local Prompt Lab state

## Truth Model Summary

```text
Builder memory
  -> _docs/_journalDB/app_journal.sqlite3

Attached project runtime state
  -> .mindshard/

Prompt Lab mutable design state
  -> .mindshard/prompt_lab/

Prompt Lab runtime-consumable state
  -> active + published package records only

Prompt versioning / evaluation persistence
  -> .prompt-versioning/
```

## Why This Separation Matters

This separation allows the system to:
- preserve builder continuity without polluting runtime state
- run Prompt Lab experimentation without mutating active runtime truth
- keep published/active boundaries explicit
- make rollback and inspection easier
