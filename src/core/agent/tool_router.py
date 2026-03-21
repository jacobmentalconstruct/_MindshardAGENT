"""Tool router — parses model output for tool call requests and dispatches.

Scans assistant response text for ```tool_call blocks, validates the tool
name and parameters, and routes to the appropriate handler.
"""

import json
import re
from typing import Any

from src.core.sandbox.tool_catalog import ToolCatalog
from src.core.sandbox.cli_runner import CLIRunner
from src.core.sandbox.file_writer import FileWriter
from src.core.sandbox.python_runner import PythonRunner
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.runtime_logger import get_logger

log = get_logger("tool_router")

_TOOL_CALL_RE = re.compile(
    r"```tool_call\s*\n(.*?)\n```",
    re.DOTALL,
)


class ToolRouter:
    """Parse and dispatch tool calls from model responses."""

    def __init__(self, catalog: ToolCatalog, cli: CLIRunner, activity: ActivityStream,
                 file_writer: FileWriter | None = None, sandbox_root: str = "",
                 on_tools_reloaded=None, python_runner: PythonRunner | None = None):
        self._catalog = catalog
        self._cli = cli
        self._file_writer = file_writer
        self._activity = activity
        self._sandbox_root = sandbox_root
        self._on_tools_reloaded = on_tools_reloaded  # callback(count, names)
        self._python_runner = python_runner

    def extract_tool_calls(self, text: str) -> list[dict[str, Any]]:
        """Extract tool_call JSON blocks from assistant text."""
        calls = []
        for match in _TOOL_CALL_RE.finditer(text):
            raw = match.group(1).strip()
            try:
                parsed = json.loads(raw)
                calls.append(parsed)
            except json.JSONDecodeError:
                log.warning("Failed to parse tool call JSON: %s", raw[:200])
                self._activity.warn("tool_router", f"Malformed tool call: {raw[:100]}")
        return calls

    def has_tool_calls(self, text: str) -> bool:
        return bool(_TOOL_CALL_RE.search(text))

    def execute(self, tool_call: dict[str, Any]) -> dict[str, Any]:
        """Validate and execute a single tool call.

        Returns dict with: tool_name, success, result (or error).
        """
        tool_name = tool_call.get("tool", "")
        entry = self._catalog.get(tool_name)

        if not entry:
            msg = f"Unknown tool: {tool_name}"
            log.warning(msg)
            self._activity.warn("tool_router", msg)
            return {"tool_name": tool_name, "success": False, "error": msg}

        if tool_name == "cli_in_sandbox":
            command = tool_call.get("command", "")
            cwd = tool_call.get("cwd", None)
            if not command:
                return {"tool_name": tool_name, "success": False, "error": "No command provided"}

            result = self._cli.run(command, cwd=cwd)
            return {
                "tool_name": tool_name,
                "success": result["exit_code"] == 0,
                "result": result,
            }

        if tool_name == "write_file":
            if not self._file_writer:
                return {"tool_name": tool_name, "success": False, "error": "File writer not initialized"}
            path = tool_call.get("path", "")
            content = tool_call.get("content", "")
            mode = tool_call.get("mode", "write")
            if not path:
                return {"tool_name": tool_name, "success": False, "error": "No path provided"}
            if not content and mode != "write":
                return {"tool_name": tool_name, "success": False, "error": "No content provided"}

            result = self._file_writer.write_file(path, content, mode=mode)

            # Auto-reload tools if a file was written to .mindshard/tools/
            if result.get("success") and self._sandbox_root and (
                    ".mindshard/tools/" in path.replace("\\", "/") or
                    ".mindshard\\tools\\" in path):
                self._auto_reload_tools()

            return {
                "tool_name": tool_name,
                "success": result["success"],
                "result": result,
            }

        if tool_name == "read_file":
            if not self._file_writer:
                return {"tool_name": tool_name, "success": False, "error": "File reader not initialized"}
            path = tool_call.get("path", "")
            if not path:
                return {"tool_name": tool_name, "success": False, "error": "No path provided"}

            result = self._file_writer.read_file(path)
            return {
                "tool_name": tool_name,
                "success": result["success"],
                "result": result,
            }

        if tool_name == "list_files":
            if not self._file_writer:
                return {"tool_name": tool_name, "success": False, "error": "File writer not initialized"}
            path = tool_call.get("path", "")
            depth = int(tool_call.get("depth", 3))
            result = self._file_writer.list_files(path, depth=depth)
            return {
                "tool_name": tool_name,
                "success": result["success"],
                "result": result,
            }

        if tool_name == "run_python_file":
            if not self._python_runner:
                return {"tool_name": tool_name, "success": False, "error": "Python runner not initialized"}
            path = tool_call.get("path", "")
            args = tool_call.get("args", [])
            cwd = tool_call.get("cwd", None)
            timeout = tool_call.get("timeout", None)
            workspace = tool_call.get("workspace", None)
            if not path:
                return {"tool_name": tool_name, "success": False, "error": "No path provided"}
            if isinstance(args, str):
                args = [args]
            if args is None:
                args = []
            if not isinstance(args, list):
                return {"tool_name": tool_name, "success": False, "error": "args must be a list of strings"}

            result = self._python_runner.run_file(
                path,
                args=args,
                cwd=cwd,
                timeout=timeout,
                workspace=workspace,
            )
            return {
                "tool_name": tool_name,
                "success": result["exit_code"] == 0,
                "result": result,
            }

        if tool_name == "reload_tools":
            if not self._sandbox_root:
                return {"tool_name": tool_name, "success": False,
                        "error": "No sandbox root configured"}
            names = self._catalog.reload_sandbox_tools(self._sandbox_root)
            self._activity.tool("tool_router",
                f"Tools reloaded: {len(names)} sandbox tool(s) available")
            if names:
                summary = f"Reloaded. Sandbox tools now available: {', '.join(names)}"
            else:
                summary = "Reloaded. No sandbox tools found in .mindshard/tools/ yet."
            if self._on_tools_reloaded:
                self._on_tools_reloaded(len(names), names)
            return {
                "tool_name": tool_name,
                "success": True,
                "result": {"summary": summary, "tools": names},
            }

        # Sandbox-local tool: execute Python script via CLI
        if entry.source == "sandbox_local":
            return self._execute_sandbox_tool(tool_name, tool_call, entry)

        return {"tool_name": tool_name, "success": False, "error": f"No handler for tool: {tool_name}"}

    def _execute_sandbox_tool(self, tool_name: str, tool_call: dict[str, Any],
                               entry) -> dict[str, Any]:
        """Execute a sandbox-local tool by running its Python script via CLI.

        The script is invoked as: python .mindshard/tools/<callable_name>.py --json '<params>'
        Parameters are passed as a JSON string on stdin or as a --json argument.
        """
        import json as _json
        params = {k: v for k, v in tool_call.items() if k != "tool"}
        params_json = _json.dumps(params)
        # Escape for shell
        escaped = params_json.replace("'", "'\"'\"'")
        command = f"python .mindshard/tools/{entry.callable_name}.py --json '{escaped}'"
        self._activity.tool("tool_router", f"Sandbox tool: {tool_name}")
        result = self._cli.run(command)
        return {
            "tool_name": tool_name,
            "success": result["exit_code"] == 0,
            "result": result,
        }

    def _auto_reload_tools(self) -> None:
        """Silently reload sandbox tools after a write to .mindshard/tools/."""
        try:
            names = self._catalog.reload_sandbox_tools(self._sandbox_root)
            if names:
                self._activity.tool("tool_router",
                    f"Auto-registered new tool(s): {', '.join(names)}")
            if self._on_tools_reloaded:
                self._on_tools_reloaded(len(names), names)
        except Exception as e:
            log.warning("Auto tool reload failed: %s", e)

    def execute_all(self, text: str) -> list[dict[str, Any]]:
        """Extract and execute all tool calls in a response."""
        calls = self.extract_tool_calls(text)
        results = []
        for call in calls:
            result = self.execute(call)
            results.append(result)
        return results
