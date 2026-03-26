# MindshardAGENT

MindshardAGENT is a local-first desktop agent workbench for advanced project
building, inspection, and controlled tool use.

It combines:
- local Ollama-backed chat and loop execution
- sandbox-aware CLI tool access
- session persistence and project state
- prompt/workbench inspection surfaces
- Prompt Lab foundations for deeper prompt/execution design work

This is not a toy chatbot shell anymore. It is closer to a power tool for local
agentic development.

## Who This Is For

MindshardAGENT is meant for users who want a serious local agent workbench and
are comfortable operating with project structure, runtime state, and tooling
surfaces that can materially affect files and workflows.

If you want a low-risk general chat app, this is probably not the right tool.

## Practical Safety Note

MindshardAGENT can be used safely, but it should be used deliberately.

Like a table saw or skill saw, the danger is not that the tool is "bad." The
danger is that it is powerful enough to do real work quickly, including work
you may not actually want if it is misconfigured or used carelessly.

Examples of what that means in practice:
- agent-driven tool calls can change files inside the active project
- project settings and prompt/runtime configuration can influence behavior in
  non-obvious ways
- experimentation without review can damage a working project state
- draft or testing workflows should not be treated casually on important code

Recommended operating habits:
- use version control or backups before major experimentation
- learn on disposable or low-stakes projects first
- review tool-facing behavior before trusting it on important work
- treat configuration changes as real engineering changes, not harmless toggles
- keep prompt/design experiments isolated until they are ready to promote

The app is intended to help capable builders move faster, not to remove the
need for judgment.

## Current Capabilities

- chat with locally running Ollama models
- execute CLI commands inside a sandbox-aware project context
- stream responses with runtime/status visibility
- save and reload sessions
- inspect runtime activity in a terminal-style log panel
- work with multiple loop modes, including planning-oriented flows
- use a Prompt Workbench inside the app for source/build inspection
- use the emerging Prompt Lab subsystem for structured prompt/execution work
- maintain project and builder continuity through the app journal

## Quick Start

```bat
setup_env.bat
run.bat
```

Or directly:

```bat
py -3.10 -m src.app
```

## Requirements

- Python 3.10+
- Ollama running locally at `http://localhost:11434`
- optional: `psutil` for richer local runtime monitoring

## Project Surfaces

- Main app entrypoint: `src/app.py`
- Prompt Lab subsystem entrypoint: `src/prompt_lab/main.py`
- Project journal DB: `_docs/_journalDB/app_journal.sqlite3`
- Prompt Lab project-local state: `.mindshard/prompt_lab/`

## Documentation

- architecture and subsystem notes: `_docs/ARCHITECTURE.md`
- builder contract and build discipline: `_docs/builder_constraint_contract.md`
- Prompt Lab storage/doctrine notes: `prompt_lab/STORAGE_DOCTRINE.md`

## Status

The app is actively evolving and already useful, but it should still be treated
as an advanced builder workbench rather than a polished beginner-safe product.

That is intentional. The goal is to provide strong local capability with clear
boundaries, not to hide the fact that powerful tooling requires careful use.
