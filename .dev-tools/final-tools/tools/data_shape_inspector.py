"""
FILE: data_shape_inspector.py
ROLE: Agent-facing data inspection tool.
WHAT IT DOES: Inspects common local data formats and returns a compact structural summary through the same JSON contract as the other final tools.
SUPPORTED FORMATS:
  - JSON / JSONL
  - CSV / TSV
  - XML / KML / KMZ
  - SQLite
HOW TO USE:
  - Metadata: python .final-tools/tools/data_shape_inspector.py metadata
  - Run: python .final-tools/tools/data_shape_inspector.py run --input-json "{\"path\": \"data.json\"}"
INPUT OBJECT:
  - path: file to inspect
  - max_depth: optional JSON schema depth cap
  - sample_rows: optional row sample cap
  - json_path_db: optional SQLite output path for flattened JSON paths
"""

from __future__ import annotations

import csv
import json
import sqlite3
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result


FILE_METADATA = {
    "tool_name": "data_shape_inspector",
    "version": "1.0.0",
    "entrypoint": "tools/data_shape_inspector.py",
    "category": "data",
    "summary": "Inspect local data files and return compact structural summaries.",
    "mcp_name": "data_shape_inspector",
    "legacy_replaces": [
        ".dev-tools/analyze_timeline_schema.py",
        ".dev-tools/analyze_kml_schema.py",
        ".dev-tools/sql_schema_mapper.py"
    ],
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to inspect."},
            "max_depth": {"type": "integer", "default": 6},
            "sample_rows": {"type": "integer", "default": 5},
            "json_path_db": {"type": "string", "description": "Optional SQLite output path for flattened JSON paths."}
        },
        "required": ["path"],
        "additionalProperties": False
    }
}


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _json_schema(obj: Any, depth: int, max_depth: int) -> Any:
    if depth >= max_depth:
        return "max_depth_reached"
    if isinstance(obj, dict):
        return {key: _json_schema(value, depth + 1, max_depth) for key, value in obj.items()}
    if isinstance(obj, list):
        if not obj:
            return ["empty_list"]
        return [_json_schema(obj[0], depth + 1, max_depth)]
    return type(obj).__name__


def _flatten_json(obj: Any, prefix: str = "", out: dict[str, tuple[str, str]] | None = None) -> dict[str, tuple[str, str]]:
    if out is None:
        out = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            next_prefix = f"{prefix}.{key}" if prefix else key
            _flatten_json(value, next_prefix, out)
    elif isinstance(obj, list):
        if obj:
            _flatten_json(obj[0], f"{prefix}[]" if prefix else "[]", out)
        else:
            out[prefix] = ("list", "[]")
    else:
        out[prefix] = (type(obj).__name__, str(obj)[:80])
    return out


def _write_json_path_db(payload: Any, out_path: Path) -> str:
    flat = _flatten_json(payload)
    conn = sqlite3.connect(out_path)
    try:
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS json_paths")
        cur.execute(
            """
            CREATE TABLE json_paths (
                path TEXT PRIMARY KEY,
                data_type TEXT NOT NULL,
                sample_value TEXT
            )
            """
        )
        cur.executemany(
            "INSERT INTO json_paths (path, data_type, sample_value) VALUES (?, ?, ?)",
            [(path, dtype, sample) for path, (dtype, sample) in flat.items()],
        )
        conn.commit()
    finally:
        conn.close()
    return str(out_path.resolve())


def _inspect_json(path: Path, max_depth: int, json_path_db: Path | None) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    result = {
        "format": "json",
        "path": str(path.resolve()),
        "root_type": type(payload).__name__,
        "schema": _json_schema(payload, 0, max_depth),
    }
    if isinstance(payload, dict):
        result["top_level_keys"] = sorted(payload.keys())[:100]
    if isinstance(payload, list):
        result["item_count"] = len(payload)
    if json_path_db is not None:
        result["json_path_db"] = _write_json_path_db(payload, json_path_db)
    return result


def _inspect_jsonl(path: Path, max_depth: int, sample_rows: int) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines()
    parsed = [json.loads(line) for line in lines[:sample_rows] if line.strip()]
    return {
        "format": "jsonl",
        "path": str(path.resolve()),
        "line_count": len(lines),
        "sample_schema": [_json_schema(item, 0, max_depth) for item in parsed],
    }


