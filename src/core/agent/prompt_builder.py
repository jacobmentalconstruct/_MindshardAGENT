"""System prompt construction for the Ollama agent."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from src.core.agent.os_knowledge import get_command_teaching
from src.core.agent.prompt_sources import PromptSection, PromptSourceResult, load_prompt_sources
from src.core.sandbox.command_policy import CommandPolicy
from src.core.sandbox.tool_catalog import ToolCatalog


@dataclass(frozen=True)
class PromptBuildResult:
    """Effective system prompt plus diagnostics for preview and reload checks."""

    prompt: str
    sections: tuple[PromptSection, ...]
    source_fingerprint: str
    prompt_fingerprint: str
    warnings: tuple[str, ...] = ()


def build_system_prompt_bundle(
    sandbox_root: str,
    tools: ToolCatalog,
    command_policy: CommandPolicy | None = None,
    session_title: str = "",
    model_name: str = "",
    rag_context: str = "",
    docker_mode: bool = False,
    journal_context: str = "",
    vcs_context: str = "",
    active_project: str = "",
    project_brief: str = "",
    project_meta_path: str = "",
) -> PromptBuildResult:
    """Build the full system prompt plus diagnostics."""

    source_result = load_prompt_sources(sandbox_root=sandbox_root)
    sections: list[PromptSection] = list(source_result.sections)

    behavior_text = source_result.text.strip()
    if not behavior_text:
        fallback = (
            "You are MindshardAGENT, a helpful assistant running inside the "
            "Mindshard sandbox workspace."
        )
        sections.append(PromptSection(name="fallback_identity", layer="runtime", content=fallback))

    tool_defs = tools.to_schema_list()
    tool_section = _format_tool_section(tool_defs)

    if docker_mode:
        os_section = get_command_teaching("", docker_mode=True)
    elif command_policy:
        os_section = get_command_teaching(command_policy.get_command_reference(), docker_mode=False)
    else:
        os_section = ""

    env_block = _format_environment_block(
        sandbox_root=sandbox_root,
        session_title=session_title,
        model_name=model_name,
        docker_mode=docker_mode,
    )
    project_focus = _format_project_focus_section(active_project)
    brief_section = _format_brief_section(project_brief)
    tools_block = f"## Available Tools\n{tool_section}"
    tool_rules_block = _tool_rules_block()
    tool_creation_block = _tool_creation_block()
    tool_call_block = _tool_call_block()
    journal_block = _format_journal_section(journal_context)
    vcs_block = _format_vcs_section(vcs_context)
    rag_block = _format_rag_section(rag_context)

    _append_section(sections, "environment", "runtime", env_block)
    _append_section(sections, "project_focus", "runtime", project_focus)
    _append_section(sections, "project_brief", "project_meta", brief_section, project_meta_path)
    _append_section(sections, "os_knowledge", "runtime", os_section)
    _append_section(sections, "available_tools", "runtime", tools_block)
    _append_section(sections, "tool_rules", "runtime", tool_rules_block)
    _append_section(sections, "tool_creation", "runtime", tool_creation_block)
    _append_section(sections, "tool_call_examples", "runtime", tool_call_block)
    _append_section(sections, "journal", "runtime", journal_block)
    _append_section(sections, "vcs", "runtime", vcs_block)
    _append_section(sections, "rag", "runtime", rag_block)

    prompt = "\n\n".join(section.content.strip() for section in sections if section.content.strip()) + "\n"
    prompt_fingerprint = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return PromptBuildResult(
        prompt=prompt,
        sections=tuple(sections),
        source_fingerprint=source_result.fingerprint,
        prompt_fingerprint=prompt_fingerprint,
        warnings=source_result.warnings,
    )


def build_system_prompt(
    sandbox_root: str,
    tools: ToolCatalog,
    command_policy: CommandPolicy | None = None,
    session_title: str = "",
    model_name: str = "",
    rag_context: str = "",
    docker_mode: bool = False,
    journal_context: str = "",
    vcs_context: str = "",
    active_project: str = "",
    project_brief: str = "",
) -> str:
    """Compatibility wrapper returning only the prompt text."""

    return build_system_prompt_bundle(
        sandbox_root=sandbox_root,
        tools=tools,
        command_policy=command_policy,
        session_title=session_title,
        model_name=model_name,
        rag_context=rag_context,
        docker_mode=docker_mode,
        journal_context=journal_context,
        vcs_context=vcs_context,
        active_project=active_project,
        project_brief=project_brief,
    ).prompt


def _append_section(
    sections: list[PromptSection],
    name: str,
    layer: str,
    content: str,
    source_path: str = "",
) -> None:
    if content and content.strip():
        sections.append(PromptSection(name=name, layer=layer, content=content, source_path=source_path))


def _format_tool_section(tool_defs: list[dict[str, Any]]) -> str:
    lines = []
    for tool_def in tool_defs:
        lines.append(f"### {tool_def['name']}")
        lines.append(f"{tool_def['description']}")
        if tool_def.get("parameters"):
            lines.append("Parameters:")
            for pname, pinfo in tool_def["parameters"].items():
                req = " (required)" if pinfo.get("required") else ""
                lines.append(f"  - {pname}: {pinfo.get('description', '')}{req}")
        lines.append("")
    return "\n".join(lines).strip()


def _format_environment_block(
    *,
    sandbox_root: str,
    session_title: str,
    model_name: str,
    docker_mode: bool,
) -> str:
    if docker_mode:
        return f"""## Your Environment
