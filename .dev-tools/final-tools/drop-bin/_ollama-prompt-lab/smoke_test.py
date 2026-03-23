"""
FILE: smoke_test.py
ROLE: Portable self-test for _ollama-prompt-lab.
WHAT IT DOES: Verifies that core prompt-lab files compile and that the example quick-eval job can run locally.
HOW TO USE:
  - python _ollama-prompt-lab/smoke_test.py
"""

from __future__ import annotations

import subprocess
import sys
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _run(args: list[str]) -> None:
    completed = subprocess.run(args, cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


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
        proc.stdin.write(_mcp_message({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {},
        }))
        proc.stdin.flush()
        init_response = _mcp_read(proc.stdout)
        if init_response.get("result", {}).get("serverInfo", {}).get("name") != "ollama-prompt-lab-mcp":
            raise RuntimeError(f"Unexpected MCP initialize response: {init_response}")

        proc.stdin.write(_mcp_message({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        }))
        proc.stdin.flush()
        list_response = _mcp_read(proc.stdout)
        tool_names = [tool["name"] for tool in list_response.get("result", {}).get("tools", [])]
        if "ollama_prompt_lab" not in tool_names:
            raise RuntimeError(f"Expected ollama_prompt_lab in MCP tool list, got: {tool_names}")

        proc.stdin.write(_mcp_message({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "ollama_prompt_lab",
                "arguments": {
                    "models": ["qwen3.5:2b"],
                    "prompt_variants": [{"id": "dry-run", "template": "Reply with PASS."}],
                    "cases": [{"id": "case-1", "checks": {"exact_match": "PASS"}}],
                    "dry_run": True,
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
    _run([sys.executable, "-m", "py_compile", str(ROOT / "common.py"), str(ROOT / "mcp_server.py"), str(ROOT / "tools" / "ollama_prompt_lab.py")])
    _run([sys.executable, str(ROOT / "tools" / "ollama_prompt_lab.py"), "metadata"])
    _run([
        sys.executable,
        str(ROOT / "tools" / "ollama_prompt_lab.py"),
        "run",
        "--input-file",
        str(ROOT / "jobs" / "examples" / "quick_eval.json"),
    ])
    _mcp_smoke()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
