"""System prompt construction for the Ollama agent.

Composes the system prompt with:
  - agent identity and sandbox policy
  - OS fundamentals knowledge (what directories are, how shells work, etc.)
  - allowed command reference with usage examples
  - tool definitions and usage instructions
  - session context
"""

from typing import Any

from src.core.sandbox.tool_catalog import ToolCatalog
from src.core.sandbox.command_policy import CommandPolicy
from src.core.agent.os_knowledge import get_command_teaching


def build_system_prompt(
    sandbox_root: str,
    tools: ToolCatalog,
    command_policy: CommandPolicy | None = None,
    session_title: str = "",
    model_name: str = "",
    rag_context: str = "",
    docker_mode: bool = False,
    journal_context: str = "",
) -> str:
    """Build the system prompt for the agent."""

    tool_defs = tools.to_schema_list()
    tool_section = _format_tool_section(tool_defs)

    # Build the OS + command knowledge section
    if docker_mode:
        os_section = get_command_teaching("", docker_mode=True)
    elif command_policy:
        cmd_ref = command_policy.get_command_reference()
        os_section = get_command_teaching(cmd_ref, docker_mode=False)
    else:
        os_section = ""

    # Environment description changes based on mode
    if docker_mode:
        env_block = f"""## Your Environment
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
- You have full bash access — most Linux commands work.
- pip install is available for Python packages.
- If you create tools, they must go under _tools/ directory."""
    else:
        env_block = f"""## Your Environment
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
- If you create tools, they must go under the sandbox's _tools/ directory."""

    # List files example changes based on mode
    list_cmd = "ls -la" if docker_mode else "dir"

    return f"""You are a helpful assistant running inside the MindshardAGENT sandbox environment.

{env_block}

{os_section}

## Available Tools
{tool_section}

## CRITICAL: Tool Selection Rules

You have three tools. Pick the RIGHT one:

| Task | Correct Tool | WRONG (never do this) |
|------|-------------|----------------------|
| Create/write a file | write_file | ~~echo ... > file~~ |
| Read a file | read_file | ~~type file~~ ~~cat file~~ |
| Run a program | cli_in_sandbox | — |
| List files | cli_in_sandbox | — |
| Create a directory | cli_in_sandbox | — |

NEVER use echo, python -c, or any CLI command to create files.
NEVER use type, cat, or any CLI command to read files.
ALWAYS use write_file to create files. ALWAYS use read_file to read files.

## How to Call Tools

Wrap a JSON object in triple-backtick tool_call fences. One tool call per block.

### Example: Create a Python file
```tool_call
{{"tool": "write_file", "path": "hello.py", "content": "import tkinter as tk\\n\\nroot = tk.Tk()\\nroot.title('Hello')\\nlabel = tk.Label(root, text='HELLO WORLD!', font=('Arial', 48), fg='pink', bg='black')\\nlabel.pack(expand=True, fill='both')\\nroot.mainloop()\\n"}}
```

### Example: Read a file
```tool_call
{{"tool": "read_file", "path": "hello.py"}}
```

### Example: Run a program
```tool_call
{{"tool": "cli_in_sandbox", "command": "python hello.py"}}
```

### Example: Append to a file
```tool_call
{{"tool": "write_file", "path": "log.txt", "content": "new entry\\n", "mode": "append"}}
```

### Example: List files
```tool_call
{{"tool": "cli_in_sandbox", "command": "{list_cmd}"}}
```

## Tool Call Rules
- In write_file content: use \\n for newlines, \\t for tabs, \\\\ for backslash, \\" for quotes.
- Only one tool call per ```tool_call block.
- You may include explanation text before and after tool call blocks.
- Wait for tool results before making your next tool call.
- To create and run a script: FIRST use write_file, THEN use cli_in_sandbox to run it.

{_format_journal_section(journal_context)}{_format_rag_section(rag_context)}## Response Style
- Be helpful and direct.
- Show your reasoning when solving problems.
- When you don't know something, say so.
- Report errors clearly.
"""


def _format_tool_section(tool_defs: list[dict[str, Any]]) -> str:
    lines = []
    for t in tool_defs:
        lines.append(f"### {t['name']}")
        lines.append(f"{t['description']}")
        if t.get("parameters"):
            lines.append("Parameters:")
            for pname, pinfo in t["parameters"].items():
                req = " (required)" if pinfo.get("required") else ""
                lines.append(f"  - {pname}: {pinfo.get('description', '')}{req}")
        lines.append("")
    return "\n".join(lines)


def _format_journal_section(journal_context: str) -> str:
    """Format recent action journal for injection into system prompt."""
    if not journal_context:
        return ""
    return f"""## Recent Workspace Activity
The following actions happened recently in this workspace. Use this to orient
yourself and understand the current state of work.

{journal_context}

"""


def _format_rag_section(rag_context: str) -> str:
    """Format retrieved knowledge context for injection into the system prompt."""
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
