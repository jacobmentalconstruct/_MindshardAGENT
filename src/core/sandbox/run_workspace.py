"""Disposable run-workspace helpers for sandbox-local execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
import json
from pathlib import Path
import shutil
from uuid import uuid4

from src.core.runtime.runtime_logger import get_logger

log = get_logger("run_workspace")

_IGNORE_NAMES = {
    ".mindshard",
    ".git",
    "__pycache__",
    "node_modules",
    "venv",
    ".venv",
}


@dataclass(frozen=True)
class RunWorkspace:
    """Metadata for a disposable execution snapshot."""

    run_id: str
    run_root: Path
    workspace_root: Path
    script_path: Path
    cwd: Path
    manifest_path: Path


def create_run_workspace(
    sandbox_root: Path,
    script_path: Path,
    cwd: Path,
    args: list[str],
) -> RunWorkspace:
    """Create a disposable copy of the sandbox workspace for execution."""

    sandbox_root = sandbox_root.resolve()
    script_path = script_path.resolve()
    cwd = cwd.resolve()

    run_id = _new_run_id()
    run_root = sandbox_root / ".mindshard" / "runs" / run_id
    workspace_root = run_root / "workspace"
    manifest_path = run_root / "manifest.json"

    run_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        sandbox_root,
        workspace_root,
        ignore=_ignore_workspace_entries,
        dirs_exist_ok=False,
    )

    script_rel = script_path.relative_to(sandbox_root)
    cwd_rel = cwd.relative_to(sandbox_root)
    staged_script = (workspace_root / script_rel).resolve()
    staged_cwd = (workspace_root / cwd_rel).resolve()

    manifest = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "source_script": script_rel.as_posix(),
        "source_cwd": cwd_rel.as_posix(),
        "args": list(args),
        "workspace_root": str(workspace_root),
        "mode": "run_copy",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log.info("Run workspace created: %s", run_root)

    return RunWorkspace(
        run_id=run_id,
        run_root=run_root,
        workspace_root=workspace_root,
        script_path=staged_script,
        cwd=staged_cwd,
        manifest_path=manifest_path,
    )


def record_run_result(run_workspace: RunWorkspace, result: dict) -> None:
    """Persist run output metadata for later inspection."""

    manifest = {}
    if run_workspace.manifest_path.exists():
        try:
            manifest = json.loads(run_workspace.manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    stdout_path = run_workspace.run_root / "stdout.txt"
    stderr_path = run_workspace.run_root / "stderr.txt"
    result_path = run_workspace.run_root / "result.json"

    stdout_path.write_text(str(result.get("stdout", "")), encoding="utf-8")
    stderr_path.write_text(str(result.get("stderr", "")), encoding="utf-8")

    manifest["completed_at"] = datetime.now(UTC).isoformat()
    manifest["exit_code"] = result.get("exit_code", -1)
    manifest["stdout_path"] = str(stdout_path)
    manifest["stderr_path"] = str(stderr_path)
    manifest["result_path"] = str(result_path)
    run_workspace.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")


def _new_run_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"run_{stamp}_{uuid4().hex[:6]}"


def _ignore_workspace_entries(_dir: str, names: list[str]) -> set[str]:
    return {name for name in names if name in _IGNORE_NAMES}
