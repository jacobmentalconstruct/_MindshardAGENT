"""Workspace layout helpers for sandbox-owned sidecar structure."""

from __future__ import annotations

from pathlib import Path


def ensure_sidecar_dirs(sandbox_root: str | Path) -> None:
    """Create the standard `.mindshard/` sidecar directories if missing."""
    root = Path(sandbox_root)
    sidecar = root / ".mindshard"
    for name in ("vcs", "sessions", "logs", "tools", "parts", "ref", "outputs", "state", "runs"):
        (sidecar / name).mkdir(parents=True, exist_ok=True)
