"""
FILE: domain_boundary_audit.py
ROLE: Agent-facing Python domain boundary auditor.
WHAT IT DOES: Uses AST to count how many distinct domains each function/class/file
  accesses, flagging violations of the builder contract:
    - Components: 1 domain only
    - Managers: max 3 domains
    - Orchestrators: bounded to their side (UI or CORE)
    - app.py: wiring only, no deep hierarchy access
HOW TO USE:
  - Metadata: python final-tools/tools/domain_boundary_audit.py metadata
  - Run: python final-tools/tools/domain_boundary_audit.py run --input-json "{\"root\": \"src\"}"
INPUT OBJECT:
  - root: folder or single file to audit
  - component_max: max domains for a component (default 1)
  - manager_max: max domains for a manager (default 3)
  - depth_warn: attribute chain depth that triggers a warning (default 3)
"""

from __future__ import annotations

import ast
import os
import sys
from collections import defaultdict
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from common import should_skip_dir, standard_main, tool_result, tool_error


FILE_METADATA = {
    "tool_name": "domain_boundary_audit",
    "version": "1.0.0",
    "entrypoint": "tools/domain_boundary_audit.py",
    "category": "analysis",
    "summary": "AST-based audit of domain boundary violations per function, class, and file.",
    "mcp_name": "domain_boundary_audit",
    "legacy_replaces": [],
    "input_schema": {
        "type": "object",
        "properties": {
            "root": {"type": "string", "description": "Folder or file to audit."},
            "component_max": {"type": "integer", "default": 1},
            "manager_max": {"type": "integer", "default": 3},
            "depth_warn": {"type": "integer", "default": 3},
        },
        "required": ["root"],
        "additionalProperties": False,
    },
}


# ── Domain classification ──

# Map import paths to domain names.
# Imports from these packages indicate which domain a name belongs to.
_IMPORT_DOMAIN_MAP = {
    "src.ui": "ui",
    "src.core.agent": "agent",
    "src.core.config": "config",
    "src.core.engine": "engine",
    "src.core.ollama": "ollama",
    "src.core.runtime": "runtime",
    "src.core.sandbox": "sandbox",
    "src.core.sessions": "sessions",
    "src.core.vcs": "vcs",
    "src.core.project": "project",
    "tkinter": "ui",
    "tk": "ui",
}

# Attribute chains that indicate deep hierarchy access (domain violations).
# e.g., window.control_pane.vcs_panel → 3 domains deep.
_ATTR_DOMAIN_MAP = {
    "control_pane": "ui.control_pane",
    "chat_pane": "ui.chat_pane",
    "input_pane": "ui.input_pane",
    "model_picker": "ui.model_picker",
    "vcs_panel": "ui.vcs_panel",
    "file_writer": "sandbox",
    "tool_catalog": "sandbox",
    "tool_router": "agent",
    "response_loop": "agent",
    "knowledge_store": "sessions",
    "evidence_bag": "sessions",
    "config": "config",
    "journal": "runtime",
    "activity": "runtime",
    "docker_runner": "sandbox",
}


def _classify_import(module_path: str) -> str | None:
    """Map a dotted import path to a domain name."""
    for prefix, domain in _IMPORT_DOMAIN_MAP.items():
        if module_path.startswith(prefix):
            return domain
    return None


def _get_attr_chain(node: ast.Attribute) -> list[str]:
    """Walk an Attribute chain and return the full list of names."""
    parts = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    parts.reverse()
    return parts


class _DomainVisitor(ast.NodeVisitor):
    """Walk a Python AST and collect domain access info."""

    def __init__(self):
        self.import_domains: dict[str, str] = {}  # local name → domain
        self.function_domains: dict[str, set[str]] = defaultdict(set)  # func_name → {domains}
        self.class_domains: dict[str, set[str]] = defaultdict(set)  # class_name → {domains}
        self.file_domains: set[str] = set()
        self.deep_accesses: list[dict] = []  # chains deeper than threshold
        self.all_accesses: list[dict] = []  # every classified access
        self._current_func: str | None = None
        self._current_class: str | None = None
        self._depth_warn = 3

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            domain = _classify_import(alias.name)
            if domain:
                local = alias.asname or alias.name.split(".")[-1]
                self.import_domains[local] = domain
                self.file_domains.add(domain)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            domain = _classify_import(node.module)
            if domain:
                for alias in node.names:
                    local = alias.asname or alias.name
                    self.import_domains[local] = domain
                    self.file_domains.add(domain)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        prev = self._current_func
        self._current_func = node.name
        self.generic_visit(node)
        self._current_func = prev

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef):
        prev_class = self._current_class
        self._current_class = node.name
        self.generic_visit(node)
        self._current_class = prev_class

    def visit_Attribute(self, node: ast.Attribute):
        chain = _get_attr_chain(node)
        if len(chain) >= 2:
            # Classify domains touched by this chain
            domains_in_chain = set()
            for part in chain:
                if part in self._attr_domain_map:
                    domains_in_chain.add(self._attr_domain_map[part])
                elif part in self.import_domains:
                    domains_in_chain.add(self.import_domains[part])

            if domains_in_chain:
                access = {
                    "chain": ".".join(chain),
                    "domains": sorted(domains_in_chain),
                    "depth": len(chain),
                    "line": node.lineno,
                    "function": self._current_func,
                    "class": self._current_class,
                }
                self.all_accesses.append(access)

                for d in domains_in_chain:
                    self.file_domains.add(d)
                    if self._current_func:
                        self.function_domains[self._current_func].add(d)
                    if self._current_class:
                        self.class_domains[self._current_class].add(d)

                if len(chain) >= self._depth_warn:
                    self.deep_accesses.append(access)

        self.generic_visit(node)

    @property
    def _attr_domain_map(self):
        return _ATTR_DOMAIN_MAP


