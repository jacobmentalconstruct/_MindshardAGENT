# MindshardAGENT

A lean Tkinter desktop chatbot shell for local Ollama-backed agents with sandboxed DOCKER & CLI tool execution.

## Quick Start

```bat
setup_env.bat      :: create venv + install deps
run.bat            :: launch the app
```

Or directly:
```
py -3.10 -m src.app
```

## What It Does

- Chat with locally-running Ollama models
- Execute CLI commands inside a sandboxed directory
- Stream model responses with live token estimates
- View runtime activity in a terminal-style log panel
- Direct CLI panel for sandbox command testing
- Save/load conversation sessions (SQLite)
- Cyberpunk dark neon UI theme

## Requirements

- Python 3.10+
- Ollama running locally (http://localhost:11434)
- Optional: psutil (for CPU/RAM/GPU monitoring)

## Architecture

See `_docs/ARCHITECTURE.md` for full design documentation.
