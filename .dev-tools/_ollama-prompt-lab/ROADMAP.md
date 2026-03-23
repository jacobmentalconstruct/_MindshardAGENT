# Roadmap

## Phase 1

- add shared runtime helpers
- add a model-runner wrapper for Ollama CLI or HTTP
- define prompt/case/rubric JSON schemas
- create tiny fixture cases and prompt variants

## Phase 2

- build `ollama_prompt_lab`
- build `prompt_case_builder`
- build `prompt_rubric_judge`

## Phase 3

- build `prompt_diff_report`
- build `agent_interview`
- add regression summaries and artifact indexes

## Phase 4

- add optional MCP wrapper
- add prompt-pack export/import
- add batch comparison across prompt families

## Notes

- Start with repeatable offline evals.
- Keep the first version boring and inspectable.
- Save raw outputs first; derive reports second.
