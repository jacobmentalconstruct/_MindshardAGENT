# Drop Bin

This folder is the intake area for rough scripts, experiments, one-off helpers, and random tooling ideas that are not yet part of the official tool suite.

## Purpose

Use this folder when you want to:

- dump a random script for later cleanup
- save a promising utility before it is normalized
- collect rough tools from different projects
- stage a conversion into a proper `tools/` script

## Rules

- Files here are not official tools yet.
- Files here should not be exposed through MCP as-is.
- Files here do not have to follow the suite contract yet.
- Promotion into `tools/` should happen only after cleanup and normalization.

## Suggested Intake Flow

1. Drop the raw script here.
2. Add a short note at the top of the script if possible:
   - where it came from
   - what problem it solves
   - whether it seems reusable or project-specific
3. Later, decide one of three outcomes:
   - reject it
   - keep it as project-specific intake only
   - convert and promote it into `tools/`

## Good Naming Pattern

Prefer descriptive names like:

- `incoming_sql_mapper.py`
- `rough_doc_indexer.py`
- `candidate_test_locator.py`

That makes later triage much easier.
