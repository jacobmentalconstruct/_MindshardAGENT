"""Transcript formatter — formats tool results for reinsertion into chat history."""

from typing import Any


def format_tool_result(tool_result: dict[str, Any]) -> str:
    """Format a tool execution result as a message for the model."""
    name = tool_result.get("tool_name", "unknown")
    success = tool_result.get("success", False)

    if not success:
        error = tool_result.get("error", "Unknown error")
        return f"[Tool '{name}' failed: {error}]"

    result = tool_result.get("result", {})
    parts = [f"[Tool '{name}' completed (exit code {result.get('exit_code', '?')})]"]

    stdout = result.get("stdout", "").strip()
    stderr = result.get("stderr", "").strip()

    if stdout:
        # Truncate very long output
        if len(stdout) > 2000:
            stdout = stdout[:2000] + "\n... (truncated)"
        parts.append(f"stdout:\n{stdout}")

    if stderr:
        if len(stderr) > 1000:
            stderr = stderr[:1000] + "\n... (truncated)"
        parts.append(f"stderr:\n{stderr}")

    return "\n".join(parts)


def format_all_results(results: list[dict[str, Any]]) -> str:
    """Format multiple tool results into a single message."""
    if not results:
        return ""
    return "\n\n".join(format_tool_result(r) for r in results)
