"""
FILE: module_decomp_planner.py
ROLE: Static analysis tool for planning safe decomposition of large Python modules.
WHAT IT DOES:
  - Parses a Python file with AST
  - Groups top-level definitions by section-comment headers (# ── Name ──)
  - Detects shared closure / module-level name references between groups
  - Identifies which groups are safe to extract vs. tightly coupled
  - Outputs a ranked decomposition plan with dependency edges
HOW TO USE:
  - Metadata: python .dev-tools/tools/module_decomp_planner.py metadata
  - Run:      python .dev-tools/tools/module_decomp_planner.py run --input-json '{"path": "src/app.py"}'
INPUT:
  - path: path to the Python file to analyse
  - section_pattern: regex for section comment headers (default: "# [─—═]{2,}")
  - include_private: include _underscore definitions (default: true)
NOTES:
  - Closure variables are names used inside a nested function but defined in the outer scope.
  - A group with many inbound edges from other groups is a "hub" — hard to extract cleanly.
  - Groups with zero inbound edges are the safest to extract first.
"""

from __future__ import annotations

import ast
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result

FILE_METADATA = {
    "tool_name": "module_decomp_planner",
    "version": "1.2.0",
    "entrypoint": "tools/module_decomp_planner.py",
    "category": "architecture",
    "summary": "Plan the safe decomposition of a large Python module into smaller ones.",
    "mcp_name": "module_decomp_planner",
    "notes": (
        "Guesses are labelled as such. Section detection depends on comment conventions. "
        "Use scan_inner=true for closure-heavy files like app.py where everything lives inside "
        "a single outer function. Use scan_class='ClassName' for large class files."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the Python file to analyse."
            },
            "section_pattern": {
                "type": "string",
                "description": "Regex matching section-header comment lines.",
                "default": r"#[\s]*[─—═\-]{2,}"
            },
            "include_private": {
                "type": "boolean",
                "description": "Include definitions whose names start with _.",
                "default": True
            },
            "scan_inner": {
                "type": "boolean",
                "description": (
                    "If true, scan inside the first large top-level function for inner "
                    "function/class definitions. Use for closure-heavy files like app.py."
                ),
                "default": False,
            },
            "scan_class": {
                "type": "string",
                "description": (
                    "If set, scan methods of this class instead of top-level defs. "
                    "Use for large single-class files like control_pane.py."
                ),
                "default": "",
            },
        },
        "required": ["path"],
        "additionalProperties": False,
    },
}


# ── AST helpers ──────────────────────────────────────────────

def _collect_names_used(node: ast.AST) -> set[str]:
    """All Name.id values referenced inside a subtree."""
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _collect_names_defined(node: ast.AST) -> set[str]:
    """Names defined (assigned, function args, etc.) inside a subtree."""
    names: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(n.name)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            names.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for alias in n.names:
                names.add(alias.asname or alias.name.split(".")[0])
    return names


# ── Section detection ─────────────────────────────────────────

def _extract_sections(source: str, tree: ast.Module, section_re: re.Pattern) -> list[dict]:
    """
    Return a list of sections, each with a header label and line range.
    Definitions not preceded by any section header go into '__preamble__'.
    """
    lines = source.splitlines()
    # Map line numbers (1-based) to section labels
    section_starts: list[tuple[int, str]] = []
    for lineno, line in enumerate(lines, start=1):
        m = section_re.search(line)
        if m:
            # Extract label text between the decorative characters
            label_text = re.sub(r"[─—═\-#\s]+", " ", line).strip()
            section_starts.append((lineno, label_text or f"section_{lineno}"))

    # Build sections with line ranges
    sections: list[dict] = []
    if not section_starts or section_starts[0][0] > 1:
        # Everything before first section header
        end = section_starts[0][0] - 1 if section_starts else len(lines)
        sections.append({"label": "__preamble__", "start_line": 1, "end_line": end, "defs": []})

    for idx, (start, label) in enumerate(section_starts):
        end = section_starts[idx + 1][0] - 1 if idx + 1 < len(section_starts) else len(lines)
        sections.append({"label": label, "start_line": start, "end_line": end, "defs": []})

    return sections


