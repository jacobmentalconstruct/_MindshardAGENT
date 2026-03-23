"""
FILE: tk_ui_test_scaffold.py
ROLE: Agent-facing Tkinter test scaffold generator.
WHAT IT DOES: Generates a unittest-based smoke-test scaffold for Tkinter UI classes discovered in a project.
HOW TO USE:
  - Metadata: python .final-tools/tools/tk_ui_test_scaffold.py metadata
  - Preview:  python .final-tools/tools/tk_ui_test_scaffold.py run --input-json "{\"root\": \"path/to/project\"}"
  - Write:    python .final-tools/tools/tk_ui_test_scaffold.py run --input-json "{\"root\": \"path/to/project\", \"output_path\": \"tests/test_tk_ui_smoke.py\"}"
INPUT OBJECT:
  - root: folder to scan
  - output_path: optional path to write the generated scaffold
  - top_n: optional class cap
  - include_files: optional list of file suffix filters, defaults to Python only
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result
from lib.tk_ast import TkFileAnalyzer, iter_python_files, relative_path


FILE_METADATA = {
    "tool_name": "tk_ui_test_scaffold",
    "version": "1.0.0",
    "entrypoint": "tools/tk_ui_test_scaffold.py",
    "category": "ui",
    "summary": "Generate unittest smoke-test scaffolds for Tkinter UI classes.",
    "mcp_name": "tk_ui_test_scaffold",
    "legacy_replaces": [],
    "input_schema": {
        "type": "object",
        "properties": {
            "root": {"type": "string", "description": "Folder to scan."},
            "output_path": {"type": "string", "description": "Optional file path for generated scaffold output."},
            "top_n": {"type": "integer", "default": 25},
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


def _safe_identifier(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_") or "module"


def _param_expression(param: dict) -> tuple[str, bool]:
    name = param["name"]
    bare = name.lstrip("*")
    if bare in {"parent", "master", "root", "container", "owner"}:
        return "root", True
    if bare.startswith("on_") or "callback" in bare or "handler" in bare:
        return "_noop", True
    if param.get("has_default"):
        return repr(param.get("default")), True
    if param.get("annotation") in {"int", "float"} or any(token in bare for token in {"count", "limit", "width", "height", "index"}):
        return "0", True
    if param.get("annotation") == "bool" or bare.startswith(("is_", "has_")):
        return "False", True
    if param.get("annotation") == "str" or any(token in bare for token in {"name", "title", "text", "path", "reason", "command", "label"}):
        return "''", True
    if any(token in bare for token in {"state", "config", "activity", "stream", "engine", "registry", "store", "session", "model", "project", "ui"}):
        return "None", True
    return "TODO_UNRESOLVED", False


def _generate_test_content(root: Path, targets: list[dict]) -> str:
    lines = [
        '"""Generated Tkinter UI smoke-test scaffold."""',
        "",
        "from __future__ import annotations",
        "",
        "import importlib.util",
        "import tkinter as tk",
        "import unittest",
        "from pathlib import Path",
        "",
        "TODO_UNRESOLVED = object()",
        "",
        "",
        "def _load_module(module_name: str, file_path: str):",
        "    spec = importlib.util.spec_from_file_location(module_name, file_path)",
        "    if spec is None or spec.loader is None:",
        "        raise RuntimeError(f'Unable to load module from {file_path}')",
        "    module = importlib.util.module_from_spec(spec)",
        "    spec.loader.exec_module(module)",
        "    return module",
        "",
        "",
        "def _noop(*args, **kwargs):",
        "    return None",
        "",
        "",
        "class TkUiSmokeTests(unittest.TestCase):",
        "    def setUp(self):",
        "        self.root = tk.Tk()",
        "        self.root.withdraw()",
        "",
        "    def tearDown(self):",
        "        try:",
        "            self.root.destroy()",
        "        except Exception:",
        "            pass",
        "",
    ]

    for index, target in enumerate(targets, start=1):
        module_var = f"_module_{index}"
        rel_path = target["file"]
        lines.extend([
            f"    def _load_{module_var}(self):",
            f"        return _load_module('{_safe_identifier(target['class_name'])}_{index}', str(Path(__file__).resolve().parents[1] / {rel_path!r}))",
            "",
            f"    def _kwargs_{_safe_identifier(target['class_name'])}_{index}(self):",
            "        return {",
        ])
        unresolved = False
        for param in target["init_params"]:
            expr, resolved = _param_expression(param)
            unresolved = unresolved or not resolved
            lines.append(f"            {param['name']!r}: {expr},")
        lines.extend([
            "        }",
            "",
            f"    def test_{_safe_identifier(target['class_name'])}_{index}_smoke(self):",
            f"        module = self._load_{module_var}()",
            f"        cls = getattr(module, {target['class_name']!r})",
            f"        kwargs = self._kwargs_{_safe_identifier(target['class_name'])}_{index}()",
        ])
        if unresolved:
            lines.extend([
                "        if TODO_UNRESOLVED in kwargs.values():",
                f"            self.skipTest('Fill in constructor args for {target['class_name']} before enabling this smoke test.')",
            ])
        lines.extend([
            "        instance = cls(**kwargs)",
            "        try:",
            "            if hasattr(instance, 'update_idletasks'):",
            "                instance.update_idletasks()",
            "        finally:",
            "            try:",
            "                if hasattr(instance, 'destroy'):",
            "                    instance.destroy()",
            "            except Exception:",
            "                pass",
            "",
        ])

    if len(lines) == 34:
        lines.extend([
            "    def test_no_tk_targets_found(self):",
            "        self.skipTest('No Tkinter UI classes were discovered for scaffolding.')",
            "",
        ])

    return "\n".join(lines) + "\n"


def run(arguments: dict) -> dict:
    root = Path(arguments["root"]).resolve()
    top_n = int(arguments.get("top_n", 25))
    include_files = list(arguments.get("include_files", [".py"]))
    output_path = Path(arguments["output_path"]).resolve() if arguments.get("output_path") else None

    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Directory not found: {root}")

    targets = []
    files_scanned = 0
    for path in iter_python_files(root, include_files):
        files_scanned += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue

        analyzer = TkFileAnalyzer(path)
        analyzer.visit(tree)
        if not analyzer.imports_tkinter and not analyzer.has_tkinter_usage:
            continue

        for class_info in analyzer.classes:
            if class_info["is_tk_subclass"] or class_info["name"].endswith(("Pane", "Dialog", "Window")):
                targets.append({
                    "file": relative_path(path, root),
                    "class_name": class_info["name"],
                    "line": class_info["line"],
                    "init_params": class_info.get("init_params", []),
                })

    targets = sorted(targets, key=lambda item: (item["file"], item["line"], item["class_name"]))[:top_n]
    scaffold = _generate_test_content(root, targets)

    written_to = ""
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(scaffold, encoding="utf-8")
        written_to = str(output_path)

    result = {
        "root": str(root),
        "files_scanned": files_scanned,
        "target_count": len(targets),
        "targets": targets,
        "written_to": written_to,
        "generated_test": scaffold,
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
