# Ollama Prompt Lab

This folder is an isolated subproject inside `.dev-tools` for local prompt evaluation, prompt iteration, and agent-behavior scoring with Ollama-hosted models.

It is intentionally separated from the main `.final-tools` suite because it has heavier runtime assumptions:

- local model pulls
- longer-running eval jobs
- prompt and rubric versioning
- transcript and scoring artifacts
- experimental judge logic

## Purpose

Use this folder to:

- run prompt variants against local models
- score outputs against deterministic checks and rubrics
- compare prompt revisions before promoting them
- save transcripts and eval artifacts for later review

## Layout

- `tools/`
  - stable prompt-lab tools
- `jobs/`
  - machine-run job specs
- `artifacts/`
  - transcripts, scores, summaries, comparisons
- `templates/`
  - prompt, rubric, and case templates
- `sessions/`
  - optional one-off experiments and temporary working notes
- `drop-bin/`
  - random scripts or rough experiments to be converted later
- `tool_manifest.json`
  - machine-readable project manifest
- `common.py`
  - shared runtime and CLI contract
- `mcp_server.py`
  - MCP stdio wrapper for agent operation
- `smoke_test.py`
  - portable self-test for the subproject
- `ROADMAP.md`
  - build order and scope
- `CONTRACT.md`
  - mechanical contract to keep across tools

## Current Tooling

- `ollama_prompt_lab`

## Planned Next Tools

- `prompt_case_builder`
- `prompt_rubric_judge`
- `prompt_diff_report`
- `agent_interview`

## Standard CLI Contract

All tools in this folder should support:

```powershell
python _ollama-prompt-lab\tools\<tool>.py metadata
python _ollama-prompt-lab\tools\<tool>.py run --input-json "{...}"
python _ollama-prompt-lab\tools\<tool>.py run --input-file _ollama-prompt-lab\jobs\examples\<job>.json
```

## MCP First

This subproject is designed to be agent-operated through MCP first.

Start the MCP server with:

```powershell
python _ollama-prompt-lab\mcp_server.py
```

The MCP layer calls the same `run(arguments)` function used by the CLI, so agent and manual runs stay aligned.

## Quick Start

```powershell
python _ollama-prompt-lab\tools\ollama_prompt_lab.py run --input-file _ollama-prompt-lab\jobs\examples\quick_eval.json
```

This writes a timestamped artifact folder under `_ollama-prompt-lab\artifacts\runs\`.

## Isolation Rule

Keep this folder self-contained so it can be zipped, copied, or vendored into other workspaces as a standalone prompt-eval project.
