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

    # Handle file tool results (write_file, read_file) — different shape than CLI
    if name == "write_file":
        path = result.get("path", "?")
        bw = result.get("bytes_written", 0)
        action = result.get("action", "write")
        verb = "Appended to" if action == "append" else "Wrote"
        return f"[Tool '{name}' completed] {verb} {path} ({bw} bytes)"

    if name == "read_file":
        path = result.get("path", "?")
        content = result.get("content", "")
        size = result.get("size", 0)
        # Truncate very long file content
        if len(content) > 3000:
            content = content[:3000] + "\n... (truncated)"
        return f"[Tool '{name}' completed] {path} ({size} bytes):\n{content}"

    if name == "reload_tools":
        summary = result.get("summary", "Tools reloaded.")
        tools = result.get("tools", [])
        return f"[Tool '{name}' completed] {summary}"

    if name == "list_files":
        import json
        path = result.get("path", ".")
        tree = result.get("tree", [])

        def _render(entries, indent=0) -> list[str]:
            lines = []
            for entry in entries:
                prefix = "  " * indent
                if entry["type"] == "dir":
                    lines.append(f"{prefix}{entry['name']}/")
                    if "children" in entry:
                        lines.extend(_render(entry["children"], indent + 1))
                else:
                    size_kb = entry.get("size", 0) / 1024
                    lines.append(f"{prefix}{entry['name']}  ({size_kb:.1f}KB)")
            return lines

        rendered = "\n".join(_render(tree))
        return f"[Tool '{name}' completed] Directory: {path}\n{rendered}"

    # Default: CLI-style result with exit_code/stdout/stderr
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
