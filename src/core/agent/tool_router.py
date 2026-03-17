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
                 file_writer: FileWriter | None = None):
        self._catalog = catalog
        self._cli = cli
        self._file_writer = file_writer
        self._activity = activity

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

        return {"tool_name": tool_name, "success": False, "error": f"No handler for tool: {tool_name}"}

    def execute_all(self, text: str) -> list[dict[str, Any]]:
        """Extract and execute all tool calls in a response."""
        calls = self.extract_tool_calls(text)
        results = []
        for call in calls:
            result = self.execute(call)
            results.append(result)
        return results
