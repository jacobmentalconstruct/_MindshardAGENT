"""
FILE: workspace_audit.py
ROLE: Agent-facing workspace inventory tool.
WHAT IT DOES: Scans a folder and produces a compact summary for mechanical tool use.
HOW TO USE:
  - Metadata: python .final-tools/tools/workspace_audit.py metadata
  - Run: python .final-tools/tools/workspace_audit.py run --input-json "{\"root\": \".\"}"
INPUT OBJECT:
  - root: folder to scan
  - top_n: optional summary list size
  - max_files: optional safety cap
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from common import should_skip_dir, standard_main, tool_result


FILE_METADATA = {
    "tool_name": "workspace_audit",
    "version": "1.0.0",
    "entrypoint": "tools/workspace_audit.py",
    "category": "workspace",
    "summary": "Inventory a local workspace for fast AI-agent orientation.",
    "mcp_name": "workspace_audit",
    "legacy_replaces": [],
    "input_schema": {
        "type": "object",
        "properties": {
            "root": {"type": "string", "description": "Folder to scan."},
            "top_n": {"type": "integer", "default": 15},
            "max_files": {"type": "integer", "default": 20000}
        },
        "required": ["root"],
        "additionalProperties": False
    }
}


ENTRYPOINT_NAMES = {
    "README.md",
    "pyproject.toml",
    "package.json",
    "requirements.txt",
    "Cargo.toml",
    "go.mod",
    "Makefile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
}

DATA_EXTENSIONS = {
    ".json", ".jsonl", ".csv", ".tsv", ".parquet", ".db", ".sqlite", ".sqlite3",
    ".xml", ".kml", ".kmz", ".yaml", ".yml", ".txt"
}

LANGUAGE_BY_EXTENSION = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript React",
    ".jsx": "JavaScript React",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".cs": "C#",
    ".cpp": "C++",
    ".c": "C",
    ".rb": "Ruby",
    ".php": "PHP",
    ".html": "HTML",
    ".css": "CSS",
    ".sql": "SQL",
    ".sh": "Shell",
    ".ps1": "PowerShell",
    ".toml": "TOML",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
}


def _relative(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def run(arguments: dict) -> dict:
    root = Path(arguments["root"]).resolve()
    top_n = int(arguments.get("top_n", 15))
    max_files = int(arguments.get("max_files", 20000))

    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Directory not found: {root}")

    extension_counts: Counter[str] = Counter()
    language_counts: Counter[str] = Counter()
    notable_files: list[dict] = []
    entrypoints: list[str] = []
    large_files: list[tuple[int, str]] = []
    total_files = 0
    total_dirs = 0

    for current_root, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not should_skip_dir(d)]
        total_dirs += len(dirs)
        current_path = Path(current_root)

        for name in files:
            total_files += 1
            if total_files > max_files:
                raise RuntimeError(f"Aborted after scanning {max_files} files. Increase max_files if needed.")

            path = current_path / name
            suffix = path.suffix.lower()
            rel = _relative(path, root)
            size = path.stat().st_size

            extension_counts[suffix or "<no_ext>"] += 1
            if suffix in LANGUAGE_BY_EXTENSION:
                language_counts[LANGUAGE_BY_EXTENSION[suffix]] += 1

            if name in ENTRYPOINT_NAMES or name.lower().startswith("readme"):
                entrypoints.append(rel)

            if suffix in DATA_EXTENSIONS:
                notable_files.append({"path": rel, "kind": "data", "size_bytes": size})
            elif suffix in {".py", ".js", ".ts", ".tsx", ".jsx", ".ps1", ".sh"}:
                notable_files.append({"path": rel, "kind": "code", "size_bytes": size})

            large_files.append((size, rel))

    result = {
        "root": str(root),
        "summary": {
            "total_files": total_files,
            "total_dirs": total_dirs,
            "top_extensions": dict(extension_counts.most_common(top_n)),
            "top_languages": dict(language_counts.most_common(top_n)),
        },
        "entrypoints": sorted(entrypoints)[:top_n],
        "largest_files": [
            {"path": rel, "size_bytes": size}
            for size, rel in sorted(large_files, key=lambda item: (-item[0], item[1]))[:top_n]
        ],
        "sample_notable_files": sorted(notable_files, key=lambda item: (item["kind"], item["path"]))[: top_n * 2],
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
