"""
FILE: tk_ui_event_map.py
ROLE: Agent-facing Tkinter callback graph mapper.
WHAT IT DOES: Maps Tkinter command callbacks, binds, protocol handlers, scheduled callbacks, and worker-thread starts into a structured event graph.
HOW TO USE:
  - Metadata: python .final-tools/tools/tk_ui_event_map.py metadata
  - Run: python .final-tools/tools/tk_ui_event_map.py run --input-json "{\"root\": \"path/to/project\"}"
INPUT OBJECT:
  - root: folder to scan
  - top_n: optional summary size
  - include_files: optional list of file suffix filters, defaults to Python only
"""

from __future__ import annotations

import ast
import sys
from collections import Counter
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result
from lib.tk_ast import TkFileAnalyzer, iter_python_files, relative_path, resolve_callback


FILE_METADATA = {
    "tool_name": "tk_ui_event_map",
    "version": "1.0.0",
    "entrypoint": "tools/tk_ui_event_map.py",
    "category": "ui",
    "summary": "Map Tkinter events and callback edges across a Python project.",
    "mcp_name": "tk_ui_event_map",
    "legacy_replaces": [],
    "input_schema": {
        "type": "object",
        "properties": {
            "root": {"type": "string", "description": "Folder to scan."},
            "top_n": {"type": "integer", "default": 200},
            "include_files": {
                "type": "array",
                "items": {"type": "string"},
                "default": [".py"]
            }
        },
        "required": ["root"],
        "additionalProperties": False
    }
}


def _edge(path: Path, root: Path, edge_type: str, item: dict, resolved: dict | None) -> dict:
    payload = {
        "file": relative_path(path, root),
        "line": item["line"],
        "edge_type": edge_type,
        "class": item.get("class"),
        "function": item.get("function"),
        "target": item.get("target") or item.get("widget_names") or [],
        "callback": item.get("callback") or item.get("target"),
    }
    if "event" in item:
        payload["event"] = item.get("event")
    if "protocol" in item:
        payload["protocol"] = item.get("protocol")
    if "widget_type" in item:
        payload["widget_type"] = item.get("widget_type")
    if "delay_ms" in item:
        payload["delay_ms"] = item.get("delay_ms")
    if resolved:
        payload["resolved_callback"] = {
            "qualname": resolved["qualname"],
            "line": resolved["line"],
            "class": resolved.get("class"),
        }
    return payload


def run(arguments: dict) -> dict:
    root = Path(arguments["root"]).resolve()
    top_n = int(arguments.get("top_n", 200))
    include_files = list(arguments.get("include_files", [".py"]))

    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Directory not found: {root}")

    files_scanned = 0
    edges = []

    for path in iter_python_files(root, include_files):
        files_scanned += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue

        analyzer = TkFileAnalyzer(path)
        analyzer.visit(tree)
        if not analyzer.imports_tkinter and not analyzer.has_tkinter_usage and not analyzer.thread_targets:
            continue

        for item in analyzer.command_callbacks:
            resolved = resolve_callback(analyzer.functions, item.get("callback", ""), item.get("class"))
            edges.append(_edge(path, root, "command", item, resolved))
        for item in analyzer.bind_calls:
            resolved = resolve_callback(analyzer.functions, item.get("callback", ""), item.get("class"))
            edges.append(_edge(path, root, "bind", item, resolved))
        for item in analyzer.schedule_calls:
            resolved = resolve_callback(analyzer.functions, item.get("callback", ""), item.get("class"))
            edges.append(_edge(path, root, "schedule", item, resolved))
        for item in analyzer.protocol_calls:
            resolved = resolve_callback(analyzer.functions, item.get("callback", ""), item.get("class"))
            edges.append(_edge(path, root, "protocol", item, resolved))
        for item in analyzer.thread_targets:
            resolved = resolve_callback(analyzer.functions, item.get("target", ""), item.get("class"))
            edges.append(_edge(path, root, "thread_start", item, resolved))

    counts_by_type = Counter(item["edge_type"] for item in edges)
    counts_by_callback = Counter((item.get("resolved_callback") or {}).get("qualname") or item.get("callback") or "<unknown>" for item in edges)
    counts_by_event = Counter(str(item.get("event") or item.get("protocol") or "<none>") for item in edges if item["edge_type"] in {"bind", "protocol"})

    result = {
        "root": str(root),
        "files_scanned": files_scanned,
        "edge_count": len(edges),
        "summary": {
            "counts_by_type": dict(counts_by_type.most_common(top_n)),
            "top_callbacks": dict(counts_by_callback.most_common(top_n)),
            "top_events": dict(counts_by_event.most_common(top_n)),
        },
        "edges": edges[:top_n],
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
