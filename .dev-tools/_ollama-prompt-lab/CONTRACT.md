# Contract

This subproject is for local prompt evaluation and agent-behavior experiments.

## Builder Pledge

- Keep the folder isolated and portable.
- Keep model-specific logic configurable.
- Keep eval artifacts machine-readable.
- Keep raw transcripts alongside summaries.
- Never collapse scoring to a single magic number without rubric detail.
- Prefer deterministic checks before model-judge checks.
- Treat local judge models as heuristics, not truth.
- Make prompt versions explicit and comparable.

## Standard Tool Contract

Every tool in `tools/` should:

- include a clear file header
- export `FILE_METADATA`
- export `run(arguments)`
- support `metadata`
- support `run --input-json`
- support `run --input-file`
- return a stable JSON envelope

## MCP Contract

- Prefer MCP as the primary operation path for agents.
- Keep MCP tool names stable once published.
- MCP must call the same `run(arguments)` function as the CLI path.
- Do not fork business logic between MCP and CLI execution.

## Core Result Fields

Every result should try to include:

- `status`
- `tool`
- `input`
- `result`
- `summary`
- `warnings`
- `artifacts`

## Eval-Specific Fields

Prompt-eval tools should use explicit fields where possible:

- `prompt_id`
- `prompt_version`
- `model`
- `case_id`
- `rubric_id`
- `transcript_path`
- `score_breakdown`
- `deterministic_checks`
- `judge_notes`
- `recommendation`
- `leaderboard`

## Promotion Rule

Do not move experimental scripts into stable tools until they:

- have deterministic inputs
- emit stable JSON
- document assumptions
- save artifacts predictably
- survive smoke tests against small fixture cases