def _audit_file(path: Path, depth_warn: int = 3) -> dict | None:
    """Audit a single Python file and return domain metrics."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return None

    visitor = _DomainVisitor()
    visitor._depth_warn = depth_warn
    visitor.visit(tree)

    # Build per-function results
    functions = []
    for name, domains in sorted(visitor.function_domains.items()):
        functions.append({
            "name": name,
            "domains": sorted(domains),
            "domain_count": len(domains),
        })

    classes = []
    for name, domains in sorted(visitor.class_domains.items()):
        classes.append({
            "name": name,
            "domains": sorted(domains),
            "domain_count": len(domains),
        })

    return {
        "file": str(path),
        "file_domain_count": len(visitor.file_domains),
        "file_domains": sorted(visitor.file_domains),
        "functions": functions,
        "classes": classes,
        "deep_accesses": visitor.deep_accesses,
        "import_domains": visitor.import_domains,
    }


def run(arguments: dict) -> dict:
    root = Path(arguments["root"]).resolve()
    component_max = arguments.get("component_max", 1)
    manager_max = arguments.get("manager_max", 3)
    depth_warn = arguments.get("depth_warn", 3)

    if not root.exists():
        return tool_error("domain_boundary_audit", arguments, f"Path not found: {root}")

    # Collect files
    py_files: list[Path] = []
    if root.is_file():
        py_files.append(root)
    else:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
            for f in filenames:
                if f.endswith(".py"):
                    py_files.append(Path(dirpath) / f)

    # Audit each file
    results = []
    violations = []
    for pf in sorted(py_files):
        audit = _audit_file(pf, depth_warn=depth_warn)
        if audit is None:
            continue
        results.append(audit)

        # Check file-level violations
        if audit["file_domain_count"] > manager_max:
            violations.append({
                "file": audit["file"],
                "scope": "file",
                "name": pf.name,
                "domain_count": audit["file_domain_count"],
                "domains": audit["file_domains"],
                "threshold": manager_max,
                "severity": "high",
            })

        # Check function-level violations
        for func in audit["functions"]:
            if func["domain_count"] > component_max:
                severity = "high" if func["domain_count"] > manager_max else "medium"
                violations.append({
                    "file": audit["file"],
                    "scope": "function",
                    "name": func["name"],
                    "domain_count": func["domain_count"],
                    "domains": func["domains"],
                    "threshold": component_max,
                    "severity": severity,
                })

        # Deep access violations
        for access in audit["deep_accesses"]:
            violations.append({
                "file": audit["file"],
                "scope": "access",
                "name": access["chain"],
                "line": access["line"],
                "depth": access["depth"],
                "domains": access["domains"],
                "severity": "medium",
            })

    # Summary
    total_files = len(results)
    files_over = sum(1 for r in results if r["file_domain_count"] > manager_max)
    funcs_over = sum(
        1 for r in results
        for f in r["functions"]
        if f["domain_count"] > component_max
    )
    deep_access_count = sum(len(r["deep_accesses"]) for r in results)

    # Top offenders sorted by domain count
    top_offenders = sorted(results, key=lambda r: r["file_domain_count"], reverse=True)[:10]
    top_offenders_summary = [
        {
            "file": r["file"],
            "domain_count": r["file_domain_count"],
            "domains": r["file_domains"],
        }
        for r in top_offenders
    ]

    return tool_result("domain_boundary_audit", arguments, {
        "summary": {
            "files_scanned": total_files,
            "files_over_threshold": files_over,
            "functions_over_threshold": funcs_over,
            "deep_access_violations": deep_access_count,
            "total_violations": len(violations),
            "thresholds": {
                "component_max": component_max,
                "manager_max": manager_max,
                "depth_warn": depth_warn,
            },
        },
        "top_offenders": top_offenders_summary,
        "violations": violations,
        "details": results,
    })


if __name__ == "__main__":
    standard_main(FILE_METADATA, run)
