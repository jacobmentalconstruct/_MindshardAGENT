"""Tool catalog — registry of built-in, official, and sandbox-local tools.

Built-in tools: cli_in_sandbox, write_file, read_file
"""

from dataclasses import dataclass, field
from typing import Any

from src.core.runtime.runtime_logger import get_logger

log = get_logger("tool_catalog")


@dataclass
class ToolEntry:
    """Metadata for a registered tool."""
    name: str
    description: str
    source: str          # "builtin", "official", "sandbox_local"
    callable_name: str   # internal dispatch key
    parameters: dict[str, Any] = field(default_factory=dict)


# Built-in tool definition
CLI_IN_SANDBOX = ToolEntry(
    name="cli_in_sandbox",
    description="Execute a CLI command within the sandbox root directory. "
                "The command runs in a subprocess with stdout/stderr capture.",
    source="builtin",
    callable_name="cli_in_sandbox",
    parameters={
        "command": {"type": "string", "description": "The shell command to execute", "required": True},
        "cwd": {"type": "string", "description": "Working directory relative to sandbox root (optional)"},
    },
)


WRITE_FILE = ToolEntry(
    name="write_file",
    description="Create or overwrite a file within the sandbox. Handles multi-line content "
                "directly — no shell quoting needed. Use this instead of echo/python -c for "
                "creating files with code or multi-line text.",
    source="builtin",
    callable_name="write_file",
    parameters={
        "path": {"type": "string", "description": "File path relative to sandbox root", "required": True},
        "content": {"type": "string", "description": "The text content to write to the file", "required": True},
        "mode": {"type": "string", "description": "Write mode: 'write' (create/overwrite) or 'append' (add to end). Default: 'write'"},
    },
)

READ_FILE = ToolEntry(
    name="read_file",
    description="Read the contents of a file within the sandbox. Returns the full text content. "
                "Works reliably on all operating systems (use this instead of cat/type).",
    source="builtin",
    callable_name="read_file",
    parameters={
        "path": {"type": "string", "description": "File path relative to sandbox root", "required": True},
    },
)


class ToolCatalog:
    """Registry of available tools."""

    def __init__(self):
        self._tools: dict[str, ToolEntry] = {}
        self.register(CLI_IN_SANDBOX)
        self.register(WRITE_FILE)
        self.register(READ_FILE)

    def register(self, entry: ToolEntry) -> None:
        self._tools[entry.name] = entry
        log.info("Tool registered: %s (%s)", entry.name, entry.source)

    def get(self, name: str) -> ToolEntry | None:
        return self._tools.get(name)

    def list_tools(self) -> list[ToolEntry]:
        return list(self._tools.values())

    def to_schema_list(self) -> list[dict[str, Any]]:
        """Export tool definitions as JSON-schema-like dicts for prompt building."""
        result = []
        for t in self._tools.values():
            result.append({
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            })
        return result
