"""Project metadata — stores the project brief and profile in .mindshard/state/project_meta.json."""

from __future__ import annotations
import json
from pathlib import Path
from typing import Optional
from src.core.utils.clock import utc_iso

PROFILE_STANDARD = "standard"
PROFILE_SELF_EDIT = "self_edit"

DEFAULT_META = {
    "display_name": "",
    "project_type": "General",
    "project_purpose": "",
    "current_goal": "",
    "constraints": "",
    "sync_policy": "confirm",
    "profile": PROFILE_STANDARD,
    "source_path": "",   # original source path for sync-back (empty = in-place)
    "attached_at": "",
}


class ProjectMeta:
    """Read/write .mindshard/state/project_meta.json."""

    def __init__(self, project_root: str | Path):
        self._root = Path(project_root).resolve()
        self._path = self._root / ".mindshard" / "state" / "project_meta.json"
        self._data: dict = {}
        self._load()

    @property
    def exists(self) -> bool:
        return self._path.exists()

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                self._data = dict(DEFAULT_META)
        else:
            self._data = dict(DEFAULT_META)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        self._data[key] = value

    def update(self, d: dict) -> None:
        self._data.update(d)
        self.save()

    @property
    def display_name(self) -> str:
        return self._data.get("display_name", "") or self._root.name

    @property
    def profile(self) -> str:
        return self._data.get("profile", PROFILE_STANDARD)

    @property
    def is_self_edit(self) -> bool:
        return self.profile == PROFILE_SELF_EDIT

    @property
    def source_path(self) -> Optional[str]:
        p = self._data.get("source_path", "")
        return p if p else None

    @property
    def prompt_overrides_dir(self) -> Path:
        return self._root / ".mindshard" / "state" / "prompt_overrides"

    def brief_form_data(self) -> dict:
        """Return dialog-friendly project brief values."""
        return {
            "display_name": self.display_name,
            "project_purpose": self._data.get("project_purpose", ""),
            "current_goal": self._data.get("current_goal", ""),
            "project_type": self._data.get("project_type", "General") or "General",
            "constraints": self._data.get("constraints", ""),
            "profile": self.profile,
        }

    def ensure_prompt_override_scaffold(self) -> list[Path]:
        """Create the override folder and a minimal starter scaffold if needed."""
        override_dir = self.prompt_overrides_dir
        override_dir.mkdir(parents=True, exist_ok=True)

        created: list[Path] = []
        existing_markdown = list(override_dir.glob("*.md"))
        if existing_markdown:
            return created

        readme = override_dir / "README.md"
        readme.write_text(
            "# Prompt Overrides\n\n"
            "Place Markdown files here to override or extend the repo-level agent prompt docs.\n\n"
            "- Use the same filename as a global prompt doc to replace that section.\n"
            "- Add a new Markdown file to append a project-specific section after the defaults.\n"
            "- This folder is project-local and lives inside `.mindshard/state/`.\n",
            encoding="utf-8",
        )
        created.append(readme)

        local_notes = override_dir / "90_local_notes.md"
        local_notes.write_text(
            "## Project Override Notes\n"
            "- Add project-specific behavior guidance here.\n"
            "- Keep the notes focused on interpretation, file-listing behavior, and response style.\n",
            encoding="utf-8",
        )
        created.append(local_notes)
        return created

    def prompt_context(self) -> str:
        """Format project brief for injection into agent system prompt."""
        lines = []
        name = self.display_name
        purpose = self._data.get("project_purpose", "")
        goal = self._data.get("current_goal", "")
        ptype = self._data.get("project_type", "")
        constraints = self._data.get("constraints", "")
        profile = self.profile

        lines.append(f"## Project Brief")
        lines.append(f"- **Project**: {name}")
        if ptype:
            lines.append(f"- **Type**: {ptype}")
        if purpose:
            lines.append(f"- **Purpose**: {purpose}")
        if goal:
            lines.append(f"- **Current goal**: {goal}")
        if constraints:
            lines.append(f"- **Constraints**: {constraints}")
        if profile == PROFILE_SELF_EDIT:
            lines.append(f"- **Profile**: Self-edit — you are working on MindshardAGENT's own source code")
        lines.append("")
        return "\n".join(lines)