- Sandbox root: /sandbox
- Session: {session_title or 'unnamed'}
- Model: {model_name or 'unknown'}
- Operating system: Linux (Docker container)
- Shell: bash
- Python: python / python3 (both work)
- Package manager: pip (available)

## Sandbox Rules
- You are inside a Docker container. The container IS your sandbox.
- All files are under /sandbox.
- You have full bash access; most Linux commands work.
- pip install is available for Python packages.
- Reusable agent tools must live under `.mindshard/tools/`.
"""

    return f"""## Your Environment
- Sandbox root: {sandbox_root}
- Session: {session_title or 'unnamed'}
- Model: {model_name or 'unknown'}
- Operating system: Windows 10
- Shell: Command Prompt (cmd) with some Git Bash commands available

## Sandbox Rules
- You may ONLY read and write files within the sandbox root directory.
- You may NOT access files outside the sandbox.
- All CLI commands execute within the sandbox boundary.
- Only allowlisted commands may be used. Blocked commands will be rejected.
- Reusable agent tools must live under `.mindshard\\tools\\`.
"""


def _format_project_focus_section(active_project: str = "") -> str:
    if active_project:
        project_root = f"`{active_project}/`"
        explore_hint = f'`list_files` with `path="{active_project}"`'
    else:
        project_root = "sandbox root"
        explore_hint = '`list_files` with `path=""`'

    return f"""## Project Focus
- Active project root: {project_root}
- Start file exploration with: {explore_hint}
"""


def _format_brief_section(brief: str) -> str:
    return brief.strip()


def _tool_rules_block() -> str:
    return """## CRITICAL: Tool Selection Rules

| Task | Correct Tool | WRONG (never do this) |
|------|-------------|----------------------|
| Create/write a file | write_file | ~~echo ... > file~~ |
| Read a file | read_file | ~~type file~~ ~~cat file~~ |
| Run a program | cli_in_sandbox | — |
| List/explore files | list_files | ~~dir~~ ~~ls~~ |
| Create a directory | cli_in_sandbox | — |
| Create a reusable tool | write_file to .mindshard/tools/ + reload_tools | — |
| Check available tools | reload_tools | — |

NEVER use echo, python -c, or any CLI command to create files.
NEVER use type, cat, or any CLI command to read files.
ALWAYS use write_file to create files. ALWAYS use read_file to read files.
"""


def _tool_creation_block() -> str:
    return """## Creating New Tools (Self-Expansion)

You can extend your own capabilities by creating tools in `.mindshard/tools/`.

### Tool file format (REQUIRED docstring)
```
\"\"\"
Tool: my_tool_name
Description: One-line description of what this tool does
Parameters: param1:string:required, param2:string, count:int
\"\"\"
import json, sys

def main(params):
    # Your tool logic here
    result = params.get("param1", "")
    return {"result": result, "success": True}

if __name__ == "__main__":
    params = {}
    for i, arg in enumerate(sys.argv):
        if arg == "--json" and i + 1 < len(sys.argv):
            params = json.loads(sys.argv[i + 1])
            break
    output = main(params)
    print(json.dumps(output))
```

