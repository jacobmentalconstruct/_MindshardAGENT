"""
FILE: smoke_test.py
ROLE: Portable self-test for the .final-tools project.
WHAT IT DOES: Verifies that the core tool scripts compile, expose metadata, and can run basic example jobs.
HOW TO USE:
  - python .final-tools/smoke_test.py
NOTES:
  - Uses only the standard library.
  - Intended to be run after copying or unzipping this folder into a new project.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TOOLS = [
    ROOT / "tools" / "workspace_audit.py",
    ROOT / "tools" / "data_shape_inspector.py",
    ROOT / "tools" / "structured_patcher.py",
    ROOT / "tools" / "python_risk_scan.py",
    ROOT / "tools" / "tk_ui_map.py",
    ROOT / "tools" / "tk_ui_thread_audit.py",
    ROOT / "tools" / "tk_ui_event_map.py",
    ROOT / "tools" / "tk_ui_layout_audit.py",
    ROOT / "tools" / "tk_ui_test_scaffold.py",
]


def _run(command: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(command, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def _expect_json_output(command: list[str]) -> dict:
    code, stdout, stderr = _run(command)
    if code != 0:
        raise RuntimeError(f"Command failed: {' '.join(command)}\nSTDERR:\n{stderr}")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Command did not emit JSON: {' '.join(command)}") from exc


def main() -> int:
    failures: list[str] = []

    for tool in TOOLS:
        payload = _expect_json_output([sys.executable, str(tool), "metadata"])
        if "tool_name" not in payload:
            failures.append(f"metadata missing tool_name for {tool.name}")

    workspace_result = _expect_json_output(
        [
            sys.executable,
            str(ROOT / "tools" / "workspace_audit.py"),
            "run",
            "--input-file",
            str(ROOT / "jobs" / "examples" / "workspace_audit.json"),
        ]
    )
    if workspace_result.get("status") != "ok":
        failures.append("workspace_audit did not return status=ok")

    risk_result = _expect_json_output(
        [
            sys.executable,
            str(ROOT / "tools" / "python_risk_scan.py"),
            "run",
            "--input-file",
            str(ROOT / "jobs" / "examples" / "python_risk_scan.json"),
        ]
    )
    if risk_result.get("status") != "ok":
        failures.append("python_risk_scan did not return status=ok")

    tk_map_result = _expect_json_output(
        [
            sys.executable,
            str(ROOT / "tools" / "tk_ui_map.py"),
            "run",
            "--input-file",
            str(ROOT / "jobs" / "examples" / "tk_ui_map.json"),
        ]
    )
    if tk_map_result.get("status") != "ok":
        failures.append("tk_ui_map did not return status=ok")

    for tool_name, job_name in [
        ("tk_ui_thread_audit.py", "tk_ui_thread_audit.json"),
        ("tk_ui_event_map.py", "tk_ui_event_map.json"),
        ("tk_ui_layout_audit.py", "tk_ui_layout_audit.json"),
        ("tk_ui_test_scaffold.py", "tk_ui_test_scaffold.json"),
    ]:
        payload = _expect_json_output(
            [
                sys.executable,
                str(ROOT / "tools" / tool_name),
                "run",
                "--input-file",
                str(ROOT / "jobs" / "examples" / job_name),
            ]
        )
        if payload.get("status") != "ok":
            failures.append(f"{tool_name} did not return status=ok")

    if failures:
        print(json.dumps({"status": "error", "failures": failures}, indent=2))
        return 1

    print(json.dumps({"status": "ok", "checked_tools": [tool.name for tool in TOOLS]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
