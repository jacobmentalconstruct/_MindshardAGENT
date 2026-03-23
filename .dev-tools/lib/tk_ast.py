"""
FILE: lib/tk_ast.py
ROLE: Internal Tkinter AST analysis helpers for .final-tools.
WHAT IT DOES: Provides reusable scanning, callback resolution, and structural analysis helpers for Tkinter-oriented tools.
HOW TO USE:
  - Import from Tkinter-focused tools under tools/.
  - This is internal support code, not a direct user-facing tool.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

from common import should_skip_dir


TK_WIDGETS = {
    "Tk", "Toplevel", "Frame", "Label", "Button", "Entry", "Text", "Canvas", "Scrollbar",
    "Listbox", "Menu", "PanedWindow", "Checkbutton", "Radiobutton", "Scale", "Spinbox",
    "LabelFrame", "Message", "OptionMenu", "Menubutton",
}

TTK_WIDGETS = {
    "Frame", "Label", "Button", "Entry", "Combobox", "Notebook", "Treeview", "Scrollbar",
    "PanedWindow", "Progressbar", "Checkbutton", "Radiobutton", "Scale", "Separator",
    "LabelFrame", "Spinbox",
}

WINDOW_WIDGETS = {"Tk", "Toplevel"}
LAYOUT_METHODS = {"pack", "grid", "place"}
BIND_METHODS = {"bind", "bind_all", "bind_class"}
SCHEDULING_METHODS = {"after", "after_idle", "after_cancel"}
GEOMETRY_METHODS = {
    "geometry", "minsize", "maxsize", "resizable", "pack_propagate", "grid_propagate",
    "rowconfigure", "columnconfigure", "sash_place",
}
UI_MUTATION_METHODS = {
    "config", "configure", "insert", "delete", "set", "see", "title", "geometry",
    "minsize", "maxsize", "protocol", "destroy", "withdraw", "deiconify", "focus_set",
    "update", "update_idletasks", "after", "after_idle", "after_cancel", "pack", "grid",
    "place", "pack_forget", "grid_forget", "selection_set", "selection_clear", "yview_moveto",
    "xview_moveto", "itemconfig", "itemconfigure", "coords", "state",
}
BLOCKING_DOTTED = {
    "subprocess.run",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "subprocess.Popen",
    "time.sleep",
    "os.system",
    "os.popen",
}
BLOCKING_SHORT = {"sleep", "join", "wait", "communicate"}


def iter_python_files(root: Path, include_files: list[str] | None = None):
    include = {item.lower() for item in (include_files or [".py"])}
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if not should_skip_dir(name)]
        for name in files:
            path = Path(current_root) / name
            if path.suffix.lower() in include:
                yield path


def dotted_name(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def literal(node: ast.AST | None):
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def callback_name(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Lambda):
        return "<lambda>"
    return dotted_name(node)


def keyword_arg(call: ast.Call, name: str):
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def relative_path(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def target_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return [dotted_name(node)]
    if isinstance(node, (ast.Tuple, ast.List)):
        names: list[str] = []
        for item in node.elts:
            names.extend(target_names(item))
        return names
    return []


def function_params(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[dict]:
    args = list(node.args.args)
    defaults = [None] * (len(args) - len(node.args.defaults)) + list(node.args.defaults)
    params = []
    for arg, default in zip(args, defaults):
        params.append({
            "name": arg.arg,
            "annotation": dotted_name(arg.annotation) if arg.annotation else "",
            "has_default": default is not None,
            "default": literal(default),
        })
    for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
        params.append({
            "name": arg.arg,
            "annotation": dotted_name(arg.annotation) if arg.annotation else "",
            "has_default": default is not None,
            "default": literal(default),
        })
    return params


class TkFileAnalyzer(ast.NodeVisitor):
    def __init__(self, path: Path):
        self.path = path
        self.tk_aliases = {"tkinter"}
        self.ttk_aliases = {"ttk"}
        self.tk_direct_names = set()
        self.ttk_direct_names = set()
        self.threading_aliases = {"threading"}
        self.thread_direct_names = set()
        self.current_class: str | None = None
        self.current_function: str | None = None
        self.current_qualname: str | None = None
        self.classes: list[dict] = []
        self.functions: list[dict] = []
        self.function_lookup: dict[tuple[str | None, str], dict] = {}
        self.widget_calls: list[dict] = []
        self.window_calls: list[dict] = []
        self.layout_calls: list[dict] = []
        self.bind_calls: list[dict] = []
        self.schedule_calls: list[dict] = []
        self.protocol_calls: list[dict] = []
        self.mainloop_calls: list[dict] = []
        self.geometry_calls: list[dict] = []
        self.command_callbacks: list[dict] = []
        self.thread_targets: list[dict] = []
        self.composition_calls: list[dict] = []
        self.imports_tkinter = False
        self.has_tkinter_usage = False
        self._call_assignments: dict[int, list[str]] = {}

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "tkinter":
                self.imports_tkinter = True
                self.tk_aliases.add(alias.asname or alias.name)
            elif alias.name == "tkinter.ttk":
                self.imports_tkinter = True
                self.ttk_aliases.add(alias.asname or "ttk")
            elif alias.name == "threading":
                self.threading_aliases.add(alias.asname or alias.name)
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
        elif node.module == "threading":
            for alias in node.names:
                self.thread_direct_names.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        previous_class = self.current_class
        base_names = [dotted_name(base) for base in node.bases]
        init_params = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "__init__":
                init_params = function_params(item)[1:]
                break
        self.classes.append({
            "name": node.name,
            "line": node.lineno,
            "bases": base_names,
            "is_tk_subclass": any(self._is_widget_name(base) for base in base_names),
            "method_names": [item.name for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))],
            "init_params": init_params,
        })
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = previous_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        previous_function = self.current_function
        previous_qualname = self.current_qualname
        self.current_function = node.name
        self.current_qualname = f"{self.current_class}.{node.name}" if self.current_class else node.name
        info = {
            "name": node.name,
            "qualname": self.current_qualname,
            "line": node.lineno,
            "class": self.current_class,
            "params": function_params(node),
            "calls": [],
        }
        self.functions.append(info)
        self.function_lookup[(self.current_class, node.name)] = info
        self.generic_visit(node)
        self.current_function = previous_function
        self.current_qualname = previous_qualname

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Assign(self, node: ast.Assign) -> None:
        if isinstance(node.value, ast.Call):
            assigned: list[str] = []
            for target in node.targets:
                assigned.extend(target_names(target))
            self._call_assignments[id(node.value)] = assigned
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.value, ast.Call):
            self._call_assignments[id(node.value)] = target_names(node.target)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func_name = dotted_name(node.func)
        short_name = func_name.split(".")[-1] if func_name else ""
        target = dotted_name(getattr(node.func, "value", None))
        call_info = {
            "line": node.lineno,
            "func_name": func_name,
            "short_name": short_name,
            "target": target,
            "target_literal": literal(getattr(node.func, "value", None)),
            "target_node_type": type(getattr(node.func, "value", None)).__name__ if getattr(node.func, "value", None) is not None else "",
            "arg_literals": [literal(arg) for arg in node.args],
            "arg_names": [dotted_name(arg) or callback_name(arg) for arg in node.args],
            "keyword_literals": {keyword.arg: literal(keyword.value) for keyword in node.keywords if keyword.arg},
            "keyword_names": {keyword.arg: callback_name(keyword.value) for keyword in node.keywords if keyword.arg},
        }
        if self.current_function:
            self.function_lookup[(self.current_class, self.current_function)]["calls"].append(call_info)

        assigned_to = self._call_assignments.get(id(node), [])
        widget_kind = self._resolve_widget_kind(node.func)
        if widget_kind:
            self.has_tkinter_usage = True
            payload = {
                "line": node.lineno,
                "class": self.current_class,
                "function": self.current_function,
                "widget_type": widget_kind,
                "call": func_name or widget_kind,
                "parent_arg": dotted_name(node.args[0]) if node.args else callback_name(keyword_arg(node, "master")) or callback_name(keyword_arg(node, "parent")),
                "assigned_to": assigned_to,
                "keyword_literals": call_info["keyword_literals"],
            }
            self.widget_calls.append(payload)
            if widget_kind in WINDOW_WIDGETS:
                self.window_calls.append(payload)

            command_callback = callback_name(keyword_arg(node, "command"))
            if command_callback:
                self.command_callbacks.append({
                    "line": node.lineno,
                    "class": self.current_class,
                    "function": self.current_function,
                    "widget_type": widget_kind,
                    "widget_names": assigned_to,
                    "callback": command_callback,
                })

        if short_name in LAYOUT_METHODS:
            self.has_tkinter_usage = True
            self.layout_calls.append({
                "line": node.lineno,
                "class": self.current_class,
                "function": self.current_function,
                "method": short_name,
                "target": target,
                "arg_literals": call_info["arg_literals"],
                "keyword_literals": call_info["keyword_literals"],
                "keyword_names": call_info["keyword_names"],
            })

        if short_name in BIND_METHODS:
            self.has_tkinter_usage = True
            callback = ""
            if len(node.args) >= 2:
                callback = callback_name(node.args[1])
            if not callback:
                callback = callback_name(keyword_arg(node, "func"))
            self.bind_calls.append({
                "line": node.lineno,
                "class": self.current_class,
                "function": self.current_function,
                "method": short_name,
                "target": target,
                "event": literal(node.args[0]) if node.args else None,
                "callback": callback,
            })

        if short_name in SCHEDULING_METHODS:
            self.has_tkinter_usage = True
            callback = ""
            if short_name == "after_idle" and node.args:
                callback = callback_name(node.args[0])
            elif len(node.args) >= 2:
                callback = callback_name(node.args[1])
            self.schedule_calls.append({
                "line": node.lineno,
                "class": self.current_class,
                "function": self.current_function,
                "method": short_name,
                "target": target,
                "callback": callback,
                "delay_ms": literal(node.args[0]) if node.args and short_name == "after" else None,
            })

        if short_name == "protocol":
            self.has_tkinter_usage = True
            self.protocol_calls.append({
                "line": node.lineno,
                "class": self.current_class,
                "function": self.current_function,
                "target": target,
                "protocol": literal(node.args[0]) if node.args else None,
                "callback": callback_name(node.args[1]) if len(node.args) > 1 else "",
            })

        if short_name == "mainloop":
            self.has_tkinter_usage = True
            self.mainloop_calls.append({
                "line": node.lineno,
                "class": self.current_class,
                "function": self.current_function,
                "target": target,
            })

        if short_name in GEOMETRY_METHODS:
            self.has_tkinter_usage = True
            self.geometry_calls.append({
                "line": node.lineno,
                "class": self.current_class,
                "function": self.current_function,
                "method": short_name,
                "target": target,
                "arg_literals": call_info["arg_literals"],
                "keyword_literals": call_info["keyword_literals"],
            })

        if self._is_thread_constructor(node.func):
            self.thread_targets.append({
                "line": node.lineno,
                "class": self.current_class,
                "function": self.current_function,
                "target": callback_name(keyword_arg(node, "target")),
                "name": literal(keyword_arg(node, "name")),
                "daemon": literal(keyword_arg(node, "daemon")),
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

    def _is_widget_name(self, dotted_name_value: str) -> bool:
        short = dotted_name_value.split(".")[-1]
        return short in TK_WIDGETS or short in TTK_WIDGETS

    def _is_thread_constructor(self, func: ast.AST) -> bool:
        if isinstance(func, ast.Name):
            return func.id in self.thread_direct_names
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            return func.value.id in self.threading_aliases and func.attr == "Thread"
        return False


def resolve_callback(functions: list[dict], callback: str, current_class: str | None = None) -> dict | None:
    if not callback or callback == "<lambda>":
        return None
    normalized = callback.split(".")[-1]
    candidates = []
    for function in functions:
        if function["name"] == normalized:
            if current_class is None or function.get("class") == current_class:
                candidates.append(function)
    if candidates:
        return sorted(candidates, key=lambda item: (item.get("class") != current_class, item["line"]))[0]
    for function in functions:
        if function["qualname"] == callback:
            return function
    return None


def call_touches_ui(call_info: dict) -> bool:
    target = call_info.get("target", "")
    short_name = call_info.get("short_name", "")
    if short_name in UI_MUTATION_METHODS:
        if target.startswith("self.") or target in {"root", "self", "window"} or target.endswith(".root"):
            return True
    if call_info.get("func_name", "").startswith("tkinter.messagebox"):
        return True
    return False


def call_is_blocking(call_info: dict) -> bool:
    func_name = call_info.get("func_name", "")
    short_name = call_info.get("short_name", "")
    if func_name in BLOCKING_DOTTED:
        return True
    if short_name == "join":
        if isinstance(call_info.get("target_literal"), (str, bytes)):
            return False
        target = (call_info.get("target") or "").lower()
        if not target:
            return False
        blocking_markers = (
            "thread",
            "worker",
            "process",
            "proc",
            "future",
            "task",
            "pool",
            "executor",
            "job",
            "child",
            "subprocess",
        )
        return target.startswith("self.") or any(marker in target for marker in blocking_markers)
    if short_name in BLOCKING_SHORT:
        return True
    return False
