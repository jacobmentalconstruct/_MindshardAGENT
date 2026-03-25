# Dev Tools → Agent Tools Pipeline

_Design doc — 2026-03-23. Describes the promotion path for toolbox tools into
runtime agent tools. Do not build until living graph loop is shipped._

---

## The Problem

Dev tools (under `.dev-tools/`) are structured for human + MCP invocation:
- `python <pkg>/tools/<tool>.py metadata|run` CLI contract
- JSON envelopes: `{name, description, input_schema, result}`
- Used from Claude Desktop or the diagnostic lab

Runtime agent tools (under `_sandbox/_tools/` or engine's tool catalog) are
invoked by the agent during turns:
- Discovery at startup via `ToolCatalog.scan()`
- Execution via `ToolRouter.execute_all(assistant_text)`
- Exposed in the system prompt as `[available_tools]` block

These are different contracts. A dev tool that passes `python tool.py run` is
not directly callable by the agent without adaptation.

---

## Promotion Path

### Stage 1: Tool passes quality gate

A tool is eligible for promotion when it meets all criteria:
- [ ] `metadata` returns valid JSON with `name`, `description`, `input_schema`
- [ ] `run` accepts JSON on stdin and writes JSON to stdout (MCP envelope)
- [ ] No interactive I/O (no tkinter, no `input()`)
- [ ] Handles missing/bad input gracefully (returns error envelope, not exception)
- [ ] Runtime-safe (no file writes outside sandbox, no network by default)

Quality gate is checked by `python_risk_scan` (final-tools MCP) + manual review.

### Stage 2: Adapter wrapper

Create a thin adapter in `_sandbox/_tools/<tool_name>.py`:
```python
"""Adapter: promotes <tool_name> from .dev-tools into agent tool catalog.

This file is discovered by ToolCatalog at startup and callable by the agent.
It delegates to the source tool via subprocess.
"""
import json, subprocess, sys
from pathlib import Path

TOOL_PATH = Path(__file__).resolve().parents[N] / ".dev-tools" / "<pkg>" / "tools" / "<tool>.py"

def run(args: dict) -> dict:
    proc = subprocess.run(
        [sys.executable, str(TOOL_PATH), "run"],
        input=json.dumps(args),
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        return {"error": proc.stderr.strip() or "tool failed"}
    return json.loads(proc.stdout)

# Standard tool metadata for ToolCatalog discovery
TOOL_METADATA = {
    "name": "<tool_name>",
    "description": "<copy from tool metadata>",
    "input_schema": { ... },  # copy from tool metadata
}
```

The agent sees this as a normal sandbox tool. The adapter handles the subprocess
boundary and translates any tool-specific conventions.

### Stage 3: Integration test

Add a test case to `tests/test_tool_roundtrip.py` (or a new tool-specific file):
```python
def test_<tool_name>_roundtrip():
    result = run_tool_via_catalog("<tool_name>", {"<input>": "<value>"})
    assert result.get("error") is None
    assert "<expected_key>" in result
```

Run: `python -m pytest tests/test_<tool_name>_roundtrip.py`

### Stage 4: Prompt doc update

Add the tool to the relevant prompt doc section so the agent knows when to use it:
- `50_tool_usage_preferences.md` — when to prefer this tool over shell
- Or create `62_specialized_tools.md` for tools that need specific guidance

---

## Candidate Tools for Promotion

| Tool | Package | Use Case | Effort |
|------|---------|----------|--------|
| `workspace_audit` | final-tools | Agent self-checks folder hygiene | Low |
| `python_risk_scan` | final-tools | Pre-commit code safety checks | Low |
| `data_shape_inspector` | final-tools | Inspect DataFrames, JSON schemas | Medium |
| `structured_patch` | final-tools | Safe multi-file patch application | Medium |
| `journal_write` | app-journal | Agent writes structured dev notes | Low |
| `journal_query` | app-journal | Agent queries its own journal | Low |

### Not candidates (UI tools)
- `tk_ui_*` tools (final-tools) — require Tkinter display, not runtime-safe
- `ollama_prompt_lab` — diagnostic tool, not runtime action

---

## Sandbox-Authored Tool Creation

Separate from promotion: the agent can create NEW tools under `_sandbox/_tools/`
during a session. These are discovered at the next reload (F5) or startup.

Rules the agent must follow:
1. Tool file must export `TOOL_METADATA` dict with `name`, `description`, `input_schema`
2. Tool file must export `run(args: dict) -> dict`
3. No side effects outside sandbox (no writes to `src/`, no network)
4. Agent must call `reload_tools` after creating to make it discoverable

This is the `Sandbox-authored tool creation` feature from the TODO — it's already
mechanically possible (ToolCatalog scans `_tools/`). The remaining work is:
- Prompt doc teaching the agent the tool contract
- Validation at scan time (reject malformed tools with a warning, not crash)
- UI indicator showing agent-created tools with a distinct badge

---

## Relationship to Living Graph

Once the living graph loop ships, dev tool promotion becomes more powerful:
- The agent can pick the right tool for a node type (Evidence-gathering → workspace_audit)
- Graph operation `ADD_EVIDENCE` can reference a promoted tool as the `produced_by` source
- Tool results become first-class evidence nodes, not just tool_output strings

This is the long-term vision: tools are typed evidence producers that the graph
navigator can dispatch selectively based on node type and active task.
