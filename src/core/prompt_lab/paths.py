"""Prompt Lab path resolution and storage doctrine helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PromptLabPaths:
    project_root: Path
    package_root: Path
    assets_root: Path
    state_root: Path
    db_path: Path
    operations_log_path: Path
    prompt_profiles_dir: Path
    execution_plans_dir: Path
    bindings_dir: Path
    drafts_dir: Path
    published_dir: Path
    active_dir: Path
    build_artifacts_dir: Path
    training_suites_dir: Path
    source_overlays_dir: Path
    eval_runs_dir: Path
    promotion_dir: Path


def resolve_prompt_lab_paths(project_root: str | Path) -> PromptLabPaths:
    root = Path(project_root).resolve()
    state_root = root / ".mindshard" / "prompt_lab"
    return PromptLabPaths(
        project_root=root,
        package_root=root / "src" / "core" / "prompt_lab",
        assets_root=root / "prompt_lab",
        state_root=state_root,
        db_path=state_root / "prompt_lab.sqlite3",
        operations_log_path=state_root / "operations.jsonl",
        prompt_profiles_dir=state_root / "prompt_profiles",
        execution_plans_dir=state_root / "execution_plans",
        bindings_dir=state_root / "bindings",
        drafts_dir=state_root / "drafts",
        published_dir=state_root / "published",
        active_dir=state_root / "active",
        build_artifacts_dir=state_root / "build_artifacts",
        training_suites_dir=state_root / "training_suites",
        source_overlays_dir=state_root / "source_overlays",
        eval_runs_dir=state_root / "eval_runs",
        promotion_dir=state_root / "promotion",
    )
