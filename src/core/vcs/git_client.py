"""Git subprocess wrapper — sniped from CodeMONKEY, no UI coupling.

GitCLI: wraps raw subprocess calls to git.
MindshardGitCLI: subclass that redirects GIT_DIR to .mindshard/ while
keeping the work tree at the project root.
"""

from __future__ import annotations
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


def _which(cmd: str) -> Optional[str]:
    """Return full path if command exists on PATH."""
    for p in os.environ.get("PATH", "").split(os.pathsep):
        f = Path(p) / cmd
        if os.name == "nt":
            for ext in (".exe", ".cmd", ".bat"):
                if (f.with_suffix(ext)).exists():
                    return str(f.with_suffix(ext))
        if f.exists() and os.access(f, os.X_OK):
            return str(f)
    return None


GIT_AVAILABLE = _which("git") is not None


@dataclass
class GitStatusEntry:
    path: str
    index: str
    workdir: str


@dataclass
class GitStatus:
    repo_path: str
    branch: Optional[str]
    ahead: int
    behind: int
    entries: List[GitStatusEntry]


class GitCLI:
    """Thin subprocess wrapper around the git CLI."""

    def __init__(self, repo_path: Path):
        self.root = self._resolve_repo_root(repo_path)

    def _run(self, args: List[str], *, cwd: Optional[Path] = None) -> Tuple[str, str]:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd or self.root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
        return proc.stdout, proc.stderr

    @staticmethod
    def _resolve_repo_root(path: Path) -> Path:
        path = path.resolve()
        if (path / ".git").exists():
            return path
        p = path
        while True:
            if (p / ".git").exists():
                return p
            if p.parent == p:
                break
            p = p.parent
        return path

    def init(self) -> None:
        self._run(["init"])

    def status(self) -> GitStatus:
        try:
            out, _ = self._run(["rev-parse", "--abbrev-ref", "HEAD"])
            branch = out.strip()
        except Exception:
            branch = None
        ahead = behind = 0
        try:
            out, _ = self._run(["rev-list", "--left-right", "--count", "@{upstream}...HEAD"])
            left, right = out.strip().split()
            behind, ahead = int(left), int(right)
        except Exception:
            pass
        out, _ = self._run(["status", "--porcelain=v1"])
        entries: List[GitStatusEntry] = []
        for line in out.splitlines():
            if not line.strip():
                continue
            xy = line[:2]
            path = line[3:]
            index, work = xy[0], xy[1]
            def norm(c: str) -> str:
                return c if c in "AMD R?" else "-"
            entries.append(GitStatusEntry(path=path, index=norm(index), workdir=norm(work)))
        return GitStatus(str(self.root), branch, ahead, behind, entries)

    def stage(self, paths: List[str]) -> None:
        if paths:
            self._run(["add", "--"] + paths)

    def unstage(self, paths: List[str]) -> None:
        if paths:
            self._run(["reset", "HEAD", "--"] + paths)

    def diff(self, file: Optional[str] = None) -> str:
        args = ["diff"]
        if file:
            args += ["--", file]
        out, _ = self._run(args)
        return out

    def commit(self, message: str, author_name: str, author_email: str) -> str:
        env = os.environ.copy()
        env["GIT_AUTHOR_NAME"] = author_name
        env["GIT_AUTHOR_EMAIL"] = author_email
        env["GIT_COMMITTER_NAME"] = author_name
        env["GIT_COMMITTER_EMAIL"] = author_email
        proc = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=str(self.root),
            capture_output=True, text=True, env=env,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
        out, _ = self._run(["rev-parse", "HEAD"])
        return out.strip()

    def log(self, limit: int = 100) -> List[Tuple[str, str, str, int]]:
        fmt = "%H%x1f%s%x1f%an%x1f%at"
        out, _ = self._run(["log", f"-n{limit}", f"--pretty=format:{fmt}"])
        items = []
        for line in out.splitlines():
            if not line.strip():
                continue
            parts = line.split("\x1f")
            if len(parts) == 4:
                commit, summary, author, at = parts
                items.append((commit, summary, author, int(at)))
        return items

    def branches(self) -> List[Tuple[str, bool]]:
        out, _ = self._run(["branch"])
        res = []
        for line in out.splitlines():
            is_head = line.strip().startswith("*")
            name = line.replace("*", "", 1).strip()
            res.append((name, is_head))
        return res

    def checkout(self, name: str, create: bool = False) -> None:
        if create:
            self._run(["checkout", "-B", name])
        else:
            self._run(["checkout", name])

    def reset_to(self, target: str, hard: bool = False) -> None:
        mode = "--hard" if hard else "--soft"
        self._run(["reset", mode, target])

    def tags(self) -> List[Tuple[str, str]]:
        try:
            out, _ = self._run(["show-ref", "--tags"])
        except RuntimeError:
            return []
        res = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) == 2:
                oid, ref = parts
                name = ref.split("/")[-1]
                res.append((name, oid))
        return res

    def create_tag(self, name: str, message: str) -> None:
        self._run(["tag", "-a", name, "-m", message])


class MindshardGitCLI(GitCLI):
    """GitCLI variant using .mindshard/ as git dir, project root as work tree.

    Overrides _run and commit to inject GIT_DIR and GIT_WORK_TREE env vars,
    which keeps all git metadata inside .mindshard/ without touching .git.
    """

    def __init__(self, project_root: Path):
        # Don't call super().__init__ — we set root directly
        self.project_root = Path(project_root).resolve()
        self.root = self.project_root
        self.git_dir = self.project_root / ".mindshard" / "vcs"

    def _git_env(self) -> dict:
        env = os.environ.copy()
        env["GIT_DIR"] = str(self.git_dir)
        env["GIT_WORK_TREE"] = str(self.project_root)
        return env

    def _run(self, args: List[str], *, cwd: Optional[Path] = None) -> Tuple[str, str]:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd or self.project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=self._git_env(),
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
        return proc.stdout, proc.stderr

    def commit(self, message: str, author_name: str, author_email: str) -> str:
        env = self._git_env()
        env["GIT_AUTHOR_NAME"] = author_name
        env["GIT_AUTHOR_EMAIL"] = author_email
        env["GIT_COMMITTER_NAME"] = author_name
        env["GIT_COMMITTER_EMAIL"] = author_email
        proc = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=str(self.project_root),
            capture_output=True, text=True, env=env,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
        out, _ = self._run(["rev-parse", "HEAD"])
        return out.strip()
