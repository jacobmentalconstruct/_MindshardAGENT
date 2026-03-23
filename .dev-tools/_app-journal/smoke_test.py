"""
FILE: smoke_test.py
ROLE: Portable self-test for _app-journal.
WHAT IT DOES: Verifies CLI, SQLite, export, and MCP paths for the journal package.
HOW TO USE:
  - python _app-journal/smoke_test.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _run(args: list[str]) -> None:
    completed = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stdout or completed.stderr)


def _run_json(args: list[str]) -> dict:
    completed = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stdout or completed.stderr)
    return json.loads(completed.stdout)


def _mcp_message(message: dict) -> bytes:
    body = json.dumps(message).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8") + body


def _mcp_read(stdout) -> dict:
    headers = {}
    while True:
        line = stdout.readline()
        if not line:
            raise RuntimeError("MCP server closed before responding.")
        if line in {b"\r\n", b"\n"}:
            break
        key, value = line.decode("utf-8").split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length = int(headers["content-length"])
    body = stdout.read(length)
    return json.loads(body.decode("utf-8"))


def _mcp_smoke(project_root: Path) -> None:
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "mcp_server.py")],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert proc.stdin is not None
        assert proc.stdout is not None
        proc.stdin.write(_mcp_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}))
        proc.stdin.flush()
        init_response = _mcp_read(proc.stdout)
        if init_response.get("result", {}).get("serverInfo", {}).get("name") != "app-journal":
            raise RuntimeError(f"Unexpected MCP initialize response: {init_response}")

        proc.stdin.write(_mcp_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}))
        proc.stdin.flush()
        list_response = _mcp_read(proc.stdout)
        tool_names = [tool["name"] for tool in list_response.get("result", {}).get("tools", [])]
        for expected in ("journal_init", "journal_manifest", "journal_write", "journal_query", "journal_export"):
            if expected not in tool_names:
                raise RuntimeError(f"Expected {expected} in MCP tool list, got: {tool_names}")

        proc.stdin.write(
            _mcp_message(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "journal_query",
                        "arguments": {"project_root": str(project_root), "query": "decision"},
                    },
                }
            )
        )
        proc.stdin.flush()
        call_response = _mcp_read(proc.stdout)
        structured = call_response.get("result", {}).get("structuredContent", {})
        if structured.get("status") != "ok":
            raise RuntimeError(f"Unexpected MCP tool call response: {call_response}")
    finally:
        proc.kill()
        proc.wait(timeout=5)


def main() -> int:
    _run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(ROOT / "common.py"),
            str(ROOT / "mcp_server.py"),
            str(ROOT / "launch_ui.py"),
            str(ROOT / "lib" / "journal_store.py"),
            str(ROOT / "tools" / "journal_init.py"),
            str(ROOT / "tools" / "journal_manifest.py"),
            str(ROOT / "tools" / "journal_write.py"),
            str(ROOT / "tools" / "journal_query.py"),
            str(ROOT / "tools" / "journal_export.py"),
            str(ROOT / "ui" / "app_journal_ui.py"),
        ]
    )

    project_root = Path(tempfile.mkdtemp(prefix="app_journal_project_")) / "sample-project"
    project_root.mkdir(parents=True, exist_ok=True)

    init_result = _run_json(
        [
            sys.executable,
            str(ROOT / "tools" / "journal_init.py"),
            "run",
            "--input-json",
            json.dumps({"project_root": str(project_root)}),
        ]
    )
    db_path = init_result["result"]["paths"]["db_path"]

    manifest_result = _run_json(
        [
            sys.executable,
            str(ROOT / "tools" / "journal_manifest.py"),
            "run",
            "--input-json",
            json.dumps({"project_root": str(project_root)}),
        ]
    )
    if manifest_result["result"]["package_manifest"].get("name") != "app-journal":
        raise RuntimeError(f"Unexpected package manifest: {manifest_result}")
    if manifest_result["result"]["db_manifest"].get("db_manifest_version") != "1.0":
        raise RuntimeError(f"Unexpected DB manifest: {manifest_result}")
    if manifest_result["result"]["db_summary"].get("schema_version") != "1.0.0":
        raise RuntimeError(f"Unexpected schema version: {manifest_result}")
    if manifest_result["result"]["db_summary"].get("sqlite_user_version") != 1:
        raise RuntimeError(f"Unexpected sqlite user_version: {manifest_result}")
    if not manifest_result["result"].get("migrations"):
        raise RuntimeError(f"Expected at least one migration row: {manifest_result}")

    create_result = _run_json(
        [
            sys.executable,
            str(ROOT / "tools" / "journal_write.py"),
            "run",
            "--input-json",
            json.dumps(
                {
                    "project_root": str(project_root),
                    "action": "create",
                    "title": "Initial decision",
                    "body": "We want one durable place for project notes.",
                    "kind": "decision",
                    "source": "agent",
                    "tags": ["notes", "journal"],
                }
            ),
        ]
    )
    entry_uid = create_result["result"]["entry"]["entry_uid"]

    _run_json(
        [
            sys.executable,
            str(ROOT / "tools" / "journal_write.py"),
            "run",
            "--input-json",
            json.dumps(
                {
                    "db_path": db_path,
                    "action": "append",
                    "entry_uid": entry_uid,
                    "append_text": "The journal should work for both Tkinter users and MCP agents.",
                }
            ),
        ]
    )

    query_result = _run_json(
        [
            sys.executable,
            str(ROOT / "tools" / "journal_query.py"),
            "run",
            "--input-json",
            json.dumps({"project_root": str(project_root), "query": "durable place", "limit": 10}),
        ]
    )
    if query_result["result"]["summary"]["entry_count"] < 1:
        raise RuntimeError(f"Expected at least one journal entry, got: {query_result}")

    export_result = _run_json(
        [
            sys.executable,
            str(ROOT / "tools" / "journal_export.py"),
            "run",
            "--input-json",
            json.dumps({"project_root": str(project_root), "format": "markdown"}),
        ]
    )
    export_path = Path(export_result["result"]["export_path"])
    if not export_path.exists():
        raise RuntimeError(f"Expected export file to exist: {export_path}")

    _mcp_smoke(project_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
