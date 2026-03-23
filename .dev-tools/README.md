# Dev Tools Toolbox

This folder is the local agent toolbox.

It is organized so a zero-context agent can tell, at a glance, what is ready to use and what is not.

## Top-Level Meaning

- `final-tools/`
  - active vendorable headless tool suite for folder/code/data/UI work
- `_app-journal/`
  - active vendorable SQLite journal package with Tkinter UI and MCP access
- `_manifold-mcp/`
  - active vendorable evidence-bag and reversible manifold package
- `_ollama-prompt-lab/`
  - active vendorable prompt-eval package for local Ollama workflows
- `legacy/`
  - older loose scripts kept for reference or later conversion
- `intake/`
  - incomplete or empty scaffolds and rough future work

## Agent Rule

If you have no context:

1. read `toolbox_manifest.json`
2. choose one of the active package folders
3. read that package's `tool_manifest.json` and `README.md`
4. ignore `legacy/` and `intake/` unless the user explicitly asks about them

## What Counts As Active

An active package is a self-contained folder with:

- its own `README.md`
- its own `tool_manifest.json`
- its own entrypoints
- its own smoke test

## What Does Not Count As Active

- loose scripts in `legacy/root-scripts`
- empty scaffolds in `intake/empty-scaffolds`

Those are preserved so nothing useful is lost, but they are not the default tool surface for agents.