def _inspect_delimited(path: Path, sample_rows: int, delimiter: str) -> dict:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle, delimiter=delimiter))
    header = rows[0] if rows else []
    return {
        "format": "tsv" if delimiter == "\t" else "csv",
        "path": str(path.resolve()),
        "row_count": max(len(rows) - 1, 0),
        "column_count": len(header),
        "header": header,
        "sample_rows": rows[1:1 + sample_rows],
    }


def _walk_xml(elem: ET.Element, path: str, path_counts: Counter[str], tag_counts: Counter[str], schema_map: dict[str, dict]) -> None:
    tag = _strip_ns(elem.tag)
    current_path = f"{path}/{tag}" if path else f"/{tag}"
    path_counts[current_path] += 1
    tag_counts[tag] += 1
    schema_map[current_path] = {
        "tag": tag,
        "attributes": sorted(elem.attrib.keys()),
        "child_tags": sorted({_strip_ns(child.tag) for child in list(elem)}),
        "has_text": bool((elem.text or "").strip()),
    }
    for child in list(elem):
        _walk_xml(child, current_path, path_counts, tag_counts, schema_map)


def _load_xml_root(path: Path) -> tuple[ET.Element, str]:
    if path.suffix.lower() == ".kmz":
        with zipfile.ZipFile(path, "r") as archive:
            kml_names = [name for name in archive.namelist() if name.lower().endswith(".kml")]
            if not kml_names:
                raise FileNotFoundError("No .kml file found inside the .kmz archive.")
            chosen = "doc.kml" if "doc.kml" in kml_names else kml_names[0]
            with archive.open(chosen) as handle:
                tree = ET.parse(handle)
                return tree.getroot(), f"{path.resolve()}::{chosen}"
    tree = ET.parse(path)
    return tree.getroot(), str(path.resolve())


def _inspect_xml_like(path: Path) -> dict:
    root, source = _load_xml_root(path)
    tag_counts: Counter[str] = Counter()
    path_counts: Counter[str] = Counter()
    schema_map: dict[str, dict] = {}
    _walk_xml(root, "", path_counts, tag_counts, schema_map)
    return {
        "format": path.suffix.lower().lstrip("."),
        "path": source,
        "root_tag": _strip_ns(root.tag),
        "tag_counts": dict(tag_counts.most_common(50)),
        "path_counts": dict(path_counts.most_common(50)),
        "schema_by_path": schema_map,
    }


def _inspect_sqlite(path: Path) -> dict:
    conn = sqlite3.connect(path)
    try:
        cur = conn.cursor()
        tables = [row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        table_payload = []
        for table in tables:
            columns = [
                {"cid": row[0], "name": row[1], "type": row[2], "notnull": bool(row[3]), "pk": bool(row[5])}
                for row in cur.execute(f"PRAGMA table_info('{table}')")
            ]
            row_count = cur.execute(f"SELECT COUNT(*) FROM '{table}'").fetchone()[0]
            table_payload.append({"table": table, "row_count": row_count, "columns": columns})
        return {
            "format": "sqlite",
            "path": str(path.resolve()),
            "table_count": len(table_payload),
            "tables": table_payload,
        }
    finally:
        conn.close()


def run(arguments: dict) -> dict:
    path = Path(arguments["path"]).resolve()
    max_depth = int(arguments.get("max_depth", 6))
    sample_rows = int(arguments.get("sample_rows", 5))
    json_path_db = Path(arguments["json_path_db"]).resolve() if arguments.get("json_path_db") else None

    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".json":
        result = _inspect_json(path, max_depth, json_path_db)
    elif suffix == ".jsonl":
        result = _inspect_jsonl(path, max_depth, sample_rows)
    elif suffix == ".csv":
        result = _inspect_delimited(path, sample_rows, ",")
    elif suffix == ".tsv":
        result = _inspect_delimited(path, sample_rows, "\t")
    elif suffix in {".xml", ".kml", ".kmz"}:
        result = _inspect_xml_like(path)
    elif suffix in {".db", ".sqlite", ".sqlite3"}:
        result = _inspect_sqlite(path)
    else:
        raise ValueError(f"Unsupported file type: {suffix or '<none>'}")

    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
