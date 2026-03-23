"""
FILE: python_risk_scan.py
ROLE: Agent-facing Python static scanner.
WHAT IT DOES: Flags a small set of practical AST-detectable risks using a uniform JSON contract.
HOW TO USE:
  - Metadata: python .final-tools/tools/python_risk_scan.py metadata
  - Run: python .final-tools/tools/python_risk_scan.py run --input-json "{\"root\": \".\"}"
INPUT OBJECT:
  - root: folder to scan
  - top_n: optional finding cap
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from common import should_skip_dir, standard_main, tool_result


FILE_METADATA = {
    "tool_name": "python_risk_scan",
    "version": "1.0.0",
    "entrypoint": "tools/python_risk_scan.py",
    "category": "analysis",
    "summary": "Scan Python files for a focused set of practical risk patterns.",
    "mcp_name": "python_risk_scan",
    "legacy_replaces": [
        ".dev-tools/scan_blocking_calls.py"
    ],
    "input_schema": {
        "type": "object",
        "properties": {
            "root": {"type": "string", "description": "Folder to scan."},
            "top_n": {"type": "integer", "default": 200}
        },
        "required": ["root"],
        "additionalProperties": False
    }
}


BLOCKING_CALLS = {
    ("subprocess", "run"),
    ("subprocess", "call"),
    ("subprocess", "check_call"),
    ("subprocess", "check_output"),
    ("subprocess", "Popen"),
    ("time", "sleep"),
}

SHELL_EXECUTION_CALLS = {
    ("os", "system"),
    ("os", "popen"),
}

DYNAMIC_EXECUTION_NAMES = {"eval", "exec"}
MUTABLE_DEFAULT_NODES = (ast.List, ast.Dict, ast.Set)


def _iter_python_files(root: Path):
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not should_skip_dir(d)]
        for name in files:
            if name.endswith(".py"):
                yield Path(current_root) / name


def _call_pair(node: ast.Call) -> tuple[str, str] | None:
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return func.value.id, func.attr
    return None


def run(arguments: dict) -> dict:
    root = Path(arguments["root"]).resolve()
    top_n = int(arguments.get("top_n", 200))

    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Directory not found: {root}")

    findings = []
    files_scanned = 0

    for path in _iter_python_files(root):
        files_scanned += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as exc:
            findings.append({
                "file": str(path),
                "line": exc.lineno or 1,
                "rule": "syntax_error",
                "message": str(exc),
            })
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                pair = _call_pair(node)
                if pair in BLOCKING_CALLS:
                    findings.append({
                        "file": str(path),
                        "line": node.lineno,
                        "rule": "blocking_call",
                        "message": f"Blocking call detected: {pair[0]}.{pair[1]}()",
                    })
                elif pair in SHELL_EXECUTION_CALLS:
                    findings.append({
                        "file": str(path),
                        "line": node.lineno,
                        "rule": "shell_execution",
                        "message": f"Shell execution detected: {pair[0]}.{pair[1]}()",
                    })
                elif isinstance(node.func, ast.Name) and node.func.id in DYNAMIC_EXECUTION_NAMES:
                    findings.append({
                        "file": str(path),
                        "line": node.lineno,
                        "rule": "dynamic_execution",
                        "message": f"Dynamic execution detected: {node.func.id}()",
                    })

            elif isinstance(node, ast.Try):
                for handler in node.handlers:
                    if handler.type is None:
                        findings.append({
                            "file": str(path),
                            "line": handler.lineno,
                            "rule": "bare_except",
                            "message": "Bare except block detected.",
                        })

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defaults = list(node.args.defaults) + [item for item in node.args.kw_defaults if item is not None]
                for default in defaults:
                    if isinstance(default, MUTABLE_DEFAULT_NODES):
                        findings.append({
                            "file": str(path),
                            "line": node.lineno,
                            "rule": "mutable_default",
                            "message": f"Mutable default argument in function '{node.name}'.",
                        })

            if len(findings) >= top_n:
                break
        if len(findings) >= top_n:
            break

    counts_by_rule: dict[str, int] = {}
    for finding in findings:
        counts_by_rule[finding["rule"]] = counts_by_rule.get(finding["rule"], 0) + 1

    result = {
        "root": str(root),
        "files_scanned": files_scanned,
        "finding_count": len(findings),
        "counts_by_rule": counts_by_rule,
        "findings": findings[:top_n],
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
