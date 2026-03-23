"""
FILE: smoke_test.py
ROLE: Portable self-test for _manifold-mcp.
WHAT IT DOES: Verifies CLI and MCP paths for reversible ingest, query, and extract workflows.
HOW TO USE:
  - python _manifold-mcp/smoke_test.py
"""

from __future__ import annotations

import json
import subprocess
import sys
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


def _mcp_smoke() -> None:
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
        if init_response.get("result", {}).get("serverInfo", {}).get("name") != "manifold-mcp":
            raise RuntimeError(f"Unexpected MCP initialize response: {init_response}")

        proc.stdin.write(_mcp_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}))
        proc.stdin.flush()
        list_response = _mcp_read(proc.stdout)
        tool_names = [tool["name"] for tool in list_response.get("result", {}).get("tools", [])]
        for expected in ("manifold_ingest", "manifold_query", "manifold_extract"):
            if expected not in tool_names:
                raise RuntimeError(f"Expected {expected} in MCP tool list, got: {tool_names}")

        temp_store = ROOT / "artifacts" / "smoke-mcp-store"
        proc.stdin.write(_mcp_message({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "manifold_ingest",
                "arguments": {
                    "corpus_id": "mcp-smoke",
                    "store_dir": str(temp_store),
                    "texts": [{"title": "Smoke", "text": "Evidence bags preserve exact source text. Hyperedges stay traceable."}]
                },
            },
        }))
        proc.stdin.flush()
        call_response = _mcp_read(proc.stdout)
        structured = call_response.get("result", {}).get("structuredContent", {})
        if structured.get("status") != "ok":
            raise RuntimeError(f"Unexpected MCP tool call response: {call_response}")
    finally:
        proc.kill()
        proc.wait(timeout=5)


def main() -> int:
    _run([sys.executable, "-m", "py_compile", str(ROOT / "common.py"), str(ROOT / "mcp_server.py"), str(ROOT / "lib" / "manifold_store.py"), str(ROOT / "tools" / "manifold_ingest.py"), str(ROOT / "tools" / "manifold_query.py"), str(ROOT / "tools" / "manifold_extract.py")])
    _run([sys.executable, "-m", "py_compile", str(ROOT / "sdk" / "evidence_package.py")])
    ingest = _run_json([
        sys.executable,
        str(ROOT / "tools" / "manifold_ingest.py"),
        "run",
        "--input-file",
        str(ROOT / "jobs" / "examples" / "ingest_inline.json"),
    ])
    query = _run_json([
        sys.executable,
        str(ROOT / "tools" / "manifold_query.py"),
        "run",
        "--input-json",
        json.dumps({
            "store_dir": ingest["result"]["store_dir"],
            "corpus_id": ingest["result"]["corpus_id"],
            "query": "evidence bag exact source text",
            "top_n": 8,
        }),
    ])
    extract = _run_json([
        sys.executable,
        str(ROOT / "tools" / "manifold_extract.py"),
        "run",
        "--input-json",
        json.dumps({
            "store_dir": ingest["result"]["store_dir"],
            "bag_file": query["result"]["bag_file"],
            "mode": "verbatim",
        }),
    ])
    if "evidence bags preserve exact source text" not in extract["result"]["text"].lower():
        raise RuntimeError(f"Unexpected extraction text: {extract['result']['text']}")

    sdk_probe = _run_json([
        sys.executable,
        "-c",
        (
            "import json, sys, tempfile; "
            "from pathlib import Path; "
            f"sys.path.insert(0, r'{str(ROOT)}'); "
            "from sdk.evidence_package import EvidencePackage; "
            "root = Path(tempfile.mkdtemp(prefix='manifold_sdk_')); "
            "pkg = EvidencePackage(root / 'evidence.db'); "
            "pkg.set_goal('preserve exact evidence text'); "
            "pkg.ingest_turn('Evidence bags preserve exact source text.', source_role='assistant', turn_id='sdk'); "
            "window = pkg.window('exact source text', token_budget=128); "
            "pkg.close(); "
            "print(json.dumps(window))"
        ),
    ])
    if "evidence bags preserve exact source text" not in sdk_probe["text"].lower():
        raise RuntimeError(f"Unexpected SDK window text: {sdk_probe['text']}")

    _mcp_smoke()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
