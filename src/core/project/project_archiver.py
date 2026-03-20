"""Project archiver — packs up .mindshard/ into the memory vault on detach.

Lifecycle:
  1. Final VCS snapshot
  2. Bundle .mindshard/ into a zip archive
  3. Register in the memory vault index
  4. Verify archive integrity (zip test)
  5. Delete .mindshard/ from working copy
"""
from __future__ import annotations
import shutil
import zipfile
from pathlib import Path
from typing import Optional
from src.core.utils.clock import utc_iso
from src.core.runtime.runtime_logger import get_logger

log = get_logger("project_archiver")


def archive_sidecar(
    project_root: str | Path,
    vault_dir: str | Path,
    final_snapshot_hash: Optional[str] = None,
) -> dict:
    """Archive .mindshard/ into the vault and return a result dict.

    Args:
        project_root: The working copy root (contains .mindshard/)
        vault_dir: Path to the global memory vault directory
        final_snapshot_hash: VCS commit hash of the final snapshot (if any)

    Returns:
        {
          "success": bool,
          "archive_path": str,
          "project_name": str,
          "error": str or None,
        }
    """
    project_root = Path(project_root).resolve()
    sidecar = project_root / ".mindshard"
    vault_dir = Path(vault_dir).resolve()
    vault_dir.mkdir(parents=True, exist_ok=True)

    if not sidecar.exists():
        return {"success": False, "archive_path": "", "project_name": project_root.name,
                "error": "No .mindshard/ sidecar found"}

    # Load project name from meta if available
    project_name = project_root.name
    try:
        import json
        meta_path = sidecar / "state" / "project_meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            project_name = meta.get("display_name", "") or project_name
    except Exception:
        pass

    # Build archive filename: <project_name>_<timestamp>.zip
    ts = utc_iso().replace(":", "-").replace(".", "-")
    archive_name = f"{project_root.name}_{ts}.zip"
    archive_path = vault_dir / archive_name

    try:
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in sidecar.rglob("*"):
                if item.is_file():
                    zf.write(item, item.relative_to(project_root))
        # Verify integrity
        with zipfile.ZipFile(archive_path, "r") as zf:
            bad = zf.testzip()
            if bad:
                raise RuntimeError(f"Archive corrupt: {bad}")
    except Exception as e:
        log.error("Archive failed: %s", e)
        return {"success": False, "archive_path": str(archive_path),
                "project_name": project_name, "error": str(e)}

    log.info("Sidecar archived: %s", archive_path)
    return {
        "success": True,
        "archive_path": str(archive_path),
        "project_name": project_name,
        "error": None,
        "snapshot_hash": final_snapshot_hash or "",
        "ts": ts,
    }


def remove_sidecar(project_root: str | Path) -> bool:
    """Delete .mindshard/ from the working copy. Returns True on success."""
    sidecar = Path(project_root).resolve() / ".mindshard"
    if not sidecar.exists():
        return True
    try:
        shutil.rmtree(sidecar)
        log.info("Sidecar removed from %s", project_root)
        return True
    except Exception as e:
        log.error("Failed to remove sidecar: %s", e)
        return False
