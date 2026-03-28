"""Transcript formatter — formats tool results and compacts tool-call transcripts."""

import json
import re
from typing import Any

_TOOL_CALL_RE = re.compile(
    r"```tool_call\s*\n(.*?)\n```",
    re.DOTALL,
)


def format_tool_result(tool_result: dict[str, Any]) -> str:
    """Format a tool execution result as a message for the model."""
    name = tool_result.get("tool_name", "unknown")
    success = tool_result.get("success", False)

    if not success:
        error = tool_result.get("error", "Unknown error")
        return f"[Tool '{name}' failed: {error}]"

    result = tool_result.get("result", {})

    # Handle file tool results — different shape than CLI
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
        start_line = result.get("start_line")
        end_line = result.get("end_line")
        # Truncate very long file content
        if len(content) > 3000:
            content = content[:3000] + "\n... (truncated)"
        if start_line and end_line:
            return f"[Tool '{name}' completed] {path} ({size} bytes, lines {start_line}-{end_line}):\n{content}"
        return f"[Tool '{name}' completed] {path} ({size} bytes):\n{content}"

    if name in {"replace_in_file", "replace_lines"}:
        path = result.get("path", "?")
        before_excerpt = result.get("before_excerpt", "")
        after_excerpt = result.get("after_excerpt", "")
        parts = [f"[Tool '{name}' completed] {path}"]
        if "replaced_count" in result:
            parts.append(f"replaced_count: {result.get('replaced_count')} (matched {result.get('match_count', '?')})")
        if "start_line" in result and "end_line" in result:
            parts.append(f"line_range: {result.get('start_line')}-{result.get('end_line')}")
        if before_excerpt:
            parts.append(f"before_excerpt:\n{before_excerpt}")
        if after_excerpt:
            parts.append(f"after_excerpt:\n{after_excerpt}")
        return "\n".join(parts)

    if name == "run_python_file":
        path = result.get("path", "?")
        exit_code = result.get("exit_code", "?")
        stdout = result.get("stdout", "").strip()
        stderr = result.get("stderr", "").strip()
        workspace_mode = result.get("workspace_mode", "sandbox")
        parts = [f"[Tool '{name}' completed] {path} (exit code {exit_code}, workspace={workspace_mode})"]
        if result.get("run_root"):
            parts.append(f"run_root:\n{result['run_root']}")
        if stdout:
            if len(stdout) > 2000:
                stdout = stdout[:2000] + "\n... (truncated)"
            parts.append(f"stdout:\n{stdout}")
        if stderr:
            if len(stderr) > 1000:
                stderr = stderr[:1000] + "\n... (truncated)"
            parts.append(f"stderr:\n{stderr}")
        return "\n".join(parts)

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


def strip_tool_call_markup(text: str) -> str:
    """Remove executable tool-call syntax from assistant-visible text.

    This keeps raw tool JSON and `TOOL_CALLS:` summary strings out of user-facing
    chat/history while preserving any surrounding prose the model wrote.
    """
    cleaned = _TOOL_CALL_RE.sub("", text or "")
    cleaned_lines = [
        line for line in cleaned.splitlines()
        if not line.strip().startswith("TOOL_CALLS:")
    ]
    compact = "\n".join(cleaned_lines)
    compact = re.sub(r"\n{3,}", "\n\n", compact)
    return compact.strip()


def compact_tool_call_transcript(text: str) -> str:
    """Replace verbose fenced tool-call JSON with a compact summary line."""

    summaries: list[str] = []
    prose_parts: list[str] = []
    last_end = 0

    for match in _TOOL_CALL_RE.finditer(text):
        prose = text[last_end:match.start()].strip()
        if prose:
            prose_parts.append(prose)

        raw = match.group(1).strip()
        try:
            tool_call = json.loads(raw)
            summaries.append(_format_tool_call(tool_call))
        except json.JSONDecodeError:
            summaries.append("tool_call(parse_error — model retrying)")
        last_end = match.end()

    tail = text[last_end:].strip()
    if tail:
        prose_parts.append(tail)

    if summaries:
        prose_parts.append("TOOL_CALLS: " + ", ".join(summaries))

    compact = "\n\n".join(part for part in prose_parts if part)
    return compact or text


def _format_tool_call(tool_call: dict[str, Any]) -> str:
    tool_name = str(tool_call.get("tool", "unknown"))
    params: list[str] = []
    for key, value in tool_call.items():
        if key == "tool":
            continue
        rendered = _compact_value(value)
        params.append(f"{key}:{rendered}")
    return f"{tool_name}({', '.join(params)})" if params else tool_name


def _compact_value(value: Any) -> str:
    if isinstance(value, str):
        compact = value.replace("\n", "\\n")
        return compact if len(compact) <= 60 else compact[:57] + "..."
    if isinstance(value, list):
        items = ", ".join(_compact_value(item) for item in value[:4])
        return f"[{items}{', ...' if len(value) > 4 else ''}]"
    if isinstance(value, dict):
        items = ", ".join(f"{k}:{_compact_value(v)}" for k, v in list(value.items())[:4])
        suffix = ", ..." if len(value) > 4 else ""
        return "{" + items + suffix + "}"
    return str(value)
