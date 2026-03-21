"""Tool catalog — registry of built-in, official, and sandbox-local tools.

Built-in tools: cli_in_sandbox, write_file, read_file, list_files,
run_python_file, reload_tools
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

LIST_FILES = ToolEntry(
    name="list_files",
    description="List files and directories within the sandbox as a structured JSON tree. "
                "Use this to explore the workspace — much better than running dir or ls.",
    source="builtin",
    callable_name="list_files",
    parameters={
        "path": {"type": "string", "description": "Directory path relative to sandbox root (empty = root)"},
        "depth": {"type": "integer", "description": "How many levels deep to recurse (default: 3)"},
    },
)

RUN_PYTHON_FILE = ToolEntry(
    name="run_python_file",
    description="Run a Python file located inside the sandbox without using freeform shell. "
                "Use this for testing scripts or apps. By default it runs in a disposable copied workspace "
                "under .mindshard/runs/ so experiments do not mutate the live project. "
                "Local GUI launches may ask for approval; Docker mode blocks GUI windows.",
    source="builtin",
    callable_name="run_python_file",
    parameters={
        "path": {"type": "string", "description": "Python file path relative to sandbox root", "required": True},
        "args": {"type": "array", "description": "Optional list of string arguments to pass to the script"},
        "cwd": {"type": "string", "description": "Optional working directory relative to sandbox root"},
        "timeout": {"type": "integer", "description": "Optional timeout in seconds (1-120, default: 30)"},
        "workspace": {"type": "string", "description": "Execution workspace: 'run_copy' (default, disposable snapshot) or 'sandbox' (live project)"},
    },
)

RELOAD_TOOLS = ToolEntry(
    name="reload_tools",
    description="Re-scan .mindshard/tools/ and register any new or updated sandbox tools. "
                "Call this after writing a new tool script so you can use it immediately. "
                "Returns the list of currently available sandbox tools.",
    source="builtin",
    callable_name="reload_tools",
    parameters={},
)


class ToolCatalog:
    """Registry of available tools."""

    def __init__(self):
        self._tools: dict[str, ToolEntry] = {}
        self.register(CLI_IN_SANDBOX)
        self.register(WRITE_FILE)
        self.register(READ_FILE)
        self.register(LIST_FILES)
        self.register(RUN_PYTHON_FILE)
        self.register(RELOAD_TOOLS)

    def register(self, entry: ToolEntry) -> None:
        self._tools[entry.name] = entry
        log.info("Tool registered: %s (%s)", entry.name, entry.source)

    def get(self, name: str) -> ToolEntry | None:
        return self._tools.get(name)

    def list_tools(self) -> list[ToolEntry]:
        return list(self._tools.values())

    def reload_sandbox_tools(self, sandbox_root: str) -> list[str]:
        """Clear all sandbox_local tools and re-discover from .mindshard/tools/.

        Returns list of newly registered tool names.
        """
        from src.core.sandbox.tool_discovery import discover_tools
        # Remove all previously registered sandbox tools
        stale = [name for name, entry in self._tools.items()
                 if entry.source == "sandbox_local"]
        for name in stale:
            del self._tools[name]
        # Re-discover and register
        entries = discover_tools(sandbox_root)
        for entry in entries:
            self.register(entry)
        names = [e.name for e in entries]
        log.info("Reloaded sandbox tools: %s", names or "none")
        return names

    def sandbox_tool_names(self) -> list[str]:
        """Return names of all currently registered sandbox_local tools."""
        return [name for name, e in self._tools.items() if e.source == "sandbox_local"]

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
