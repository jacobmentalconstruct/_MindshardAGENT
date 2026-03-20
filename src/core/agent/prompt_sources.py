"""Load editable prompt source documents for the agent behavior layer."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path


GLOBAL_PROMPT_DIR = Path("_docs") / "agent_prompt"
PROJECT_OVERRIDE_DIR = Path(".mindshard") / "state" / "prompt_overrides"
DEFAULT_PROMPT_DOC_FILENAMES = (
    "00_identity.md",
    "10_workspace_semantics.md",
    "20_intent_interpretation.md",
    "30_file_listing_rules.md",
    "40_response_style.md",
    "50_tool_usage_preferences.md",
    "90_local_notes.md",
)


@dataclass(frozen=True)
class PromptSection:
    """One ordered prompt section from docs, metadata, or runtime scaffolding."""

    name: str
    layer: str
    content: str
    source_path: str = ""


@dataclass(frozen=True)
class PromptSourceResult:
    """Merged editable prompt-doc layer plus diagnostics."""

    sections: tuple[PromptSection, ...]
    text: str
    fingerprint: str
    warnings: tuple[str, ...] = ()


def default_global_prompt_dir() -> Path:
    """Return the repo-level prompt-doc folder."""
    return Path(__file__).resolve().parents[3] / GLOBAL_PROMPT_DIR


def project_override_dir(sandbox_root: str | Path | None) -> Path | None:
    """Return the project-specific prompt override folder if a sandbox exists."""
    if not sandbox_root:
        return None
    return Path(sandbox_root).resolve() / PROJECT_OVERRIDE_DIR


def load_prompt_sources(
    sandbox_root: str | Path | None = None,
    global_prompt_dir: str | Path | None = None,
    override_dir: str | Path | None = None,
) -> PromptSourceResult:
    """Load global prompt docs and optional project override docs."""

    warnings: list[str] = []
    global_dir = Path(global_prompt_dir).resolve() if global_prompt_dir else default_global_prompt_dir()
    overrides_dir = Path(override_dir).resolve() if override_dir else project_override_dir(sandbox_root)

    global_sections = _load_sections_from_dir(global_dir, "global_doc", warn_if_missing=True, warnings=warnings)
    override_sections = _load_sections_from_dir(
        overrides_dir, "project_override", warn_if_missing=False, warnings=warnings
    )

    global_names = {section.name for section in global_sections}
    override_by_name = {section.name: section for section in override_sections}

    merged_sections: list[PromptSection] = []
    for section in global_sections:
        merged_sections.append(override_by_name.pop(section.name, section))

    # Any extra override files append after the standard ordered set.
    for section in sorted(override_by_name.values(), key=lambda item: item.name.lower()):
        merged_sections.append(section)

    text = "\n\n".join(section.content.strip() for section in merged_sections if section.content.strip())
    fingerprint = _fingerprint_sections(merged_sections)
    return PromptSourceResult(
        sections=tuple(merged_sections),
        text=text,
        fingerprint=fingerprint,
        warnings=tuple(warnings),
    )


def _load_sections_from_dir(
    base_dir: Path | None,
    layer: str,
    *,
    warn_if_missing: bool,
    warnings: list[str],
) -> list[PromptSection]:
    if base_dir is None:
        return []
    if not base_dir.exists():
        if warn_if_missing:
            warnings.append(f"Prompt source directory missing: {base_dir}")
        return []
    if not base_dir.is_dir():
        warnings.append(f"Prompt source path is not a directory: {base_dir}")
        return []

    sections: list[PromptSection] = []
    for path in sorted(base_dir.glob("*.md"), key=lambda item: item.name.lower()):
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as exc:  # pragma: no cover - exercised via warnings contract
            warnings.append(f"Failed to read prompt source '{path}': {exc}")
            continue
        sections.append(
            PromptSection(
                name=path.name,
                layer=layer,
                content=content,
                source_path=str(path),
            )
        )
    return sections


def _fingerprint_sections(sections: list[PromptSection]) -> str:
    digest = hashlib.sha256()
    for section in sections:
        digest.update(section.layer.encode("utf-8"))
        digest.update(b"\0")
        digest.update(section.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(section.content.encode("utf-8"))
        digest.update(b"\0")
        digest.update(section.source_path.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()
