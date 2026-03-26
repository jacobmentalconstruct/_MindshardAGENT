"""File-backed source inspection for Prompt Lab."""

from __future__ import annotations

from pathlib import Path

from .contracts import PromptProfile, PromptSourceRef
from .operation_log import PromptLabOperationLog


class SourceService:
    """Inspect and resolve file-backed prompt sources without editing them."""

    def __init__(self, project_root: str | Path, *, operation_log: PromptLabOperationLog | None = None):
        self.project_root = Path(project_root).resolve()
        self._operation_log = operation_log

    def inspect_source(self, source_ref: str) -> PromptSourceRef:
        relative_path = str(source_ref).strip()
        source_path = (self.project_root / relative_path).resolve()
        metadata = {
            "exists": source_path.exists(),
            "is_file": source_path.is_file(),
            "project_relative_path": relative_path,
        }
        if source_path.exists() and source_path.is_file():
            metadata["size_bytes"] = source_path.stat().st_size
        result = PromptSourceRef(
            id=relative_path,
            path=relative_path,
            metadata=metadata,
        )
        if self._operation_log is not None:
            self._operation_log.record(
                channel="service",
                action="inspect_source",
                status="ok",
                details={"source_ref": relative_path, "exists": metadata["exists"]},
            )
        return result

    def resolve_profile_sources(self, profile: PromptProfile) -> list[PromptSourceRef]:
        resolved = [self.inspect_source(source_ref) for source_ref in profile.source_refs]
        if self._operation_log is not None:
            self._operation_log.record(
                channel="service",
                action="resolve_profile_sources",
                status="ok",
                details={"profile_id": profile.id, "source_count": len(resolved)},
            )
        return resolved

    def read_source_text(self, source_ref: str) -> str:
        relative_path = str(source_ref).strip()
        source_path = (self.project_root / relative_path).resolve()
        text = source_path.read_text(encoding="utf-8")
        if self._operation_log is not None:
            self._operation_log.record(
                channel="service",
                action="read_source_text",
                status="ok",
                details={"source_ref": relative_path, "chars": len(text)},
            )
        return text
