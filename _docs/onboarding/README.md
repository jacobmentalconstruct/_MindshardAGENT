# Onboarding Docs

Session-specific onboarding documents for MindshardAGENT development.

## Purpose
Each development session gets an onboarding doc that:
- Summarizes where the app is at session start
- Lists exactly what to work on and where to start
- Includes the roadmap/plan for that session's goals

## Workflow
1. At session start: read the latest onboarding doc to orient
2. During session: reference the guidebook for system understanding
3. At session end: archive the onboarding doc to `archive/` with a date prefix

## Files
- `GUIDEBOOK.md` — Permanent reference: full system guide, all subsystems explained
- `ROADMAP.md` — Current roadmap and phase plan (updated each session)
- `NEXT_SESSION.md` — Where to start next (updated at end of each session)
- `archive/` — Completed session onboarding docs (date-prefixed)

## Giving These to Another Agent
To onboard a GPT or other agent on this project, provide:
1. `GUIDEBOOK.md` (system understanding)
2. `ROADMAP.md` (what's planned)
3. `NEXT_SESSION.md` (where to start)
4. A project folder tree dump
5. The builder constraint contract (`_docs/builder_constraint_contract.md`)
