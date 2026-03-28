"""Tool catalog — registry of built-in, official, sandbox-local, and toolbox tools.

Built-in tools: cli_in_sandbox, write_file, read_file, replace_in_file,
replace_lines, list_files, run_python_file, reload_tools
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
    source: str          # "builtin", "official", "sandbox_local", "toolbox"
    callable_name: str   # internal dispatch key
    parameters: dict[str, Any] = field(default_factory=dict)
    script_path: str = ""


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
    description="Read the contents of a file within the sandbox. Can return the full file "
                "or a numbered/whitespace-aware line window for precise editing work. "
                "Use this instead of cat/type.",
    source="builtin",
    callable_name="read_file",
    parameters={
        "path": {"type": "string", "description": "File path relative to sandbox root", "required": True},
        "start_line": {"type": "integer", "description": "Optional first line to read (1-based, inclusive)"},
        "end_line": {"type": "integer", "description": "Optional last line to read (1-based, inclusive)"},
        "line_numbers": {"type": "boolean", "description": "Include stable line-number prefixes (default: false)"},
        "show_whitespace": {"type": "boolean", "description": "Visualize indentation/tabs/trailing spaces (default: false)"},
    },
)

REPLACE_IN_FILE = ToolEntry(
    name="replace_in_file",
    description="Replace exact literal text inside an existing file. "
                "Use this when you know the exact target snippet and want a surgical edit "
                "with before/after verification excerpts.",
    source="builtin",
    callable_name="replace_in_file",
    parameters={
        "path": {"type": "string", "description": "File path relative to sandbox root", "required": True},
        "old_text": {"type": "string", "description": "Exact existing text to replace", "required": True},
        "new_text": {"type": "string", "description": "Replacement text", "required": True},
        "expected_count": {"type": "integer", "description": "Expected number of literal matches (default: 1)"},
        "replace_all": {"type": "boolean", "description": "Replace all exact matches instead of only one (default: false)"},
        "context_lines": {"type": "integer", "description": "How many surrounding lines to include in before/after excerpts (default: 2)"},
    },
)

REPLACE_LINES = ToolEntry(
    name="replace_lines",
    description="Replace an inclusive line range inside an existing file. "
                "Use this when exact text matching is brittle because of indentation, repeated snippets, "
                "or whitespace-sensitive formatting.",
    source="builtin",
    callable_name="replace_lines",
    parameters={
        "path": {"type": "string", "description": "File path relative to sandbox root", "required": True},
        "start_line": {"type": "integer", "description": "First line to replace (1-based, inclusive)", "required": True},
        "end_line": {"type": "integer", "description": "Last line to replace (1-based, inclusive)", "required": True},
        "new_text": {"type": "string", "description": "Replacement text for the requested line span", "required": True},
        "context_lines": {"type": "integer", "description": "How many surrounding lines to include in before/after excerpts (default: 2)"},
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
    description="Re-scan discovered tool roots and register any new or updated tools. "
                "Call this after writing a tool script so you can use it immediately. "
                "Returns the list of currently available discovered tools.",
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
        self.register(REPLACE_IN_FILE)
        self.register(REPLACE_LINES)
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

    def clear_discovered_tools(self) -> int:
        """Remove all non-builtin tools (sandbox_local, toolbox, etc.).

        Called before re-discovery on sandbox/toolbox switches so that tools
        from the previous project don't linger in the catalog.

        Returns count of tools removed.
        """
        stale = [name for name, entry in self._tools.items()
                 if entry.source != "builtin"]
        for name in stale:
            del self._tools[name]
        if stale:
            log.info("Cleared %d discovered tool(s): %s", len(stale), stale)
        return len(stale)

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

    def discovered_tool_names(self) -> list[str]:
        """Return names of all non-builtin tools currently registered."""
        return [name for name, e in self._tools.items() if e.source != "builtin"]

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
