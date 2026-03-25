"""Tool router — parses model output for tool call requests and dispatches.

Scans assistant response text for ```tool_call blocks, validates the tool
name and parameters, and routes to the appropriate handler.
"""

import json
import re
import sys
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
                 on_tools_reloaded=None, reload_tools_fn=None,
                 python_runner: PythonRunner | None = None):
        self._catalog = catalog
        self._cli = cli
        self._file_writer = file_writer
        self._activity = activity
        self._sandbox_root = sandbox_root
        self._on_tools_reloaded = on_tools_reloaded  # callback(count, names)
        self._reload_tools_fn = reload_tools_fn
        self._python_runner = python_runner

    def extract_tool_calls(self, text: str) -> list[dict[str, Any]]:
        """Extract tool_call JSON blocks from assistant text.

        Malformed blocks (invalid JSON) are returned as sentinel dicts with
        ``tool="__malformed__"`` so that ``execute_all`` can report the failure
        back to the model explicitly rather than silently dropping the call.
        """
        calls = []
        for match in _TOOL_CALL_RE.finditer(text):
            raw = match.group(1).strip()
            try:
                parsed = json.loads(raw)
                calls.append(parsed)
            except json.JSONDecodeError as exc:
                log.warning("Failed to parse tool call JSON: %s", raw[:200])
                self._activity.warn("tool_router", f"Malformed tool call JSON: {raw[:100]}")
                # Return error sentinel — execute() will surface this to the model
                # so it knows to fix its format rather than assuming success.
                calls.append({
                    "tool": "__malformed__",
                    "_raw": raw[:300],
                    "_error": str(exc),
                })
        return calls

    def has_tool_calls(self, text: str) -> bool:
        return bool(_TOOL_CALL_RE.search(text))

    def execute(self, tool_call: dict[str, Any]) -> dict[str, Any]:
        """Validate and execute a single tool call.

        Returns dict with: tool_name, success, result (or error).
        """
        tool_name = tool_call.get("tool", "")

        # Malformed sentinel — JSON parse failed in extract_tool_calls()
        if tool_name == "__malformed__":
            raw = tool_call.get("_raw", "")
            err = tool_call.get("_error", "JSON parse error")
            msg = (
                f"Your tool call could not be parsed (invalid JSON). "
                f"Parse error: {err}. "
                f"Ensure the tool call block contains only valid JSON with no trailing commas, "
                f"comments, or unquoted strings. "
                f"Received: {raw[:150]}"
            )
            log.warning("Malformed tool call returned to model: %s", err)
            return {"tool_name": "tool_call", "success": False, "error": msg}

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
            names = self._reload_discovered_tools()
            self._activity.tool("tool_router",
                f"Tools reloaded: {len(names)} discovered tool(s) available")
            if names:
                summary = f"Reloaded. Discovered tools now available: {', '.join(names)}"
            else:
                summary = "Reloaded. No discovered tools found yet."
            if self._on_tools_reloaded and not self._reload_tools_fn:
                self._on_tools_reloaded(len(names), names)
            return {
                "tool_name": tool_name,
                "success": True,
                "result": {"summary": summary, "tools": names},
            }

        # Discovered Python tool: execute the registered script path directly.
        if entry.source != "builtin":
            return self._execute_script_tool(tool_name, tool_call, entry)

        return {"tool_name": tool_name, "success": False, "error": f"No handler for tool: {tool_name}"}

    def _execute_script_tool(self, tool_name: str, tool_call: dict[str, Any], entry) -> dict[str, Any]:
        """Execute a discovered Python tool by running its script directly.

        Uses subprocess.run with an explicit arg list (no shell=True) so that
        the JSON params string is passed as a single argv element without any
        platform-specific shell-quoting issues.  Single-quote escaping on
        Windows cmd.exe does not work, so we bypass the shell entirely here.
        """
        import json as _json
        import subprocess as _subprocess
        params = {k: v for k, v in tool_call.items() if k != "tool"}
        params_json = _json.dumps(params)

        script_path = entry.script_path or f".mindshard/tools/{entry.callable_name}.py"
        cmd = [sys.executable, script_path, "--json", params_json]

        self._activity.tool("tool_router", f"Tool: {tool_name}")
        log.info("Tool exec: %s source=%s path=%s", tool_name, entry.source, script_path)

        try:
            proc = _subprocess.run(
                cmd,
                cwd=self._sandbox_root or None,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return {
                "tool_name": tool_name,
                "success": proc.returncode == 0,
                "result": {
                    "exit_code": proc.returncode,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                },
            }
        except _subprocess.TimeoutExpired:
            return {"tool_name": tool_name, "success": False,
                    "error": "Tool timed out after 30s"}
        except Exception as exc:
            return {"tool_name": tool_name, "success": False, "error": str(exc)}

    def _auto_reload_tools(self) -> None:
        """Silently reload discovered tools after a write to .mindshard/tools/."""
        try:
            names = self._reload_discovered_tools()
            if names:
                self._activity.tool("tool_router",
                    f"Auto-registered new tool(s): {', '.join(names)}")
            if self._on_tools_reloaded and not self._reload_tools_fn:
                self._on_tools_reloaded(len(names), names)
        except Exception as e:
            log.warning("Auto tool reload failed: %s", e)

    def _reload_discovered_tools(self) -> list[str]:
        if self._reload_tools_fn:
            return list(self._reload_tools_fn())
        return self._catalog.reload_sandbox_tools(self._sandbox_root)

    def execute_all(self, text: str) -> list[dict[str, Any]]:
        """Extract and execute all tool calls in a response."""
        calls = self.extract_tool_calls(text)
        results = []
        for call in calls:
            result = self.execute(call)
            results.append(result)
        return results
