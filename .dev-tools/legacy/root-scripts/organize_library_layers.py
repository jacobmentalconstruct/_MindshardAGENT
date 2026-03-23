"""
organize_library_layers.py

Creates a layered library layout for growing microservice ecosystems without
breaking existing root-level imports. Supports dry-run planning and safe apply
(copy by default, optional move).
"""

from __future__ import annotations

TOOL_METADATA = {
    "name": "Library Organizer",
    "description": "Creates a layered library layout for growing microservice ecosystems without breaking imports.",
    "usage": "Analyzes tags and naming conventions to safely copy or move root microservices into a structured directory tree."
}

import argparse
import ast
import json
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


LAYER_ORDER = [
    "reference",
    "ui",
    "storage",
    "structure",
    "meaning",
    "relation",
    "observability",
    "manifold",
    "pipeline",
    "db",
    "core",
]

TAG_LAYER_RULES: List[Tuple[str, Set[str]]] = [
    ("storage", {"storage", "verbatim", "merkle", "temporal", "cid", "hash"}),
    ("structure", {"structure", "dag", "interval", "flow", "positional", "chunking", "chunker"}),
    ("meaning", {"meaning", "semantic", "lexical", "ontology", "vector"}),
    ("relation", {"relation", "identity", "property-graph", "graph", "knowledge-graph"}),
    ("observability", {"observability", "monitoring", "trace", "telemetry", "diagnostic"}),
    ("manifold", {"manifold", "hypergraph", "cross-layer", "superposition"}),
    ("ui", {"ui", "theme", "viewer", "tkinter"}),
    ("pipeline", {"pipeline", "ingest", "embed", "extract", "manifest"}),
    ("db", {"db", "sqlite", "query", "search"}),
]

FILENAME_LAYER_HINTS: List[Tuple[str, str]] = [
    ("tkinter", "ui"),
    ("viewer", "ui"),
    ("theme", "ui"),
    ("explorer", "ui"),
    ("db", "db"),
    ("search", "db"),
    ("chunk", "pipeline"),
    ("ingest", "pipeline"),
    ("embed", "pipeline"),
    ("manifest", "pipeline"),
    ("graph", "relation"),
    ("telemetry", "observability"),
]

SUPPORT_FILE_DEST_MAP = {
    "microservice_std_lib.py": "microservice_std_lib.py",
}


NEW_MODULE_DEST_MAP = {
    "managers.py": "managers/_source_managers.py",
    "microservice_std_lib_registry.py": "orchestrators/microservice_std_lib_registry.py",
    "inject_register_hook.py": "tools/inject_register_hook.py",
    "storage_group.py": "microservices/grouped/storage_group.py",
    "structure_group.py": "microservices/grouped/structure_group.py",
    "meaning_relation_observability_manifold_groups.py": "microservices/grouped/meaning_relation_observability_manifold_groups.py",
    "wasm_modules_spec.py": "modules/wasm_modules_spec.py",
    "files.zip": "assets/files.zip",
}


@dataclass
class FilePlan:
    source: str
    destination: str
    source_type: str
    layer: str
    service_name: str = ""
    class_name: str = ""
    tags: List[str] = field(default_factory=list)
    mode: str = "copy"


@dataclass
class PlanSummary:
    total_files: int
    by_source_type: Dict[str, int]
    by_layer: Dict[str, int]



def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""



def _literal(node: Optional[ast.AST]) -> Any:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except Exception:
        return None



def extract_service_metadata(path: Path) -> Tuple[str, str, List[str]]:
    source = path.read_text(encoding="utf-8", errors="ignore")
    tree = ast.parse(source)

    best_class = ""
    best_name = ""
    best_tags: List[str] = []

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if not node.name.endswith("MS"):
            continue

        svc_name = node.name
        tags: List[str] = []

        for deco in node.decorator_list:
            if isinstance(deco, ast.Call) and _call_name(deco.func) == "service_metadata":
                for kw in deco.keywords:
                    if kw.arg == "name":
                        val = _literal(kw.value)
                        if isinstance(val, str) and val.strip():
                            svc_name = val.strip()
                    elif kw.arg == "tags":
                        val = _literal(kw.value)
                        if isinstance(val, list):
                            tags = [str(x).strip() for x in val if str(x).strip()]
                break

        best_class = node.name
        best_name = svc_name
        best_tags = tags
        break

    if not best_class:
        stem = path.stem.lstrip("_")
        return stem or path.stem, "", []

    return best_name, best_class, best_tags



def classify_layer(filename: str, tags: List[str]) -> str:
    fname = filename.lower()
    if fname.startswith("_reference"):
        return "reference"

    normalized_tags = {t.lower() for t in tags}

    for layer, tag_set in TAG_LAYER_RULES:
        if normalized_tags & tag_set:
            return layer

    for needle, layer in FILENAME_LAYER_HINTS:
        if needle in fname:
            return layer

    return "core"



def plan_root_microservices(root: Path, dest_root: Path, mode: str) -> List[FilePlan]:
    plans: List[FilePlan] = []
    for path in sorted(root.glob("_*MS.py")):
        svc_name, class_name, tags = extract_service_metadata(path)
        layer = classify_layer(path.name, tags)
        dest = dest_root / "microservices" / layer / path.name
        plans.append(
            FilePlan(
                source=str(path),
                destination=str(dest),
                source_type="root_microservice",
                layer=layer,
                service_name=svc_name,
                class_name=class_name,
                tags=tags,
                mode=mode,
            )
        )
    return plans