### Tool creation workflow
1. Use `write_file` to create `.mindshard/tools/<tool_name>.py`.
2. Call `reload_tools` to register it immediately.
3. Call the new tool like any other `tool_call`.

### Example: Create and use a new tool
Step 1 — Write the tool:
```tool_call
{"tool": "write_file", "path": ".mindshard/tools/count_lines.py", "content": "\"\"\"\\nTool: count_lines\\nDescription: Count lines in a file\\nParameters: path:string:required\\n\"\"\"\\nimport json, sys\\nfrom pathlib import Path\\n\\ndef main(params):\\n    p = Path(params[\\"path\\"])\\n    if not p.exists():\\n        return {\\\"error\\\": \\\"not found\\\", \\\"success\\\": False}\\n    lines = p.read_text(encoding=\\"utf-8\\").splitlines()\\n    return {\\\"count\\\": len(lines), \\\"path\\\": str(p), \\\"success\\\": True}\\n\\nif __name__ == \\"__main__\\":\\n    params = {}\\n    for i, arg in enumerate(sys.argv):\\n        if arg == \\"--json\\" and i + 1 < len(sys.argv):\\n            params = json.loads(sys.argv[i + 1])\\n            break\\n    print(json.dumps(main(params)))\\n"}
```
Step 2 — Register it:
```tool_call
{"tool": "reload_tools"}
```
Step 3 — Use it:
```tool_call
{"tool": "count_lines", "path": "my_project/src/main.py"}
```
"""


def _tool_call_block() -> str:
    return """## How to Call Tools

Wrap a JSON object in triple-backtick `tool_call` fences. One tool call per block.

### Example: Create a Python file
```tool_call
{"tool": "write_file", "path": "hello_app/src/hello.py", "content": "import tkinter as tk\\n\\nroot = tk.Tk()\\nroot.title('Hello')\\nlabel = tk.Label(root, text='HELLO WORLD!', font=('Arial', 48), fg='pink', bg='black')\\nlabel.pack(expand=True, fill='both')\\nroot.mainloop()\\n"}
```

### Example: Read a file
```tool_call
{"tool": "read_file", "path": "hello_app/src/hello.py"}
```

### Example: Run a program
```tool_call
{"tool": "cli_in_sandbox", "command": "python hello_app/src/hello.py"}
```

### Example: Append to a file
```tool_call
{"tool": "write_file", "path": "hello_app/logs/build.log", "content": "new entry\\n", "mode": "append"}
```

### Example: List files in sandbox root
```tool_call
{"tool": "list_files", "path": "", "depth": 2}
```

### Example: List files in a specific folder
```tool_call
{"tool": "list_files", "path": "my_project/src"}
```

## Tool Call Rules
- In `write_file` content: use `\\n` for newlines, `\\t` for tabs, `\\\\` for backslash, `\\"` for quotes.
- Only one tool call per `tool_call` block.
- You may include explanation text before and after tool call blocks.
- Wait for tool results before making your next tool call.
- To create and run a script: FIRST use `write_file`, THEN use `cli_in_sandbox` to run it.
"""


def _format_journal_section(journal_context: str) -> str:
    if not journal_context:
        return ""
    return f"""## Recent Workspace Activity
The following actions happened recently in this workspace. Use this to orient
yourself and understand the current state of work.

{journal_context}
"""


def _format_vcs_section(vcs_context: str) -> str:
    if not vcs_context:
        return ""
    return f"""## Version History (recent snapshots)
This workspace uses local git versioning (`.mindshard/vcs/`). Recent commits:

{vcs_context}
"""


def _format_rag_section(rag_context: str) -> str:
    if not rag_context:
        return ""
    return f"""## Relevant Context (from session knowledge)
The following information was retrieved from previous interactions and may be
relevant to the current conversation. Use it if helpful, but do not mention
that you are reading from a knowledge base.

{rag_context}
"""


def build_messages(
    system_prompt: str,
    chat_history: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Assemble the full message list for the Ollama API."""
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(chat_history)
    return messages
