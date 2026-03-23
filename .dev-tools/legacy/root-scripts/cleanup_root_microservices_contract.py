TOOL_METADATA = {
    "name": "MS Contract Cleanup",
    "description": "Standardizes microservice contracts and ensures the health endpoint is properly decorated.",
    "usage": "Run against a root directory to automatically inject missing service_metadata and get_health() methods."
}

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def build_line_offsets(text: str) -> List[int]:
    offsets = [0]
    for line in text.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def to_offset(offsets: List[int], lineno: int, col: int) -> int:
    return offsets[lineno - 1] + col


def parse_header_list(text: str, label: str) -> List[str]:
    chunk = "\n".join(text.splitlines()[:80])
    match = re.search(rf"{re.escape(label)}\s*:\s*(.+)", chunk)
    if not match:
        return []
    raw = match.group(1).strip()
    if raw.lower() in {"", "none", "n/a", "na"}:
        return []
    parts = [p.strip().strip("'\"") for p in raw.split(",")]
    seen = set()
    out: List[str] = []
    for part in parts:
        if not part:
            continue
        key = part.lower()
        if key in {"none", "n/a", "na"}:
            continue
        if key not in seen:
            seen.add(key)
            out.append(part)
    return out


def is_service_metadata_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and (
        (isinstance(node.func, ast.Name) and node.func.id == "service_metadata")
        or (isinstance(node.func, ast.Attribute) and node.func.attr == "service_metadata")
    )


def is_service_endpoint_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and (
        (isinstance(node.func, ast.Name) and node.func.id == "service_endpoint")
        or (isinstance(node.func, ast.Attribute) and node.func.attr == "service_endpoint")
    )


def collect_class_side_effects(class_node: ast.ClassDef) -> List[str]:
    seen = set()
    effects: List[str] = []
    for node in class_node.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if not is_service_endpoint_call(dec):
                continue
            for kw in dec.keywords:
                if kw.arg != "side_effects":
                    continue
                if isinstance(kw.value, (ast.List, ast.Tuple)):
                    for elt in kw.value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            if elt.value not in seen:
                                seen.add(elt.value)
                                effects.append(elt.value)
    return effects


def default_service_metadata(
    class_name: str,
    internal_deps: List[str],
    external_deps: List[str],
    side_effects: List[str],
) -> str:
    call = ast.Call(
        func=ast.Name(id="service_metadata", ctx=ast.Load()),
        args=[],
        keywords=[
            ast.keyword(arg="name", value=ast.Constant(value=class_name)),
            ast.keyword(arg="version", value=ast.Constant(value="1.0.0")),
            ast.keyword(
                arg="description",
                value=ast.Constant(value=f"Auto-generated metadata for {class_name}."),
            ),
            ast.keyword(
                arg="tags",
                value=ast.List(elts=[ast.Constant(value="microservice")], ctx=ast.Load()),
            ),
            ast.keyword(arg="capabilities", value=ast.List(elts=[], ctx=ast.Load())),
            ast.keyword(
                arg="side_effects",
                value=ast.List(
                    elts=[ast.Constant(value=e) for e in side_effects],
                    ctx=ast.Load(),
                ),
            ),
            ast.keyword(
                arg="internal_dependencies",
                value=ast.List(
                    elts=[ast.Constant(value=e) for e in internal_deps],
                    ctx=ast.Load(),
                ),
            ),
            ast.keyword(
                arg="external_dependencies",
                value=ast.List(
                    elts=[ast.Constant(value=e) for e in external_deps],
                    ctx=ast.Load(),
                ),
            ),
        ],
    )
    return f"@{ast.unparse(call)}\n"


def service_endpoint_health_decorator(indent: str) -> str:
    return (
        f"{indent}@service_endpoint(inputs={{}}, outputs={{'status': 'str', 'uptime': 'float'}}, "
        "description='Standardized health check for service status.', tags=['diagnostic', 'health'])\n"
    )


def service_health_method(indent: str) -> str:
    return (
        f"\n{service_endpoint_health_decorator(indent)}"
        f"{indent}def get_health(self):\n"
        f"{indent}    \"\"\"Returns the operational status of the service.\"\"\"\n"
        f"{indent}    start = getattr(self, 'start_time', None)\n"
        f"{indent}    if start is None:\n"
        f"{indent}        start = time.time()\n"
        f"{indent}        self.start_time = start\n"
        f"{indent}    return {{'status': 'online', 'uptime': time.time() - start}}\n"
    )


