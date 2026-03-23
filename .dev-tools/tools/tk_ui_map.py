"""
FILE: tk_ui_map.py
ROLE: Agent-facing Tkinter UI structure mapper.
WHAT IT DOES: Scans Python files and extracts Tkinter-oriented structure such as windows, dialogs, widget construction, layout calls, event bindings, callbacks, and UI class composition.
HOW TO USE:
  - Metadata: python .final-tools/tools/tk_ui_map.py metadata
  - Run: python .final-tools/tools/tk_ui_map.py run --input-json "{\"root\": \"path/to/project\"}"
INPUT OBJECT:
  - root: folder to scan
  - top_n: optional summary list size
  - include_files: optional list of file suffix filters, defaults to Python only
NOTES:
  - This is an AST-based mapper intended for large Tkinter codebases.
  - It is structural, not visual: it maps code shape and UI wiring rather than rendering windows.
"""

from __future__ import annotations

import ast
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from common import should_skip_dir, standard_main, tool_result


FILE_METADATA = {
    "tool_name": "tk_ui_map",
    "version": "1.0.0",
    "entrypoint": "tools/tk_ui_map.py",
    "category": "ui",
    "summary": "Map Tkinter UI structure, widget wiring, callbacks, and layout patterns across a Python project.",
    "mcp_name": "tk_ui_map",
    "legacy_replaces": [],
    "input_schema": {
        "type": "object",
        "properties": {
            "root": {"type": "string", "description": "Folder to scan."},
            "top_n": {"type": "integer", "default": 50},
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


TK_WIDGETS = {
    "Tk", "Toplevel", "Frame", "Label", "Button", "Entry", "Text", "Canvas", "Scrollbar",
    "Listbox", "Menu", "PanedWindow", "Checkbutton", "Radiobutton", "Scale", "Spinbox",
    "LabelFrame", "Message", "OptionMenu", "Menubutton"
}

TTK_WIDGETS = {
    "Frame", "Label", "Button", "Entry", "Combobox", "Notebook", "Treeview", "Scrollbar",
    "PanedWindow", "Progressbar", "Checkbutton", "Radiobutton", "Scale", "Separator",
    "LabelFrame", "Spinbox"
}

WINDOW_WIDGETS = {"Tk", "Toplevel"}
LAYOUT_METHODS = {"pack", "grid", "place"}
BIND_METHODS = {"bind", "bind_all", "bind_class"}
SCHEDULING_METHODS = {"after", "after_idle", "after_cancel"}


def _iter_python_files(root: Path, include_files: list[str]):
    include = {item.lower() for item in include_files} or {".py"}
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if not should_skip_dir(name)]
        for name in files:
            path = Path(current_root) / name
            if path.suffix.lower() in include:
                yield path


def _dotted_name(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _literal(node: ast.AST | None):
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def _keyword_arg(call: ast.Call, name: str):
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


class TkFileAnalyzer(ast.NodeVisitor):
    def __init__(self, path: Path):
        self.path = path
        self.tk_aliases = {"tkinter"}
        self.ttk_aliases = {"ttk"}
        self.tk_direct_names = set()
        self.ttk_direct_names = set()
        self.current_class: str | None = None
        self.current_function: str | None = None
        self.classes: list[dict] = []
        self.functions: list[dict] = []
        self.widget_calls: list[dict] = []
        self.window_calls: list[dict] = []
        self.layout_calls: list[dict] = []
        self.bind_calls: list[dict] = []
        self.schedule_calls: list[dict] = []
        self.protocol_calls: list[dict] = []
        self.mainloop_calls: list[dict] = []
        self.composition_calls: list[dict] = []
        self.imports_tkinter = False
        self.has_tkinter_usage = False

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "tkinter":
                self.imports_tkinter = True
                self.tk_aliases.add(alias.asname or alias.name)
            elif alias.name == "tkinter.ttk":
                self.imports_tkinter = True
                self.ttk_aliases.add(alias.asname or "ttk")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "tkinter":
            self.imports_tkinter = True
            for alias in node.names:
                name = alias.asname or alias.name
                if alias.name == "ttk":
                    self.ttk_aliases.add(name)
                else:
                    self.tk_direct_names.add(name)
        elif node.module == "tkinter.ttk":
            self.imports_tkinter = True
            for alias in node.names:
                self.ttk_direct_names.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        previous_class = self.current_class
        base_names = [_dotted_name(base) for base in node.bases]
        class_info = {
            "name": node.name,
            "line": node.lineno,
            "bases": base_names,
            "is_tk_subclass": any(self._is_widget_name(base) for base in base_names),
            "method_names": [item.name for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))],
        }
        self.classes.append(class_info)
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = previous_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        previous_function = self.current_function
        self.current_function = node.name
        self.functions.append({
            "name": node.name,
            "line": node.lineno,
            "class": self.current_class,
        })
        self.generic_visit(node)
        self.current_function = previous_function

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        func_name = _dotted_name(node.func)
        short_name = func_name.split(".")[-1] if func_name else ""

        widget_kind = self._resolve_widget_kind(node.func)
        if widget_kind:
            self.has_tkinter_usage = True
            payload = {
                "line": node.lineno,
                "class": self.current_class,
                "function": self.current_function,
                "widget_type": widget_kind,
                "call": func_name or widget_kind,
                "parent_arg": _dotted_name(node.args[0]) if node.args else "",
            }
            self.widget_calls.append(payload)
            if widget_kind in WINDOW_WIDGETS:
                self.window_calls.append(payload)

        if short_name in LAYOUT_METHODS:
            self.has_tkinter_usage = True
            self.layout_calls.append({
                "line": node.lineno,
                "class": self.current_class,
                "function": self.current_function,
                "method": short_name,
                "target": _dotted_name(getattr(node.func, "value", None)),
            })

        if short_name in BIND_METHODS:
            self.has_tkinter_usage = True
            callback = ""
            if len(node.args) >= 2:
                callback = _dotted_name(node.args[1])
            if not callback:
                callback = _dotted_name(_keyword_arg(node, "func"))
            self.bind_calls.append({
                "line": node.lineno,
                "class": self.current_class,
                "function": self.current_function,
                "method": short_name,
                "target": _dotted_name(getattr(node.func, "value", None)),
                "event": _literal(node.args[0]) if node.args else None,
                "callback": callback,
            })

        if short_name in SCHEDULING_METHODS:
            self.has_tkinter_usage = True
            callback = ""
            if len(node.args) >= 2:
                callback = _dotted_name(node.args[1])
            if len(node.args) >= 1 and short_name == "after_idle":
                callback = _dotted_name(node.args[0])
            self.schedule_calls.append({
                "line": node.lineno,
                "class": self.current_class,
                "function": self.current_function,
                "method": short_name,
                "target": _dotted_name(getattr(node.func, "value", None)),
                "callback": callback,
                "delay_ms": _literal(node.args[0]) if node.args and short_name == "after" else None,
            })

        if short_name == "protocol":
            self.has_tkinter_usage = True
            self.protocol_calls.append({
                "line": node.lineno,
                "class": self.current_class,
                "function": self.current_function,
                "target": _dotted_name(getattr(node.func, "value", None)),
                "protocol": _literal(node.args[0]) if node.args else None,
                "callback": _dotted_name(node.args[1]) if len(node.args) > 1 else "",
            })

        if short_name == "mainloop":
            self.has_tkinter_usage = True
            self.mainloop_calls.append({
                "line": node.lineno,
                "class": self.current_class,
                "function": self.current_function,
                "target": _dotted_name(getattr(node.func, "value", None)),
            })

        if self.current_class and isinstance(node.func, ast.Name) and node.func.id[:1].isupper():
            if node.func.id not in TK_WIDGETS and node.func.id not in TTK_WIDGETS:
                self.composition_calls.append({
                    "line": node.lineno,
                    "class": self.current_class,
                    "function": self.current_function,
                    "child_class": node.func.id,
                })

        self.generic_visit(node)

    def _resolve_widget_kind(self, func: ast.AST) -> str:
        if isinstance(func, ast.Name):
            if func.id in self.tk_direct_names and func.id in TK_WIDGETS:
                return func.id
            if func.id in self.ttk_direct_names and func.id in TTK_WIDGETS:
                return f"ttk.{func.id}"
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            alias = func.value.id
            if alias in self.tk_aliases and func.attr in TK_WIDGETS:
                return func.attr
            if alias in self.ttk_aliases and func.attr in TTK_WIDGETS:
                return f"ttk.{func.attr}"
        return ""

    def _is_widget_name(self, dotted_name: str) -> bool:
        short = dotted_name.split(".")[-1]
        return short in TK_WIDGETS or short in TTK_WIDGETS


def _relative(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def run(arguments: dict) -> dict:
    root = Path(arguments["root"]).resolve()
    top_n = int(arguments.get("top_n", 50))
    include_files = list(arguments.get("include_files", [".py"]))

    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Directory not found: {root}")

    files_payload = []
    widget_counts: Counter[str] = Counter()
    layout_counts: Counter[str] = Counter()
    bind_event_counts: Counter[str] = Counter()
    class_counts: Counter[str] = Counter()
    schedule_counts: Counter[str] = Counter()
    ui_composition: dict[str, list[str]] = defaultdict(list)
    files_scanned = 0

    for path in _iter_python_files(root, include_files):
        files_scanned += 1
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source)
        except SyntaxError as exc:
            files_payload.append({
                "path": _relative(path, root),
                "parse_error": str(exc),
            })
            continue

        analyzer = TkFileAnalyzer(path)
        analyzer.visit(tree)
        if not analyzer.imports_tkinter and not analyzer.has_tkinter_usage:
            continue

        for item in analyzer.widget_calls:
            widget_counts[item["widget_type"]] += 1
        for item in analyzer.layout_calls:
            layout_counts[item["method"]] += 1
        for item in analyzer.bind_calls:
            bind_event_counts[str(item.get("event") or "<unknown>")] += 1
        for item in analyzer.schedule_calls:
            schedule_counts[item["method"]] += 1
        for item in analyzer.classes:
            if item["is_tk_subclass"]:
                class_counts[item["name"]] += 1
        for item in analyzer.composition_calls:
            ui_composition[item["class"]].append(item["child_class"])

        files_payload.append({
            "path": _relative(path, root),
            "class_count": len(analyzer.classes),
            "ui_class_count": len([item for item in analyzer.classes if item["is_tk_subclass"]]),
            "widget_call_count": len(analyzer.widget_calls),
            "window_count": len(analyzer.window_calls),
            "layout_call_count": len(analyzer.layout_calls),
            "bind_call_count": len(analyzer.bind_calls),
            "schedule_call_count": len(analyzer.schedule_calls),
            "mainloop_count": len(analyzer.mainloop_calls),
            "protocol_call_count": len(analyzer.protocol_calls),
            "classes": analyzer.classes[:top_n],
            "windows": analyzer.window_calls[:top_n],
            "widget_calls": analyzer.widget_calls[:top_n],
            "layout_calls": analyzer.layout_calls[:top_n],
            "bind_calls": analyzer.bind_calls[:top_n],
            "schedule_calls": analyzer.schedule_calls[:top_n],
            "composition_calls": analyzer.composition_calls[:top_n],
        })

    composition_summary = {
        key: sorted(Counter(value).items(), key=lambda item: (-item[1], item[0]))[:top_n]
        for key, value in ui_composition.items()
    }

    result = {
        "root": str(root),
        "files_scanned": files_scanned,
        "tkinter_files": len([item for item in files_payload if "parse_error" not in item]),
        "summary": {
            "top_widget_types": dict(widget_counts.most_common(top_n)),
            "top_layout_methods": dict(layout_counts.most_common(top_n)),
            "top_bind_events": dict(bind_event_counts.most_common(top_n)),
            "top_schedule_methods": dict(schedule_counts.most_common(top_n)),
            "ui_subclass_counts": dict(class_counts.most_common(top_n)),
        },
        "ui_composition": composition_summary,
        "files": files_payload[:top_n],
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
