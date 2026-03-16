"""Tool catalog — registry of built-in, official, and sandbox-local tools.

Version 1 has one real built-in tool: cli_in_sandbox.
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


class ToolCatalog:
    """Registry of available tools."""

    def __init__(self):
        self._tools: dict[str, ToolEntry] = {}
        self.register(CLI_IN_SANDBOX)

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
