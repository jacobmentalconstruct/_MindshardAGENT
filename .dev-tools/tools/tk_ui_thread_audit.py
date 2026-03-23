"""
FILE: tk_ui_thread_audit.py
ROLE: Agent-facing Tkinter thread-safety auditor.
WHAT IT DOES: Audits Tkinter code for UI callbacks that may block the main thread and worker-thread targets that appear to touch UI state directly.
HOW TO USE:
  - Metadata: python .final-tools/tools/tk_ui_thread_audit.py metadata
  - Run: python .final-tools/tools/tk_ui_thread_audit.py run --input-json "{\"root\": \"path/to/project\"}"
INPUT OBJECT:
  - root: folder to scan
  - top_n: optional finding cap
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
from lib.tk_ast import TkFileAnalyzer, call_is_blocking, call_touches_ui, iter_python_files, relative_path, resolve_callback


FILE_METADATA = {
    "tool_name": "tk_ui_thread_audit",
    "version": "1.0.0",
    "entrypoint": "tools/tk_ui_thread_audit.py",
    "category": "ui",
    "summary": "Audit Tkinter callbacks and worker-thread targets for blocking behavior and unsafe UI access.",
    "mcp_name": "tk_ui_thread_audit",
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


def _make_finding(path: Path, root: Path, line: int, rule: str, message: str, **extra) -> dict:
    payload = {
        "file": relative_path(path, root),
        "line": line,
        "rule": rule,
        "message": message,
    }
    payload.update(extra)
    return payload


def _dedupe_findings(items: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    deduped = []
    for item in items:
        key = (
            item.get("file"),
            item.get("line"),
            item.get("rule"),
            item.get("callback"),
            item.get("target"),
            item.get("message"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def run(arguments: dict) -> dict:
    root = Path(arguments["root"]).resolve()
    top_n = int(arguments.get("top_n", 200))
    include_files = list(arguments.get("include_files", [".py"]))

    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Directory not found: {root}")

    findings = []
    files_scanned = 0

    for path in iter_python_files(root, include_files):
        files_scanned += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as exc:
            findings.append(_make_finding(path, root, exc.lineno or 1, "syntax_error", str(exc)))
            continue

        analyzer = TkFileAnalyzer(path)
        analyzer.visit(tree)

        if not analyzer.imports_tkinter and not analyzer.has_tkinter_usage and not analyzer.thread_targets:
            continue

        callback_edges = []
        callback_edges.extend(("command", item) for item in analyzer.command_callbacks if item.get("callback"))
        callback_edges.extend(("bind", item) for item in analyzer.bind_calls if item.get("callback"))
        callback_edges.extend(("schedule", item) for item in analyzer.schedule_calls if item.get("callback"))
        callback_edges.extend(("protocol", item) for item in analyzer.protocol_calls if item.get("callback"))

        for edge_type, item in callback_edges:
            resolved = resolve_callback(analyzer.functions, item["callback"], item.get("class"))
            if not resolved:
                continue
            blocking_calls = [call for call in resolved["calls"] if call_is_blocking(call)]
            for call in blocking_calls:
                findings.append(
                    _make_finding(
                        path,
                        root,
                        call["line"],
                        "ui_callback_blocking_call",
                        f"UI callback '{resolved['qualname']}' contains blocking call {call['func_name'] or call['short_name']}.",
                        callback=resolved["qualname"],
                        callback_type=edge_type,
                    )
                )

        for thread_target in analyzer.thread_targets:
            target_name = thread_target.get("target", "")
            if not target_name:
                findings.append(
                    _make_finding(
                        path,
                        root,
                        thread_target["line"],
                        "thread_target_unresolved",
                        "Thread start does not provide a resolvable target callback.",
                    )
                )
                continue

            resolved = resolve_callback(analyzer.functions, target_name, thread_target.get("class"))
            if not resolved:
                findings.append(
                    _make_finding(
                        path,
                        root,
                        thread_target["line"],
                        "thread_target_missing_definition",
                        f"Thread target '{target_name}' could not be resolved in the same file.",
                        target=target_name,
                    )
                )
                continue

            ui_calls = [call for call in resolved["calls"] if call_touches_ui(call)]
            for call in ui_calls:
                findings.append(
                    _make_finding(
                        path,
                        root,
                        call["line"],
                        "thread_target_touches_ui",
                        f"Worker-thread target '{resolved['qualname']}' appears to call UI method {call['func_name'] or call['short_name']}.",
                        target=resolved["qualname"],
                    )
                )

        if len(findings) >= top_n:
            break

    findings = _dedupe_findings(findings)
    counts_by_rule: dict[str, int] = Counter(item["rule"] for item in findings)
    result = {
        "root": str(root),
        "files_scanned": files_scanned,
        "finding_count": len(findings),
        "counts_by_rule": dict(counts_by_rule),
        "findings": findings[:top_n],
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
