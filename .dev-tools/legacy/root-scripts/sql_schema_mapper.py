TOOL_METADATA = {
    "name": "SQL Schema Mapper",
    "description": "Flattens JSON paths into a queryable SQLite database.",
    "usage": (
        "python sql_schema_mapper.py <workspace_folder_or_json_file> "
        "[--out path/to/output.db]"
    )
}

import argparse
import json
import sqlite3
from pathlib import Path


def flatten_json(y, sep='.'):
    """Flattens a nested JSON object into dot-notation paths."""
    out = {}

    def flatten(x, name=''):
        if isinstance(x, dict):
            for key in x:
                flatten(x[key], name + key + sep)

        elif isinstance(x, list):
            if len(x) > 0:
                # Sample the first item in the list to infer structure
                flatten(x[0], name + sep)
            else:
                out[name[:-1]] = ("list", "[]")

        else:
            out[name[:-1]] = (type(x).__name__, str(x)[:50])  # type + short sample

    flatten(y)
    return out


def resolve_paths(target: Path, out_path: Path | None = None) -> tuple[Path, Path]:
    """
    Accept either:
    - a workspace folder containing Timeline.json
    - a direct path to a JSON file

    Returns:
    - json_path
    - db_path
    """
    if target.is_dir():
        json_path = target / "Timeline.json"
        db_path = out_path if out_path else target / "schema_map.db"
        return json_path, db_path

    if target.is_file():
        json_path = target
        if out_path:
            db_path = out_path
        else:
            db_path = target.with_name(f"{target.stem}_schema_map.db")
        return json_path, db_path

    raise FileNotFoundError(f"Input path not found: {target}")


def map_to_sqlite(target: Path, out_path: Path | None = None):
    json_path, db_path = resolve_paths(target, out_path)

    if not json_path.exists():
        print(f"Error: {json_path} not found.")
        return

    print(f"Parsing JSON into memory from: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print("Flattening structure...")
    flat_schema = flatten_json(data)

    print(f"Building queryable SQLite map at: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('DROP TABLE IF EXISTS schema_map')
    cursor.execute('''
        CREATE TABLE schema_map (
            path TEXT PRIMARY KEY,
            data_type TEXT,
            sample_value TEXT
        )
    ''')

    for path, (dtype, sample) in flat_schema.items():
        cursor.execute(
            'INSERT INTO schema_map (path, data_type, sample_value) VALUES (?, ?, ?)',
            (path, dtype, sample)
        )

    conn.commit()
    conn.close()

    print(f"\nSuccess! Schema mapped to: {db_path}")
    print("You can now open this DB in any SQLite viewer and search for things like '%driving%' or '%distance%'.")


def main():
    parser = argparse.ArgumentParser(
        description="Flatten a JSON file into a queryable SQLite schema map."
    )
    parser.add_argument(
        "target",
        help="Path to either a workspace folder or a JSON file"
    )
    parser.add_argument(
        "--out",
        help="Optional output SQLite DB path"
    )

    args = parser.parse_args()

    target = Path(args.target)
    out_path = Path(args.out) if args.out else None

    map_to_sqlite(target, out_path)


if __name__ == "__main__":
    main()