def plan_support_files(root: Path, dest_root: Path, mode: str) -> List[FilePlan]:
    plans: List[FilePlan] = []
    for name, rel_dest in SUPPORT_FILE_DEST_MAP.items():
        src = root / name
        if not src.exists() or not src.is_file():
            continue
        dest = dest_root / rel_dest
        plans.append(
            FilePlan(
                source=str(src),
                destination=str(dest),
                source_type="support_module",
                layer="support",
                service_name=src.stem,
                class_name="",
                tags=[],
                mode=mode,
            )
        )
    return plans


def plan_new_modules(root: Path, new_dir_name: str, dest_root: Path, mode: str) -> List[FilePlan]:
    plans: List[FilePlan] = []
    new_dir = root / new_dir_name
    if not new_dir.exists():
        return plans

    for path in sorted(new_dir.glob("*")):
        if not path.is_file():
            continue
        rel_dest = NEW_MODULE_DEST_MAP.get(path.name, f"modules/extra/{path.name}")
        if rel_dest.startswith("microservices/grouped/"):
            layer = "grouped"
        elif rel_dest.startswith("managers/"):
            layer = "manager"
        elif rel_dest.startswith("orchestrators/"):
            layer = "orchestrator"
        elif rel_dest.startswith("tools/"):
            layer = "tooling"
        elif rel_dest.startswith("assets/"):
            layer = "asset"
        else:
            layer = "module"

        dest = dest_root / rel_dest
        plans.append(
            FilePlan(
                source=str(path),
                destination=str(dest),
                source_type="new_module",
                layer=layer,
                service_name=path.stem,
                class_name="",
                tags=[],
                mode=mode,
            )
        )

    return plans



def summarize(plans: List[FilePlan]) -> PlanSummary:
    by_source_type: Dict[str, int] = {}
    by_layer: Dict[str, int] = {}
    for p in plans:
        by_source_type[p.source_type] = by_source_type.get(p.source_type, 0) + 1
        by_layer[p.layer] = by_layer.get(p.layer, 0) + 1
    return PlanSummary(total_files=len(plans), by_source_type=by_source_type, by_layer=by_layer)



def ensure_layout_markers(dest_root: Path) -> None:
    package_dirs = [
        dest_root,
        dest_root / "microservices",
        dest_root / "managers",
        dest_root / "orchestrators",
        dest_root / "modules",
        dest_root / "tools",
    ]
    for d in package_dirs:
        d.mkdir(parents=True, exist_ok=True)
        init_py = d / "__init__.py"
        if not init_py.exists():
            init_py.write_text('"""Generated package marker for grouped library layout."""\n', encoding="utf-8")



def apply(plans: List[FilePlan], mode: str) -> None:
    for p in plans:
        src = Path(p.source)
        dst = Path(p.destination)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if mode == "move":
            shutil.move(str(src), str(dst))
        else:
            shutil.copy2(src, dst)



def write_artifacts(dest_root: Path, root: Path, mode: str, plans: List[FilePlan], summary: PlanSummary, applied: bool) -> None:
    catalog_dir = dest_root / "catalog"
    catalog_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "root": str(root),
        "destination_root": str(dest_root),
        "mode": mode,
        "applied": applied,
        "summary": asdict(summary),
        "plans": [asdict(p) for p in plans],
    }

    (catalog_dir / "library_catalog.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines: List[str] = []
    lines.append("# Library Grouping Plan")
    lines.append("")
    lines.append(f"- Applied: `{applied}`")
    lines.append(f"- Mode: `{mode}`")
    lines.append(f"- Total files: `{summary.total_files}`")
    lines.append("")
    lines.append("## By Source Type")
    for key in sorted(summary.by_source_type):
        lines.append(f"- `{key}`: `{summary.by_source_type[key]}`")
    lines.append("")
    lines.append("## By Layer")
    for key in sorted(summary.by_layer):
        lines.append(f"- `{key}`: `{summary.by_layer[key]}`")
    lines.append("")
    lines.append("## Planned Moves/Copies")
    for p in plans:
        lines.append(f"- `{p.source_type}` `{Path(p.source).name}` -> `{p.destination}`")

    (catalog_dir / "library_plan.md").write_text("\n".join(lines) + "\n", encoding="utf-8")



def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Group microservices/modules into a layered library layout.")
    parser.add_argument("--root", default=".", help="Workspace root path.")
    parser.add_argument("--dest", default="library", help="Destination grouped library directory (relative to root).")
    parser.add_argument("--new-modules-dir", default="NEW MICROSERVICES AND MODULES", help="Folder name containing newly added grouped modules.")
    parser.add_argument("--mode", choices=["copy", "move"], default="copy", help="Whether to copy (safe) or move source files.")
    parser.add_argument("--apply", action="store_true", help="Apply copy/move operations. Without this, only dry-run artifacts are produced.")
    return parser



def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    root = Path(args.root).resolve()
    dest_root = (root / args.dest).resolve()

    plans: List[FilePlan] = []
    plans.extend(plan_root_microservices(root, dest_root, mode=args.mode))
    plans.extend(plan_support_files(root, dest_root, mode=args.mode))
    plans.extend(plan_new_modules(root, args.new_modules_dir, dest_root, mode=args.mode))

    summary = summarize(plans)

    if args.apply:
        ensure_layout_markers(dest_root)
        apply(plans, mode=args.mode)

    write_artifacts(dest_root, root, args.mode, plans, summary, applied=bool(args.apply))

    result = {
        "status": "applied" if args.apply else "dry-run",
        "mode": args.mode,
        "destination": str(dest_root),
        "summary": asdict(summary),
        "catalog": str(dest_root / "catalog" / "library_catalog.json"),
        "plan": str(dest_root / "catalog" / "library_plan.md"),
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())