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
) -> str:
    """Build the system prompt for the agent."""

    tool_defs = tools.to_schema_list()
    tool_section = _format_tool_section(tool_defs)

    # Build the OS + command knowledge section
    if command_policy:
        cmd_ref = command_policy.get_command_reference()
        os_section = get_command_teaching(cmd_ref)
    else:
        os_section = ""

    return f"""You are a helpful assistant running inside the AgenticTOOLBOX sandbox environment.

## Your Environment
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
- If you create tools, they must go under the sandbox's _tools/ directory.

{os_section}

## Available Tools
{tool_section}

## How to Use Tools
When you need to run a CLI command, respond with a JSON tool call block:
```tool_call
{{"tool": "cli_in_sandbox", "command": "<your shell command>", "cwd": "<optional relative path>"}}
```

Important:
- Only use registered tools listed above.
- Only use allowed commands listed in the command reference above.
- CLI commands run inside the sandbox root.
- Include the tool_call block on its own line.
- You may include explanation before and after tool calls.
- Wait for tool results before continuing when appropriate.
- Created tools must be placed under _tools/ with clear documentation headers.
- If a command is blocked, try a different allowed command instead.

## Response Style
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


def build_messages(
    system_prompt: str,
    chat_history: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Assemble the full message list for the Ollama API."""
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(chat_history)
    return messages
