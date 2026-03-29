"""Prompt Lab storage for Phase 1A.

Design objects are canonical JSON.
Indexed history objects are canonical SQLite records.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any

from .contracts import (
    ACTIVE_PROMPT_LAB_STATE_KIND,
    BINDING_RECORD_KIND,
    EVAL_RUN_KIND,
    EXECUTION_PLAN_KIND,
    JSON_DESIGN_KINDS,
    PUBLISHED_PROMPT_LAB_PACKAGE_KIND,
    PROMOTION_RECORD_KIND,
    PROMPT_BUILD_ARTIFACT_KIND,
    PROMPT_PROFILE_KIND,
    SQLITE_HISTORY_KINDS,
    TRAINING_RUN_KIND,
    TRAINING_SUITE_KIND,
    VALIDATION_SNAPSHOT_KIND,
    ActivePromptLabState,
    BindingRecord,
    DesignObject,
    EvalRun,
    ExecutionPlan,
    PublishedPromptLabPackage,
    PromptBuildArtifact,
    PromptLabRecord,
    PromptProfile,
    PromotionRecord,
    TrainingRun,
    TrainingSuite,
    ValidationSnapshot,
    deserialize_record,
    get_record_kind,
    serialize_record,
    stable_json_dumps,
)
from .paths import PromptLabPaths, resolve_prompt_lab_paths


def ensure_prompt_lab_directories(project_root: str | Path) -> PromptLabPaths:
    """Create the agreed Prompt Lab directory tree if it does not exist."""
    paths = resolve_prompt_lab_paths(project_root)
    paths.state_root.mkdir(parents=True, exist_ok=True)
    for directory in (
        paths.prompt_profiles_dir,
        paths.execution_plans_dir,
        paths.bindings_dir,
        paths.drafts_dir,
        paths.published_dir,
        paths.active_dir,
        paths.build_artifacts_dir,
        paths.training_suites_dir,
        paths.source_overlays_dir,
        paths.eval_runs_dir,
        paths.promotion_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    return paths


def _resolve_json_directory(paths: PromptLabPaths, kind: str) -> Path:
    mapping = {
        PROMPT_PROFILE_KIND: paths.prompt_profiles_dir,
        EXECUTION_PLAN_KIND: paths.execution_plans_dir,
        BINDING_RECORD_KIND: paths.bindings_dir,
        PROMPT_BUILD_ARTIFACT_KIND: paths.build_artifacts_dir,
        TRAINING_SUITE_KIND: paths.training_suites_dir,
        PUBLISHED_PROMPT_LAB_PACKAGE_KIND: paths.published_dir,
        ACTIVE_PROMPT_LAB_STATE_KIND: paths.active_dir,
    }
    try:
        return mapping[kind]
    except KeyError as exc:
        raise ValueError(f"Unsupported Prompt Lab JSON kind: {kind!r}") from exc


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_prompt_lab_db(project_root: str | Path) -> PromptLabPaths:
    paths = ensure_prompt_lab_directories(project_root)
    with _connect(paths.db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS eval_runs (
                id TEXT PRIMARY KEY,
                execution_plan_id TEXT NOT NULL,
                suite_name TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS promotion_records (
                id TEXT PRIMARY KEY,
                target_project TEXT NOT NULL,
                promoted_execution_plan_id TEXT NOT NULL,
                validation_snapshot_id TEXT NOT NULL,
                active INTEGER NOT NULL,
                promoted_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS training_runs (
                id TEXT PRIMARY KEY,
                package_id TEXT NOT NULL,
                profile_id TEXT NOT NULL,
                suite_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS validation_snapshots (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
    return paths


@dataclass
class PromptLabStorage:
    project_root: Path
    paths: PromptLabPaths

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).resolve()
        self.paths = initialize_prompt_lab_db(self.project_root)

    def save_design_object(self, record: DesignObject) -> DesignObject:
        payload = serialize_record(record)
        canonical = deserialize_record(payload)
        kind = get_record_kind(canonical)
        if kind not in JSON_DESIGN_KINDS:
            raise ValueError(f"Record kind {kind!r} is not a JSON design object")
        object_id = getattr(canonical, "id", "").strip()
        if not object_id:
            raise ValueError(f"Cannot save {kind!r} without a non-empty id")
        if kind == ACTIVE_PROMPT_LAB_STATE_KIND:
            path = _resolve_json_directory(self.paths, kind) / "active_prompt_lab_state.json"
        else:
            path = _resolve_json_directory(self.paths, kind) / f"{object_id}.json"
        path.write_text(stable_json_dumps(payload) + "\n", encoding="utf-8")
        return canonical

    def load_design_object(self, kind: str, object_id: str) -> DesignObject:
        if kind not in JSON_DESIGN_KINDS:
            raise ValueError(f"Record kind {kind!r} is not a JSON design object")
        if kind == ACTIVE_PROMPT_LAB_STATE_KIND:
            path = _resolve_json_directory(self.paths, kind) / "active_prompt_lab_state.json"
        else:
            path = _resolve_json_directory(self.paths, kind) / f"{object_id}.json"
        if not path.exists():
            raise FileNotFoundError(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return deserialize_record(payload)  # type: ignore[return-value]

    def list_design_objects(self, kind: str) -> list[dict[str, Any]]:
        if kind not in JSON_DESIGN_KINDS:
            raise ValueError(f"Record kind {kind!r} is not a JSON design object")
        summaries: list[dict[str, Any]] = []
        file_glob = "active_prompt_lab_state.json" if kind == ACTIVE_PROMPT_LAB_STATE_KIND else "*.json"
        for path in sorted(_resolve_json_directory(self.paths, kind).glob(file_glob)):
            if path.name.startswith("."):
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            record = deserialize_record(payload)
            data = payload.get("data", {})
            summaries.append(
                {
                    "id": getattr(record, "id", path.stem),
                    "kind": kind,
                    "path": str(path),
                    "name": data.get("name", data.get("label", "")),
                    "fingerprint": data.get(
                        "version_fingerprint",
                        data.get(
                            "binding_fingerprint",
                            data.get(
                                "prompt_fingerprint",
                                data.get("package_fingerprint", ""),
                            ),
                        ),
                    ),
                }
            )
        return summaries

    def save_history_record(self, record: EvalRun | TrainingRun | PromotionRecord | ValidationSnapshot) -> PromptLabRecord:
        payload = serialize_record(record)
        canonical = deserialize_record(payload)
        kind = get_record_kind(canonical)
        if kind not in SQLITE_HISTORY_KINDS:
            raise ValueError(f"Record kind {kind!r} is not a SQLite history record")
        json_blob = stable_json_dumps(payload)
        with _connect(self.paths.db_path) as conn:
            if kind == EVAL_RUN_KIND:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO eval_runs (
                        id, execution_plan_id, suite_name, status, created_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        canonical.id,
                        canonical.execution_plan_id,
                        canonical.suite_name,
                        canonical.status,
                        canonical.created_at,
                        json_blob,
                    ),
                )
            elif kind == TRAINING_RUN_KIND:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO training_runs (
                        id, package_id, profile_id, suite_id, status, created_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        canonical.id,
                        canonical.package_id,
                        canonical.profile_id,
                        canonical.suite_id,
                        canonical.status,
                        canonical.created_at,
                        json_blob,
                    ),
                )
            elif kind == PROMOTION_RECORD_KIND:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO promotion_records (
                        id, target_project, promoted_execution_plan_id, validation_snapshot_id,
                        active, promoted_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        canonical.id,
                        canonical.target_project,
                        canonical.promoted_execution_plan_id,
                        canonical.validation_snapshot_id,
                        1 if canonical.active else 0,
                        canonical.promoted_at,
                        json_blob,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO validation_snapshots (
                        id, status, created_at, payload_json
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        canonical.id,
                        canonical.status,
                        canonical.created_at,
                        json_blob,
                    ),
                )
        return canonical

    def load_history_record(self, kind: str, object_id: str) -> EvalRun | TrainingRun | PromotionRecord | ValidationSnapshot:
        if kind not in SQLITE_HISTORY_KINDS:
            raise ValueError(f"Record kind {kind!r} is not a SQLite history record")
        table_name = {
            EVAL_RUN_KIND: "eval_runs",
            TRAINING_RUN_KIND: "training_runs",
            PROMOTION_RECORD_KIND: "promotion_records",
            VALIDATION_SNAPSHOT_KIND: "validation_snapshots",
        }[kind]
        with _connect(self.paths.db_path) as conn:
            row = conn.execute(
                f"SELECT payload_json FROM {table_name} WHERE id = ?",
                (object_id,),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(object_id)
        return deserialize_record(json.loads(row["payload_json"]))  # type: ignore[return-value]

    def list_history_records(self, kind: str) -> list[dict[str, Any]]:
        if kind not in SQLITE_HISTORY_KINDS:
            raise ValueError(f"Record kind {kind!r} is not a SQLite history record")
        query = {
            EVAL_RUN_KIND: "SELECT id, execution_plan_id AS primary_ref, suite_name AS label, status, created_at FROM eval_runs ORDER BY created_at DESC, id ASC",
            TRAINING_RUN_KIND: "SELECT id, profile_id AS primary_ref, suite_id AS label, status, created_at FROM training_runs ORDER BY created_at DESC, id ASC",
            PROMOTION_RECORD_KIND: "SELECT id, promoted_execution_plan_id AS primary_ref, target_project AS label, CASE WHEN active = 1 THEN 'active' ELSE 'inactive' END AS status, promoted_at AS created_at FROM promotion_records ORDER BY promoted_at DESC, id ASC",
            VALIDATION_SNAPSHOT_KIND: "SELECT id, '' AS primary_ref, status AS label, status, created_at FROM validation_snapshots ORDER BY created_at DESC, id ASC",
        }[kind]
        with _connect(self.paths.db_path) as conn:
            rows = conn.execute(query).fetchall()
        return [
            {
                "id": row["id"],
                "kind": kind,
                "primary_ref": row["primary_ref"],
                "label": row["label"],
                "status": row["status"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def save_prompt_profile(self, record: PromptProfile) -> PromptProfile:
        return self.save_design_object(record)  # type: ignore[return-value]

    def save_execution_plan(self, record: ExecutionPlan) -> ExecutionPlan:
        return self.save_design_object(record)  # type: ignore[return-value]

    def save_binding_record(self, record: BindingRecord) -> BindingRecord:
        return self.save_design_object(record)  # type: ignore[return-value]

    def save_build_artifact(self, record: PromptBuildArtifact) -> PromptBuildArtifact:
        return self.save_design_object(record)  # type: ignore[return-value]

    def save_published_package(self, record: PublishedPromptLabPackage) -> PublishedPromptLabPackage:
        return self.save_design_object(record)  # type: ignore[return-value]

    def save_active_state(self, record: ActivePromptLabState) -> ActivePromptLabState:
        return self.save_design_object(record)  # type: ignore[return-value]

    def save_training_suite(self, record: TrainingSuite) -> TrainingSuite:
        return self.save_design_object(record)  # type: ignore[return-value]

    def save_eval_run(self, record: EvalRun) -> EvalRun:
        return self.save_history_record(record)  # type: ignore[return-value]

    def save_training_run(self, record: TrainingRun) -> TrainingRun:
        return self.save_history_record(record)  # type: ignore[return-value]

    def save_promotion_record(self, record: PromotionRecord) -> PromotionRecord:
        return self.save_history_record(record)  # type: ignore[return-value]

    def save_validation_snapshot(self, record: ValidationSnapshot) -> ValidationSnapshot:
        return self.save_history_record(record)  # type: ignore[return-value]


def build_prompt_lab_storage(project_root: str | Path) -> PromptLabStorage:
    return PromptLabStorage(project_root)
