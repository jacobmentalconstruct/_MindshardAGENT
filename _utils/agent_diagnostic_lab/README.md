# Agent Diagnostic Lab

Internal diagnostics bench for `AgenticTOOLBOX`.

This utility is meant to help inspect and tune the app and the agent more
surgically than the main chat UI allows. It can probe:

- prompt assembly
- direct model streaming
- full engine turns
- repeatable benchmark suites
- prompt version history
- benchmark run history
- prompt restore / rollback
- benchmark run comparison
- activity and event flow
- resource snapshots

Outputs are exported under `outputs/` so runs can be compared later.

## Run

```bat
run.bat
```

## Notes

- The lab imports real core modules from the main app.
- It is intentionally isolated from the main Tk shell.
- The utility defaults the sandbox path to the main project root so the app can
  inspect itself immediately.
- Benchmark suites are defined in `_docs/benchmark_suite.json` so both humans
  and agents can tune against the same editable test set.
- Prompt snapshots live under `.prompt-versioning/` and benchmark/probe results
  are tracked in the adjacent SQLite database.
- The History tab is the safe checkpoint surface:
  - refresh recent prompt versions
  - compare benchmark runs by id
  - restore a prompt version back into the live prompt docs