def _assign_defs_to_sections(tree: ast.Module, sections: list[dict], include_private: bool) -> None:
    """Assign each top-level definition to the section whose line range contains it."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                                  ast.Assign, ast.AnnAssign, ast.AugAssign)):
            continue
        # Only top-level (direct children of Module)
        if not any(node is child for child in ast.iter_child_nodes(tree)):
            continue
        lineno = node.lineno
        name = getattr(node, "name", None)
        if name is None:
            # For assignments, try to get the target name
            if isinstance(node, ast.Assign):
                targets = node.targets
                name = targets[0].id if targets and isinstance(targets[0], ast.Name) else f"<assign@{lineno}>"
            elif isinstance(node, ast.AnnAssign):
                name = node.target.id if isinstance(node.target, ast.Name) else f"<annassign@{lineno}>"
            else:
                name = f"<stmt@{lineno}>"
        if not include_private and name.startswith("_") and name != "__all__":
            continue
        for section in reversed(sections):  # last matching section wins
            if section["start_line"] <= lineno <= section["end_line"]:
                section["defs"].append({
                    "name": name,
                    "kind": type(node).__name__,
                    "lineno": lineno,
                    "end_lineno": getattr(node, "end_lineno", lineno),
                })
                break


# ── Dependency analysis ───────────────────────────────────────

def _build_dependency_edges(
    tree: ast.Module,
    sections: list[dict],
    source_lines: list[str],
) -> list[dict]:
    """
    For each section, find which names it uses that are *defined* in other sections.
    Returns edge list: [{from_section, to_section, shared_names}]
    """
    # Build name → section label map
    name_to_section: dict[str, str] = {}
    for s in sections:
        for d in s["defs"]:
            name_to_section[d["name"]] = s["label"]

    # For each top-level def node, collect names used vs. names defined inside it
    edges: list[dict] = []
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        # Which section owns this node?
        owner_label = name_to_section.get(node.name)
        if owner_label is None:
            continue
        used = _collect_names_used(node)
        defined_inside = _collect_names_defined(node)
        # Names used but not defined inside → likely references to outer scope / other modules
        external_refs = used - defined_inside - {node.name}
        # Which sections define those names?
        cross: dict[str, set[str]] = defaultdict(set)
        for ref in external_refs:
            target_section = name_to_section.get(ref)
            if target_section and target_section != owner_label:
                cross[target_section].add(ref)
        for target, names in cross.items():
            edges.append({
                "from": owner_label,
                "to": target,
                "shared_names": sorted(names),
                "count": len(names),
            })

    return edges


# ── Decomposition recommendation ─────────────────────────────

def _score_sections(sections: list[dict], edges: list[dict]) -> list[dict]:
    """
    Score each section for extractability:
      - inbound_edges: how many other sections depend on defs in this one (hard to move)
      - outbound_edges: how many sections this one depends on (needs those as imports)
      - def_count: number of definitions
      - line_count: lines covered
    """
    inbound: dict[str, int] = defaultdict(int)
    outbound: dict[str, int] = defaultdict(int)
    inbound_names: dict[str, list[str]] = defaultdict(list)
    outbound_names: dict[str, list[str]] = defaultdict(list)

    for edge in edges:
        outbound[edge["from"]] += edge["count"]
        inbound[edge["to"]] += edge["count"]
        outbound_names[edge["from"]].extend(edge["shared_names"])
        inbound_names[edge["to"]].extend(edge["shared_names"])

    scored = []
    for s in sections:
        label = s["label"]
        def_count = len(s["defs"])
        line_count = s["end_line"] - s["start_line"] + 1
        in_count = inbound[label]
        out_count = outbound[label]
        # Heuristic: lower score = safer/easier to extract
        extractability_score = in_count * 3 + out_count
        recommendation = (
            "safe to extract" if in_count == 0
            else "extract with care — others depend on it" if in_count <= 3
            else "hub — extract last or keep in place"
        )
        scored.append({
            "label": label,
            "start_line": s["start_line"],
            "end_line": s["end_line"],
            "line_count": line_count,
            "def_count": def_count,
            "definitions": [d["name"] for d in s["defs"]],
            "inbound_refs": in_count,
            "outbound_refs": out_count,
            "names_others_depend_on": sorted(set(inbound_names[label])),
            "names_this_depends_on": sorted(set(outbound_names[label])),
            "extractability_score": extractability_score,
            "recommendation": recommendation,
            "is_guess": True,  # Static analysis — runtime behaviour may differ
        })

    scored.sort(key=lambda x: x["extractability_score"])
    return scored


# ── Inner-function / class-method scan ───────────────────────

def _find_outer_function(tree: ast.Module) -> ast.FunctionDef | None:
    """Return the largest top-level function (by line count) — used for scan_inner mode."""
    best = None
    best_lines = 0
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lines = (node.end_lineno or node.lineno) - node.lineno
            if lines > best_lines:
                best = node
                best_lines = lines
    return best


def _find_class(tree: ast.Module, class_name: str) -> ast.ClassDef | None:
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    return None


def _extract_inner_sections(
    source: str,
    container: ast.AST,
    section_re: re.Pattern,
    include_private: bool,
) -> tuple[list[dict], list[dict]]:
    """
    Extract sections and their defs from inside a function or class body.
    Returns (sections, edges).
    """
    lines = source.splitlines()

    # Find section headers within container line range
    container_start = container.lineno
    container_end = getattr(container, "end_lineno", len(lines))
    section_starts: list[tuple[int, str]] = []
    for lineno in range(container_start, container_end + 1):
        line = lines[lineno - 1] if lineno <= len(lines) else ""
        m = section_re.search(line)
        if m:
            label_text = re.sub(r"[─—═\-#\s]+", " ", line).strip()
            section_starts.append((lineno, label_text or f"section_{lineno}"))

    # Build sections
    sections: list[dict] = []
    if not section_starts or section_starts[0][0] > container_start:
        end = section_starts[0][0] - 1 if section_starts else container_end
        sections.append({"label": "__preamble__", "start_line": container_start, "end_line": end, "defs": []})
    for idx, (start, label) in enumerate(section_starts):
        end = section_starts[idx + 1][0] - 1 if idx + 1 < len(section_starts) else container_end
        sections.append({"label": label, "start_line": start, "end_line": end, "defs": []})

    # Collect direct child defs of container (one level deep)
    child_nodes: list[ast.AST] = []
    if isinstance(container, ast.ClassDef):
        child_nodes = list(ast.iter_child_nodes(container))
    elif isinstance(container, (ast.FunctionDef, ast.AsyncFunctionDef)):
        child_nodes = list(ast.iter_child_nodes(container))

    name_to_section: dict[str, str] = {}
    for node in child_nodes:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                                  ast.Assign, ast.AnnAssign)):
            continue
        lineno = node.lineno
        name = getattr(node, "name", None)
        if name is None:
            if isinstance(node, ast.Assign):
                t = node.targets
                name = t[0].id if t and isinstance(t[0], ast.Name) else f"<assign@{lineno}>"
            elif isinstance(node, ast.AnnAssign):
                name = node.target.id if isinstance(node.target, ast.Name) else f"<annassign@{lineno}>"
            else:
                name = f"<stmt@{lineno}>"
        if not include_private and name.startswith("_") and name not in ("__init__", "__all__"):
            continue
        for section in reversed(sections):
            if section["start_line"] <= lineno <= section["end_line"]:
                section["defs"].append({
                    "name": name,
                    "kind": type(node).__name__,
                    "lineno": lineno,
                    "end_lineno": getattr(node, "end_lineno", lineno),
                })
                name_to_section[name] = section["label"]
                break

    # Build dependency edges between sections
    edges: list[dict] = []
    for node in child_nodes:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        owner_label = name_to_section.get(node.name)
        if owner_label is None:
            continue
        used = _collect_names_used(node)
        defined_inside = _collect_names_defined(node)
        external_refs = used - defined_inside - {node.name}
        cross: dict[str, set[str]] = defaultdict(set)
        for ref in external_refs:
            target_section = name_to_section.get(ref)
            if target_section and target_section != owner_label:
                cross[target_section].add(ref)
        for target, names in cross.items():
            edges.append({
                "from": owner_label,
                "to": target,
                "shared_names": sorted(names),
                "count": len(names),
            })

    return sections, edges


# ── Entry point ───────────────────────────────────────────────

def run(arguments: dict) -> dict:
    path = Path(arguments["path"]).resolve()
    section_pattern = arguments.get("section_pattern", r"#[\s]*[─—═\-]{2,}")
    include_private = bool(arguments.get("include_private", True))
    scan_inner = bool(arguments.get("scan_inner", False))
    scan_class = arguments.get("scan_class", "")

    if not path.exists():
        return tool_result(FILE_METADATA["tool_name"], arguments,
                           {"message": f"File not found: {path}"}, status="error")

    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return tool_result(FILE_METADATA["tool_name"], arguments,
                           {"message": f"SyntaxError: {exc}"}, status="error")

    section_re = re.compile(section_pattern)
    scan_mode = "top-level"

    if scan_class:
        container = _find_class(tree, scan_class)
        if container is None:
            return tool_result(FILE_METADATA["tool_name"], arguments,
                               {"message": f"Class '{scan_class}' not found in {path}"}, status="error")
        sections, edges = _extract_inner_sections(source, container, section_re, include_private)
        scan_mode = f"class:{scan_class}"
    elif scan_inner:
        container = _find_outer_function(tree)
        if container is None:
            return tool_result(FILE_METADATA["tool_name"], arguments,
                               {"message": "No top-level function found for scan_inner mode."}, status="error")
        sections, edges = _extract_inner_sections(source, container, section_re, include_private)
        scan_mode = f"inner:{container.name}"
    else:
        sections = _extract_sections(source, tree, section_re)
        _assign_defs_to_sections(tree, sections, include_private)
        edges = _build_dependency_edges(tree, sections, source.splitlines())

    scored = _score_sections(sections, edges)

    # Summary stats
    total_lines = len(source.splitlines())
    total_defs = sum(len(s["defs"]) for s in sections)
    safe_count = sum(1 for s in scored if s["inbound_refs"] == 0 and s["label"] != "__preamble__")

    result = {
        "file": str(path),
        "scan_mode": scan_mode,
        "total_lines": total_lines,
        "total_definitions": total_defs,
        "section_count": len(sections),
        "dependency_edges": len(edges),
        "sections_safe_to_extract": safe_count,
        "analysis_note": (
            "GUESS: Static analysis only. Closure variables and dynamic attribute access "
            "are not fully tracked. Verify dependency edges before splitting."
        ),
        "sections": scored,
        "edges": sorted(edges, key=lambda e: -e["count"]),
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
