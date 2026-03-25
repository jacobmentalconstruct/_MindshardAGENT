"""MindshardVCS — local versioning layer for sandbox workspaces.

Creates and manages a git repo at .mindshard/vcs/ inside the sandbox/project root.
All git metadata lives in .mindshard/vcs/ — the project root is the work tree.
The whole .mindshard/ sidecar is excluded from tracking via the exclude file.
No GitHub, no remotes. Just local snapshots with auto-generated commit messages.

Lifecycle:
  1. attach(sandbox_root) — init .mindshard/vcs/ if new, open if existing
  2. snapshot(message)    — stage all changes and commit
  3. onboarding_context() — recent commits formatted for agent prompt injection
  4. revert_to(hash)      — hard reset to a prior commit
"""

from __future__ import annotations
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.vcs.git_client import MindshardGitCLI, GIT_AVAILABLE
from src.core.runtime.runtime_logger import get_logger

log = get_logger("mindshard_vcs")

AUTHOR_NAME = "MindshardAGENT"
AUTHOR_EMAIL = "agent@mindshard.local"

# Files/dirs to exclude from tracking (written to .mindshard/vcs/info/exclude)
# NOTE: VCS lives at .mindshard/vcs/ but the entire .mindshard/ sidecar is excluded
# so sessions, logs, tools and all other sidecar state is never tracked.
_EXCLUDES = """\
# MindshardAGENT workspace excludes
.mindshard
__pycache__
*.pyc
*.pyo
*.db
*.db-journal
*.db-shm
*.db-wal
venv/
.venv/
node_modules/
*.egg-info/
.DS_Store
Thumbs.db
"""


class MindshardVCS:
    """Local git versioning for a sandbox workspace.

    Uses .mindshard/vcs/ as the git directory, workspace root as the work tree.
    The whole .mindshard/ sidecar is excluded from tracking.
    Safe to use even if the workspace already has its own .git — no conflicts.
    """

    def __init__(self):
        self._cli: Optional[MindshardGitCLI] = None
        self.project_root: Optional[Path] = None
        self._init_thread: Optional[threading.Thread] = None

    @property
    def is_attached(self) -> bool:
        return self._cli is not None

    @property
    def available(self) -> bool:
        return GIT_AVAILABLE

    def attach(self, project_root: str | Path) -> bool:
        """Attach VCS to a workspace folder.

        Creates .mindshard/vcs/ and makes initial snapshot if new.
        Returns True if this is a new repository, False if existing.
        """
        if not GIT_AVAILABLE:
            log.warning("git not found on PATH — VCS disabled")
            return False

        root = Path(project_root).resolve()
        git_dir = root / ".mindshard" / "vcs"
        is_new = not (git_dir / "HEAD").exists()

        self.project_root = root
        self._cli = MindshardGitCLI(root)

        if is_new:
            # Run git init + initial snapshot in bg thread — can be slow on first attach.
            # The thread is tracked so that snapshot() can wait for init to finish
            # before attempting any git operations (prevents race on fast detach).
            def _init_bg():
                try:
                    git_dir.mkdir(parents=True, exist_ok=True)
                    self._cli.init()
                    self._write_excludes(git_dir)
                    # Call _cli directly to avoid the wait-for-init guard in snapshot()
                    self._cli.stage(["."])
                    self._cli.commit(
                        "Initial snapshot — MindshardAGENT attached",
                        AUTHOR_NAME, AUTHOR_EMAIL,
                    )
                    log.info("VCS initialized at %s/.mindshard/vcs/", root)
                except Exception as e:
                    log.error("VCS init failed: %s", e)
                    self._cli = None
            thread = threading.Thread(target=_init_bg, daemon=True, name="vcs-init")
            self._init_thread = thread
            thread.start()
        else:
            log.info("VCS attached to existing repo at %s/.mindshard/vcs/", root)

        return is_new

    def _wait_for_init(self, timeout: float = 30.0) -> None:
        """Block until any background git-init thread has finished."""
        if self._init_thread is not None and self._init_thread.is_alive():
            log.debug("Waiting for VCS init thread to finish (%.1fs timeout)...", timeout)
            self._init_thread.join(timeout=timeout)

    def snapshot(self, message: str = "") -> Optional[str]:
        """Stage all changes and commit. Returns commit hash or None if nothing to commit."""
        self._wait_for_init()
        if not self._cli:
            return None
        if not message:
            message = f"MindshardAGENT {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        try:
            self._cli.stage(["."])
            return self._cli.commit(message, AUTHOR_NAME, AUTHOR_EMAIL)
        except RuntimeError as e:
            err = str(e).lower()
            if "nothing to commit" in err or "nothing added" in err or "empty commit" in err:
                log.debug("VCS snapshot: nothing to commit")
                return None
            log.error("VCS snapshot failed: %s", e)
            raise

    def log(self, limit: int = 10) -> list:
        """Return recent commits as list of (hash, summary, author, timestamp)."""
        if not self._cli:
            return []
        try:
            return self._cli.log(limit)
        except RuntimeError as e:
            log.debug("VCS log failed (possibly no commits yet): %s", e)
            return []

    def onboarding_context(self, limit: int = 5) -> str:
        """Format recent commits for agent prompt injection."""
        items = self.log(limit)
        if not items:
            return ""
        lines = []
        for commit, summary, _author, ts in items:
            dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            lines.append(f"  [{commit[:8]}] {dt} — {summary}")
        return "\n".join(lines)

    def status_entries(self) -> list:
        """Return current GitStatusEntry list for the UI panel."""
        if not self._cli:
            return []
        try:
            return self._cli.status().entries
        except RuntimeError:
            return []

    def diff(self, file: str | None = None) -> str:
        """Return diff output for a file or all changes."""
        if not self._cli:
            return ""
        try:
            return self._cli.diff(file)
        except RuntimeError:
            return ""

    def revert_to(self, commit_hash: str) -> None:
        """Hard reset work tree to a prior commit."""
        if self._cli:
            self._cli.reset_to(commit_hash, hard=True)

    def _write_excludes(self, git_dir: Path) -> None:
        """Write .mindshard/vcs/info/exclude to prevent tracking internal dirs."""
        info_dir = git_dir / "info"
        info_dir.mkdir(exist_ok=True)
        (info_dir / "exclude").write_text(_EXCLUDES, encoding="utf-8")
