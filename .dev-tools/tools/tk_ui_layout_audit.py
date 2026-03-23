"""
FILE: tk_ui_layout_audit.py
ROLE: Agent-facing Tkinter layout auditor.
WHAT IT DOES: Flags mixed geometry-manager usage, global binds, hard-coded window sizing, and other layout-related hotspots in Tkinter code.
HOW TO USE:
  - Metadata: python .final-tools/tools/tk_ui_layout_audit.py metadata
  - Run: python .final-tools/tools/tk_ui_layout_audit.py run --input-json "{\"root\": \"path/to/project\"}"
INPUT OBJECT:
  - root: folder to scan
  - top_n: optional finding cap
  - include_files: optional list of file suffix filters, defaults to Python only
"""

from __future__ import annotations

import ast
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result
from lib.tk_ast import TkFileAnalyzer, iter_python_files, relative_path


FILE_METADATA = {
    "tool_name": "tk_ui_layout_audit",
    "version": "1.0.0",
    "entrypoint": "tools/tk_ui_layout_audit.py",
    "category": "ui",
    "summary": "Audit Tkinter layout patterns for mixed geometry use and hard-coded UI hotspots.",
    "mcp_name": "tk_ui_layout_audit",
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


WINDOW_SIZE_PATTERN = re.compile(r"^\d+x\d+$")


def _finding(path: Path, root: Path, line: int, rule: str, message: str, **extra) -> dict:
    payload = {
        "file": relative_path(path, root),
        "line": line,
        "rule": rule,
        "message": message,
    }
    payload.update(extra)
    return payload


def _layout_parent(item: dict, widget_parent_by_name: dict[str, str]) -> str:
    target = item.get("target") or ""
    method = item.get("method") or ""
    keyword_names = item.get("keyword_names") or {}

    if method == "place" and keyword_names.get("in_"):
        return keyword_names["in_"]
    if target and target in widget_parent_by_name:
        return widget_parent_by_name[target]
    if target in {"self", "root", "window"}:
        return "<root>"
    return ""


def run(arguments: dict) -> dict:
    root = Path(arguments["root"]).resolve()
    top_n = int(arguments.get("top_n", 200))
    include_files = list(arguments.get("include_files", [".py"]))

    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Directory not found: {root}")

    findings = []
    files_scanned = 0
    fixed_dimension_widgets = []

    for path in iter_python_files(root, include_files):
        files_scanned += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as exc:
            findings.append(_finding(path, root, exc.lineno or 1, "syntax_error", str(exc)))
            continue

        analyzer = TkFileAnalyzer(path)
        analyzer.visit(tree)
        if not analyzer.imports_tkinter and not analyzer.has_tkinter_usage:
            continue

        widget_parent_by_name: dict[str, str] = {}
        for item in analyzer.widget_calls:
            parent = item.get("parent_arg") or ""
            for name in item.get("assigned_to") or []:
                if parent:
                    widget_parent_by_name[name] = parent

        layout_by_parent: dict[tuple[str, str], set[str]] = defaultdict(set)
        first_layout_by_parent: dict[tuple[str, str], dict] = {}
        for item in analyzer.layout_calls:
            parent = _layout_parent(item, widget_parent_by_name)
            if not parent:
                continue
            key = (item.get("class") or "<module>", parent)
            layout_by_parent[key].add(item["method"])
            first_layout_by_parent.setdefault(key, item)

        for (class_name, parent), methods in layout_by_parent.items():
            if len(methods) > 1:
                first_line = first_layout_by_parent[(class_name, parent)]["line"]
                findings.append(
                    _finding(
                        path,
                        root,
                        first_line,
                        "mixed_geometry_managers",
                        f"{class_name} mixes geometry managers within parent {parent}: {', '.join(sorted(methods))}.",
                        class_name=class_name,
                        parent=parent,
                    )
                )

        for item in analyzer.bind_calls:
            if item["method"] == "bind_all":
                rule = "global_mousewheel_bind_all" if item.get("event") == "<MouseWheel>" else "global_bind_all"
                findings.append(
                    _finding(
                        path,
                        root,
                        item["line"],
                        rule,
                        f"Global binding via bind_all for event {item.get('event')!r}.",
                    )
                )

        for item in analyzer.geometry_calls:
            method = item["method"]
            first_arg = item["arg_literals"][0] if item["arg_literals"] else None
            if method == "geometry" and isinstance(first_arg, str) and WINDOW_SIZE_PATTERN.match(first_arg):
                findings.append(
                    _finding(
                        path,
                        root,
                        item["line"],
                        "hardcoded_window_geometry",
                        f"Hard-coded window geometry string {first_arg!r}.",
                    )
                )
            elif method in {"minsize", "maxsize"} and item["arg_literals"]:
                findings.append(
                    _finding(
                        path,
                        root,
                        item["line"],
                        "hardcoded_window_size",
                        f"Hard-coded {method} values {item['arg_literals']}.",
                    )
                )
            elif method == "sash_place":
                findings.append(
                    _finding(
                        path,
                        root,
                        item["line"],
                        "manual_sash_placement",
                        "Manual sash placement detected. This can be brittle across DPI/layout changes.",
                    )
                )
            elif method in {"pack_propagate", "grid_propagate"} and item["arg_literals"] and item["arg_literals"][0] is False:
                findings.append(
                    _finding(
                        path,
                        root,
                        item["line"],
                        "geometry_propagation_disabled",
                        f"{method} is disabled explicitly.",
                    )
                )

        for item in analyzer.widget_calls:
            dims = {}
            for key in ("width", "height", "wraplength", "padx", "pady"):
                value = item["keyword_literals"].get(key)
                if isinstance(value, (int, float)) and value:
                    dims[key] = value
            if dims:
                fixed_dimension_widgets.append({
                    "file": relative_path(path, root),
                    "line": item["line"],
                    "widget_type": item["widget_type"],
                    "dimensions": dims,
                })

        if len(findings) >= top_n:
            break

    counts_by_rule: dict[str, int] = Counter(item["rule"] for item in findings)
    result = {
        "root": str(root),
        "files_scanned": files_scanned,
        "finding_count": len(findings),
        "counts_by_rule": dict(counts_by_rule),
        "findings": findings[:top_n],
        "fixed_dimension_widgets": fixed_dimension_widgets[:top_n],
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