def cleanup_file(path: Path) -> Optional[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None

    class_nodes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    if not class_nodes:
        return None
    # Prefer the actual microservice class, not helper/dataclass types.
    ms_class_nodes = [n for n in class_nodes if n.name.endswith("MS")]
    class_node = ms_class_nodes[0] if ms_class_nodes else class_nodes[0]

    offsets = build_line_offsets(text)
    edits: List[Tuple[int, int, str, str]] = []
    reasons: List[str] = []

    internal_default = parse_header_list(text, "INTERNAL_DEPENDENCIES")
    external_default = parse_header_list(text, "EXTERNAL_DEPENDENCIES")
    side_effects_default = collect_class_side_effects(class_node)

    metadata_decorator = None
    for dec in class_node.decorator_list:
        if is_service_metadata_call(dec):
            metadata_decorator = dec
            break

    if metadata_decorator is None:
        class_start = to_offset(offsets, class_node.lineno, 0)
        edits.append(
            (
                class_start,
                class_start,
                default_service_metadata(
                    class_node.name,
                    internal_default,
                    external_default,
                    side_effects_default,
                ),
                "added_service_metadata",
            )
        )
        reasons.append("added_service_metadata")
    else:
        present = {kw.arg for kw in metadata_decorator.keywords if kw.arg}
        missing: Dict[str, ast.AST] = {}
        if "internal_dependencies" not in present:
            missing["internal_dependencies"] = ast.List(
                elts=[ast.Constant(value=e) for e in internal_default],
                ctx=ast.Load(),
            )
        if "external_dependencies" not in present:
            missing["external_dependencies"] = ast.List(
                elts=[ast.Constant(value=e) for e in external_default],
                ctx=ast.Load(),
            )
        if "side_effects" not in present:
            missing["side_effects"] = ast.List(
                elts=[ast.Constant(value=e) for e in side_effects_default],
                ctx=ast.Load(),
            )
        if missing:
            new_keywords = list(metadata_decorator.keywords)
            for key in ("side_effects", "internal_dependencies", "external_dependencies"):
                if key in missing:
                    new_keywords.append(ast.keyword(arg=key, value=missing[key]))
            new_call = ast.Call(
                func=metadata_decorator.func,
                args=metadata_decorator.args,
                keywords=new_keywords,
            )
            start = to_offset(offsets, metadata_decorator.lineno, metadata_decorator.col_offset)
            end = to_offset(offsets, metadata_decorator.end_lineno, metadata_decorator.end_col_offset)
            edits.append((start, end, ast.unparse(new_call), "expanded_service_metadata"))
            reasons.append("expanded_service_metadata")

    health_fn = None
    for node in class_node.body:
        if isinstance(node, ast.FunctionDef) and node.name == "get_health":
            health_fn = node
            break

    needs_time_import = False
    if health_fn is None:
        indent = " " * (class_node.col_offset + 4)
        insert = to_offset(offsets, class_node.end_lineno, class_node.end_col_offset)
        edits.append((insert, insert, service_health_method(indent), "added_get_health"))
        reasons.append("added_get_health")
        needs_time_import = True
    else:
        has_endpoint = any(is_service_endpoint_call(dec) for dec in health_fn.decorator_list)
        if not has_endpoint:
            fn_start = to_offset(offsets, health_fn.lineno, 0)
            indent = " " * health_fn.col_offset
            edits.append(
                (
                    fn_start,
                    fn_start,
                    service_endpoint_health_decorator(indent),
                    "decorated_get_health",
                )
            )
            reasons.append("decorated_get_health")

    has_time_import = False
    has_metadata_import = False
    has_endpoint_import = False
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "time":
                    has_time_import = True
        elif isinstance(node, ast.ImportFrom) and node.module == "microservice_std_lib":
            for alias in node.names:
                if alias.name == "service_metadata":
                    has_metadata_import = True
                if alias.name == "service_endpoint":
                    has_endpoint_import = True

    import_lines: List[str] = []
    if needs_time_import and not has_time_import:
        import_lines.append("import time\n")
    if reasons and (not has_metadata_import or not has_endpoint_import):
        import_lines.append("from microservice_std_lib import service_metadata, service_endpoint\n")

    if import_lines:
        insert_after_line = 1
        body = list(tree.body)
        idx = 0
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            insert_after_line = body[0].end_lineno + 1
            idx = 1
        while idx < len(body) and isinstance(body[idx], (ast.Import, ast.ImportFrom)):
            insert_after_line = body[idx].end_lineno + 1
            idx += 1
        import_insert = to_offset(offsets, insert_after_line, 0)
        edits.append((import_insert, import_insert, "".join(import_lines), "imports"))
        reasons.append("imports")

    if not edits:
        return None

    edits.sort(key=lambda x: (x[0], x[1]), reverse=True)
    new_text = text
    for start, end, replacement, _ in edits:
        new_text = new_text[:start] + replacement + new_text[end:]

    return {
        "path": str(path),
        "text": new_text,
        "reasons": sorted(set(reasons)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Cleanup root microservice contract fields and health endpoint.")
    parser.add_argument("--root", default=".", help="Project root containing _*MS.py files.")
    parser.add_argument("--apply", action="store_true", help="Write edits in-place.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    files = sorted([p for p in root.glob("_*MS.py") if p.is_file()])
    changed: List[Dict[str, Any]] = []
    for path in files:
        result = cleanup_file(path)
        if result:
            changed.append(result)

    summary = {
        "root": str(root),
        "files_scanned": len(files),
        "files_changed": len(changed),
        "changes": [
            {"file": Path(item["path"]).name, "reasons": item["reasons"]}
            for item in changed
        ],
    }
    print(json.dumps(summary, indent=2))

    if args.apply:
        for item in changed:
            Path(item["path"]).write_text(item["text"], encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
