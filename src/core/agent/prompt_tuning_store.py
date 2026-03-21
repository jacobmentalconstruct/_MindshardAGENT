"""Prompt tuning history: local Git snapshots + SQLite experiment tracking."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
from typing import Any

from src.core.agent.benchmark_runner import BenchmarkSuiteResult
from src.core.agent.prompt_builder import PromptBuildResult
from src.core.agent.probe_scorer import ProbeFinding, ProbeScores, compute_probe_scores, extract_probe_findings
from src.core.runtime.runtime_logger import get_logger
from src.core.utils.clock import utc_iso

log = get_logger("prompt_tuning")


@dataclass(frozen=True)
class PromptVersionSnapshot:
    version_id: int
    git_commit: str
    created_at: str
    source_fingerprint: str = ""
    prompt_fingerprint: str = ""


class PromptTuningStore:
    """Stores prompt snapshots in a local Git repo and probe metadata in SQLite."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).resolve()
        self.version_root = self.workspace_root / ".prompt-versioning"
        self.db_path = self.version_root / "prompt_eval.db"
        self._global_prompt_dir = self.workspace_root / "_docs" / "agent_prompt"

    def snapshot_current_state(
        self,
        *,
        reason: str,
        sandbox_root: str | Path | None = None,
        changed_path: str | Path | None = None,
        prompt_build: PromptBuildResult | None = None,
        notes: str = "",
    ) -> PromptVersionSnapshot | None:
        try:
            self._ensure_ready()
            sandbox_path = Path(sandbox_root).resolve() if sandbox_root else None
            created_at = utc_iso()
            self._sync_snapshot_tree(
                sandbox_root=sandbox_path,
                changed_path=Path(changed_path).resolve() if changed_path else None,
                prompt_build=prompt_build,
                reason=reason,
                notes=notes,
                created_at=created_at,
            )
            self._run_git("add", "-A")
            head_before = self._head_commit()
            if self._is_dirty():
                message = self._commit_message(reason=reason, changed_path=changed_path, prompt_build=prompt_build)
                self._run_git("commit", "-m", message)
            git_commit = self._head_commit() or head_before
            if not git_commit:
                return None
            version_id = self._upsert_prompt_version(
                created_at=created_at,
                git_commit=git_commit,
                sandbox_root=str(sandbox_path) if sandbox_path else "",
                reason=reason,
                changed_path=str(changed_path or ""),
                prompt_build=prompt_build,
                notes=notes,
            )
            return PromptVersionSnapshot(
                version_id=version_id,
                git_commit=git_commit,
                created_at=created_at,
                source_fingerprint=prompt_build.source_fingerprint if prompt_build else "",
                prompt_fingerprint=prompt_build.prompt_fingerprint if prompt_build else "",
            )
        except Exception:
            log.exception("Failed to snapshot prompt state")
            return None

    def record_probe_run(
        self,
        *,
        snapshot: PromptVersionSnapshot | None,
        probe_name: str,
        probe_type: str,
        model_name: str,
        query_text: str,
        status: str,
        summary: str,
        duration_ms: float,
        metadata: dict[str, Any],
        response_text: str,
        events: list[Any],
        warnings: list[str] | None = None,
    ) -> tuple[int | None, ProbeScores]:
        try:
            self._ensure_ready()
            findings = extract_probe_findings(
                response_text=response_text,
                events=events,
                metadata=metadata,
            )
            scores = compute_probe_scores(metadata=metadata, findings=findings)
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO probe_runs (
                        created_at, prompt_version_id, git_commit, probe_name, probe_type,
                        model_name, query_text, status, summary, duration_ms,
                        first_token_latency_ms, rounds, tokens_in, tokens_out,
                        tokens_in_num, tokens_out_num, total_tokens,
                        source_fingerprint, prompt_fingerprint,
                        accuracy_score, efficiency_score, overall_score, score, metadata_json,
                        response_excerpt, warning_count, output_dir
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        utc_iso(),
                        snapshot.version_id if snapshot else None,
                        snapshot.git_commit if snapshot else "",
                        probe_name,
                        probe_type,
                        model_name,
                        query_text,
                        status,
                        summary,
                        duration_ms,
                        scores.first_token_latency_ms,
                        scores.rounds,
                        str(metadata.get("tokens_in", "")),
                        str(metadata.get("tokens_out", "")),
                        scores.tokens_in,
                        scores.tokens_out,
                        scores.total_tokens,
                        snapshot.source_fingerprint if snapshot else str(metadata.get("source_fingerprint", "")),
                        snapshot.prompt_fingerprint if snapshot else str(metadata.get("prompt_fingerprint", "")),
                        scores.accuracy_score,
                        scores.efficiency_score,
                        scores.overall_score,
                        scores.overall_score,
                        json.dumps(metadata, ensure_ascii=False, indent=2),
                        response_text[:2000],
                        len(warnings or []),
                        "",
                    ),
                )
                run_id = int(cur.lastrowid)
                for finding in findings:
                    conn.execute(
                        """
                        INSERT INTO probe_findings (probe_run_id, finding_key, finding_value, severity, details)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (run_id, finding.key, finding.value, finding.severity, finding.details),
                    )
            return run_id, scores
        except Exception:
            log.exception("Failed to record probe run")
            return None, ProbeScores(0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def record_benchmark_run(
        self,
        *,
        snapshot: PromptVersionSnapshot | None,
        suite_result: BenchmarkSuiteResult,
        model_name: str,
    ) -> int | None:
        try:
            self._ensure_ready()
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO benchmark_runs (
                        created_at, prompt_version_id, git_commit, suite_name, suite_label,
                        model_name, duration_ms, case_count, average_accuracy_score,
                        average_efficiency_score, average_overall_score, total_tokens,
                        total_rounds, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        utc_iso(),
                        snapshot.version_id if snapshot else None,
                        snapshot.git_commit if snapshot else "",
                        suite_result.suite_name,
                        suite_result.suite_label,
                        model_name,
                        suite_result.duration_ms,
                        int(suite_result.metadata.get("case_count", 0)),
                        float(suite_result.metadata.get("average_accuracy_score", 0.0)),
                        float(suite_result.metadata.get("average_efficiency_score", 0.0)),
                        float(suite_result.metadata.get("average_overall_score", 0.0)),
                        int(suite_result.metadata.get("total_tokens", 0)),
                        int(suite_result.metadata.get("total_rounds", 0)),
                        json.dumps(suite_result.metadata, ensure_ascii=False, indent=2),
                    ),
                )
                benchmark_run_id = int(cur.lastrowid)
                for case in suite_result.cases:
                    probe_run_id = int(case.result.metadata.get("probe_run_id") or 0)
                    conn.execute(
                        """
                        INSERT INTO benchmark_run_items (
                            benchmark_run_id, probe_run_id, case_id, case_label, probe_type,
                            status, overall_score, total_tokens, rounds
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            benchmark_run_id,
                            probe_run_id,
                            case.case_id,
                            case.label,
                            case.probe_type,
                            case.result.status,
                            float(case.result.metadata.get("overall_score", 0.0)),
                            int(case.result.metadata.get("total_tokens", 0)),
                            int(case.result.metadata.get("rounds", 0)),
                        ),
                    )
            return benchmark_run_id
        except Exception:
            log.exception("Failed to record benchmark run")
            return None

    def attach_probe_export(self, probe_run_id: int, output_dir: str | Path) -> None:
        try:
            self._ensure_ready()
            with self._connect() as conn:
                conn.execute(
                    "UPDATE probe_runs SET output_dir = ? WHERE id = ?",
                    (str(Path(output_dir)), probe_run_id),
                )
        except Exception:
            log.exception("Failed to attach probe export path")

    def latest_versions(self, limit: int = 12) -> list[dict[str, Any]]:
        try:
            self._ensure_ready()
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT id, created_at, git_commit, reason, changed_path, source_fingerprint, prompt_fingerprint
                    FROM prompt_versions
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [dict(row) for row in rows]
        except Exception:
            log.exception("Failed to read latest prompt versions")
            return []

    def latest_benchmark_runs(self, limit: int = 12) -> list[dict[str, Any]]:
        try:
            self._ensure_ready()
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT id, created_at, suite_name, suite_label, model_name, case_count,
                           average_accuracy_score, average_efficiency_score, average_overall_score,
                           total_tokens, total_rounds
                    FROM benchmark_runs
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [dict(row) for row in rows]
        except Exception:
            log.exception("Failed to read latest benchmark runs")
            return []

    def get_prompt_version(self, version_id: int) -> dict[str, Any] | None:
        try:
            self._ensure_ready()
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT id, created_at, workspace_root, sandbox_root, git_commit, reason,
                           changed_path, source_fingerprint, prompt_fingerprint, notes
                    FROM prompt_versions
                    WHERE id = ?
                    """,
                    (int(version_id),),
                ).fetchone()
            return dict(row) if row else None
        except Exception:
            log.exception("Failed to get prompt version %s", version_id)
            return None

    def get_benchmark_run(self, benchmark_run_id: int) -> dict[str, Any] | None:
        try:
            self._ensure_ready()
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT id, created_at, prompt_version_id, git_commit, suite_name, suite_label,
                           model_name, duration_ms, case_count, average_accuracy_score,
                           average_efficiency_score, average_overall_score, total_tokens,
                           total_rounds, metadata_json
                    FROM benchmark_runs
                    WHERE id = ?
                    """,
                    (int(benchmark_run_id),),
                ).fetchone()
                if not row:
                    return None
                items = conn.execute(
                    """
                    SELECT probe_run_id, case_id, case_label, probe_type, status,
                           overall_score, total_tokens, rounds
                    FROM benchmark_run_items
                    WHERE benchmark_run_id = ?
                    ORDER BY id ASC
                    """,
                    (int(benchmark_run_id),),
                ).fetchall()
            result = dict(row)
            result["items"] = [dict(item) for item in items]
            return result
        except Exception:
            log.exception("Failed to get benchmark run %s", benchmark_run_id)
            return None

    def compare_benchmark_runs(self, left_run_id: int, right_run_id: int) -> dict[str, Any]:
        left = self.get_benchmark_run(left_run_id)
        right = self.get_benchmark_run(right_run_id)
        if not left or not right:
            raise ValueError("One or both benchmark runs could not be loaded")

        def _metric(name: str, record: dict[str, Any]) -> float:
            return float(record.get(name, 0.0) or 0.0)

        comparison = {
            "left": left,
            "right": right,
            "delta_average_overall_score": round(_metric("average_overall_score", right) - _metric("average_overall_score", left), 3),
            "delta_average_accuracy_score": round(_metric("average_accuracy_score", right) - _metric("average_accuracy_score", left), 3),
            "delta_average_efficiency_score": round(_metric("average_efficiency_score", right) - _metric("average_efficiency_score", left), 3),
            "delta_total_tokens": int(right.get("total_tokens", 0) or 0) - int(left.get("total_tokens", 0) or 0),
            "delta_total_rounds": int(right.get("total_rounds", 0) or 0) - int(left.get("total_rounds", 0) or 0),
        }
        left_items = {item["case_id"]: item for item in left.get("items", [])}
        right_items = {item["case_id"]: item for item in right.get("items", [])}
        case_deltas: list[dict[str, Any]] = []
        for case_id in sorted(set(left_items) | set(right_items)):
            left_item = left_items.get(case_id, {})
            right_item = right_items.get(case_id, {})
            case_deltas.append(
                {
                    "case_id": case_id,
                    "case_label": right_item.get("case_label") or left_item.get("case_label") or case_id,
                    "left_status": left_item.get("status", ""),
                    "right_status": right_item.get("status", ""),
                    "delta_score": round(float(right_item.get("overall_score", 0.0) or 0.0) - float(left_item.get("overall_score", 0.0) or 0.0), 3),
                    "delta_tokens": int(right_item.get("total_tokens", 0) or 0) - int(left_item.get("total_tokens", 0) or 0),
                    "delta_rounds": int(right_item.get("rounds", 0) or 0) - int(left_item.get("rounds", 0) or 0),
                }
            )
        comparison["case_deltas"] = case_deltas
        return comparison

    def restore_prompt_version(self, version_id: int) -> dict[str, Any]:
        version = self.get_prompt_version(version_id)
        if not version:
            raise ValueError(f"Prompt version {version_id} not found")
        commit = str(version["git_commit"])
        sandbox_root = Path(version["sandbox_root"]).resolve() if version.get("sandbox_root") else None
        self._ensure_ready()

        restored_files: list[str] = []
        self._restore_tree_from_commit(
            commit,
            "global_agent_prompt",
            self._global_prompt_dir,
            restored_files,
        )
        if sandbox_root:
            override_dir = sandbox_root / ".mindshard" / "state" / "prompt_overrides"
            self._restore_tree_from_commit(
                commit,
                "project_prompt_overrides",
                override_dir,
                restored_files,
                allow_missing=True,
            )
            project_meta_dir = sandbox_root / ".mindshard" / "state"
            self._restore_tree_from_commit(
                commit,
                "project_meta",
                project_meta_dir,
                restored_files,
                allow_missing=True,
            )
        return {
            "version_id": version_id,
            "git_commit": commit,
            "restored_files": restored_files,
        }

    def _ensure_ready(self) -> None:
        self.version_root.mkdir(parents=True, exist_ok=True)
        readme = self.version_root / "README.md"
        if not readme.exists():
            readme.write_text(
                "# Prompt Versioning\n\n"
                "Local Git history for effective prompt sources plus SQLite tracking for probe runs.\n",
                encoding="utf-8",
            )
        gitignore = self.version_root / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(
                "prompt_eval.db\n"
                "__pycache__/\n"
                "*.pyc\n",
                encoding="utf-8",
            )
        if not (self.version_root / ".git").exists():
            self._run_git("init")
            self._run_git("config", "user.name", "Mindshard Prompt Tracker")
            self._run_git("config", "user.email", "prompt-tracker@local")
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prompt_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    workspace_root TEXT NOT NULL,
                    sandbox_root TEXT,
                    git_commit TEXT NOT NULL UNIQUE,
                    reason TEXT,
                    changed_path TEXT,
                    source_fingerprint TEXT,
                    prompt_fingerprint TEXT,
                    notes TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS probe_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    prompt_version_id INTEGER,
                    git_commit TEXT,
                    probe_name TEXT,
                    probe_type TEXT,
                    model_name TEXT,
                    query_text TEXT,
                    status TEXT,
                    summary TEXT,
                    duration_ms REAL,
                    first_token_latency_ms REAL,
                    rounds INTEGER,
                    tokens_in TEXT,
                    tokens_out TEXT,
                    tokens_in_num INTEGER DEFAULT 0,
                    tokens_out_num INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    source_fingerprint TEXT,
                    prompt_fingerprint TEXT,
                    accuracy_score REAL DEFAULT 0.0,
                    efficiency_score REAL DEFAULT 0.0,
                    overall_score REAL DEFAULT 0.0,
                    score REAL,
                    metadata_json TEXT,
                    response_excerpt TEXT,
                    warning_count INTEGER DEFAULT 0,
                    output_dir TEXT DEFAULT '',
                    FOREIGN KEY(prompt_version_id) REFERENCES prompt_versions(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS probe_findings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    probe_run_id INTEGER NOT NULL,
                    finding_key TEXT NOT NULL,
                    finding_value TEXT,
                    severity TEXT,
                    details TEXT,
                    FOREIGN KEY(probe_run_id) REFERENCES probe_runs(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS benchmark_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    prompt_version_id INTEGER,
                    git_commit TEXT,
                    suite_name TEXT,
                    suite_label TEXT,
                    model_name TEXT,
                    duration_ms REAL,
                    case_count INTEGER DEFAULT 0,
                    average_accuracy_score REAL DEFAULT 0.0,
                    average_efficiency_score REAL DEFAULT 0.0,
                    average_overall_score REAL DEFAULT 0.0,
                    total_tokens INTEGER DEFAULT 0,
                    total_rounds INTEGER DEFAULT 0,
                    metadata_json TEXT,
                    FOREIGN KEY(prompt_version_id) REFERENCES prompt_versions(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS benchmark_run_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    benchmark_run_id INTEGER NOT NULL,
                    probe_run_id INTEGER,
                    case_id TEXT,
                    case_label TEXT,
                    probe_type TEXT,
                    status TEXT,
                    overall_score REAL DEFAULT 0.0,
                    total_tokens INTEGER DEFAULT 0,
                    rounds INTEGER DEFAULT 0,
                    FOREIGN KEY(benchmark_run_id) REFERENCES benchmark_runs(id),
                    FOREIGN KEY(probe_run_id) REFERENCES probe_runs(id)
                )
                """
            )
            self._ensure_column(conn, "probe_runs", "tokens_in_num", "INTEGER DEFAULT 0")
            self._ensure_column(conn, "probe_runs", "tokens_out_num", "INTEGER DEFAULT 0")
            self._ensure_column(conn, "probe_runs", "total_tokens", "INTEGER DEFAULT 0")
            self._ensure_column(conn, "probe_runs", "accuracy_score", "REAL DEFAULT 0.0")
            self._ensure_column(conn, "probe_runs", "efficiency_score", "REAL DEFAULT 0.0")
            self._ensure_column(conn, "probe_runs", "overall_score", "REAL DEFAULT 0.0")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _sync_snapshot_tree(
        self,
        *,
        sandbox_root: Path | None,
        changed_path: Path | None,
        prompt_build: PromptBuildResult | None,
        reason: str,
        notes: str,
        created_at: str,
    ) -> None:
        self._copy_markdown_dir(self._global_prompt_dir, self.version_root / "global_agent_prompt")
        override_dir = sandbox_root / ".mindshard" / "state" / "prompt_overrides" if sandbox_root else None
        if override_dir and override_dir.exists():
            self._copy_markdown_dir(override_dir, self.version_root / "project_prompt_overrides")
        else:
            shutil.rmtree(self.version_root / "project_prompt_overrides", ignore_errors=True)
        project_meta = sandbox_root / ".mindshard" / "state" / "project_meta.json" if sandbox_root else None
        project_meta_dir = self.version_root / "project_meta"
        if project_meta and project_meta.exists():
            project_meta_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(project_meta, project_meta_dir / "project_meta.json")
        else:
            shutil.rmtree(project_meta_dir, ignore_errors=True)

        manifest = {
            "created_at": created_at,
            "workspace_root": str(self.workspace_root),
            "sandbox_root": str(sandbox_root) if sandbox_root else "",
            "reason": reason,
            "notes": notes,
            "changed_path": str(changed_path) if changed_path else "",
            "source_fingerprint": prompt_build.source_fingerprint if prompt_build else "",
            "prompt_fingerprint": prompt_build.prompt_fingerprint if prompt_build else "",
            "sections": len(prompt_build.sections) if prompt_build else 0,
            "warnings": list(prompt_build.warnings) if prompt_build else [],
        }
        (self.version_root / "manifest.json").write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )

    def _copy_markdown_dir(self, source_dir: Path, target_dir: Path) -> None:
        shutil.rmtree(target_dir, ignore_errors=True)
        target_dir.mkdir(parents=True, exist_ok=True)
        if not source_dir.exists():
            return
        for path in sorted(source_dir.glob("*.md")):
            shutil.copy2(path, target_dir / path.name)

    def _upsert_prompt_version(
        self,
        *,
        created_at: str,
        git_commit: str,
        sandbox_root: str,
        reason: str,
        changed_path: str,
        prompt_build: PromptBuildResult | None,
        notes: str,
    ) -> int:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO prompt_versions (
                    created_at, workspace_root, sandbox_root, git_commit, reason,
                    changed_path, source_fingerprint, prompt_fingerprint, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    str(self.workspace_root),
                    sandbox_root,
                    git_commit,
                    reason,
                    changed_path,
                    prompt_build.source_fingerprint if prompt_build else "",
                    prompt_build.prompt_fingerprint if prompt_build else "",
                    notes,
                ),
            )
            row = conn.execute(
                "SELECT id FROM prompt_versions WHERE git_commit = ?",
                (git_commit,),
            ).fetchone()
        return int(row["id"])

    def _restore_tree_from_commit(
        self,
        commit: str,
        repo_subdir: str,
        dest_dir: Path,
        restored_files: list[str],
        *,
        allow_missing: bool = False,
    ) -> None:
        files = self._git_list_files(commit, repo_subdir)
        if not files:
            if allow_missing:
                shutil.rmtree(dest_dir, ignore_errors=True)
                return
            raise RuntimeError(f"No files found in snapshot path: {repo_subdir}")

        if repo_subdir != "project_meta":
            shutil.rmtree(dest_dir, ignore_errors=True)
        dest_dir.mkdir(parents=True, exist_ok=True)
        for repo_path in files:
            rel = Path(repo_path).relative_to(repo_subdir)
            content = self._git_show_file(commit, repo_path)
            out_path = dest_dir / rel
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8")
            restored_files.append(str(out_path))

    def _git_list_files(self, commit: str, repo_subdir: str) -> list[str]:
        try:
            result = self._run_git("ls-tree", "-r", "--name-only", commit, repo_subdir)
            return [line.strip() for line in result.stdout.splitlines() if line.strip()]
        except Exception:
            return []

    def _git_show_file(self, commit: str, repo_path: str) -> str:
        result = self._run_git("show", f"{commit}:{repo_path}")
        return result.stdout

    def _commit_message(
        self,
        *,
        reason: str,
        changed_path: str | Path | None,
        prompt_build: PromptBuildResult | None,
    ) -> str:
        subject = reason.strip() or "prompt snapshot"
        if changed_path:
            subject += f" [{Path(changed_path).name}]"
        if prompt_build and prompt_build.source_fingerprint:
            subject += f" ({prompt_build.source_fingerprint[:8]})"
        return subject[:180]

    def _is_dirty(self) -> bool:
        result = self._run_git("status", "--porcelain")
        return bool(result.stdout.strip())

    def _head_commit(self) -> str:
        try:
            result = self._run_git("rev-parse", "HEAD")
            return result.stdout.strip()
        except Exception:
            return ""

    def _run_git(self, *args: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *args],
            cwd=self.version_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"git {' '.join(args)} failed")
        return result
