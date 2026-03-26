"""
Build a parsable, size-limited code sampler for video/audio overview work.

This script emits a curated dump of the files that best explain the system to
outside readers without requiring a full repository handoff.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = Path(__file__).resolve().parent / "95_OVERVIEW_CODE_SAMPLER.txt"
MAX_TOTAL_LINES = 2800


@dataclass(frozen=True)
class FileSpec:
    path: str
    max_lines: int
    purpose: str


FILE_SPECS = [
    FileSpec("README.md", 99, "Public-facing project framing and safety posture."),
    FileSpec("src/app.py", 80, "Thin composition root for the desktop app."),
    FileSpec("src/app_bootstrap.py", 120, "Startup assembly and ownership wiring."),
    FileSpec("src/app_lifecycle.py", 120, "Shutdown and lifecycle choreography."),
    FileSpec("src/app_prompt.py", 120, "Main-app prompt workbench orchestration."),
    FileSpec("src/app_prompt_lab.py", 120, "Main-app Prompt Lab bridge and summary seam."),
    FileSpec("src/core/engine.py", 140, "Central runtime coordinator."),
    FileSpec("src/core/agent/loop_contract.md", 120, "Loop contract and result semantics."),
    FileSpec("src/core/agent/turn_pipeline.py", 140, "Turn execution pipeline."),
    FileSpec("src/ui/panes/prompt_workbench_tabs.py", 160, "Prompt workbench UI tabs and app bridge surface."),
    FileSpec("src/prompt_lab/main.py", 120, "Prompt Lab entrypoint."),
    FileSpec("src/prompt_lab/workbench.py", 180, "Dedicated Prompt Lab workbench UI."),
    FileSpec("src/prompt_lab/mcp_server.py", 140, "Prompt Lab MCP surface."),
    FileSpec("src/core/prompt_lab/contracts.py", 160, "Prompt Lab canonical objects."),
    FileSpec("src/core/prompt_lab/storage.py", 140, "Prompt Lab storage doctrine in code."),
    FileSpec("src/core/prompt_lab/validation.py", 140, "Validation and publish/apply readiness rules."),
    FileSpec("src/core/prompt_lab/runtime_loader.py", 120, "Runtime-facing active package loader."),
    FileSpec("_docs/external_atlas/10_ARCHITECTURE_MAP.md", 120, "External architecture map for narration support."),
    FileSpec("_docs/external_atlas/20_RUNTIME_LIFECYCLE.md", 120, "External lifecycle map for narration support."),
]


def _read_excerpt(path: Path, max_lines: int) -> tuple[list[str], int]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return lines[:max_lines], len(lines)


def build_sampler() -> str:
    sections: list[str] = []
    lines_used = 0
    included: list[tuple[FileSpec, int]] = []

    for spec in FILE_SPECS:
        path = REPO_ROOT / spec.path
        if not path.exists():
            continue
        excerpt, total_line_count = _read_excerpt(path, spec.max_lines)
        projected = lines_used + len(excerpt)
        if projected > MAX_TOTAL_LINES:
            break
        included.append((spec, total_line_count))
        lines_used = projected

    sections.append("MINDSHARDAGENT OVERVIEW CODE SAMPLER")
    sections.append(f"Generated UTC: {datetime.now(timezone.utc).isoformat()}")
    sections.append(f"Repository Root: {REPO_ROOT}")
    sections.append(f"Output Budget: {MAX_TOTAL_LINES} excerpt lines")
    sections.append(f"Included Excerpt Lines: {lines_used}")
    sections.append("")
    sections.append("INCLUDED FILES")
    for spec, total_line_count in included:
        sections.append(
            f"- {spec.path} | total_lines={total_line_count} | excerpt_lines={min(spec.max_lines, total_line_count)} | purpose={spec.purpose}"
        )
    sections.append("")

    for spec, total_line_count in included:
        path = REPO_ROOT / spec.path
        excerpt, _ = _read_excerpt(path, spec.max_lines)
        sections.append("=" * 80)
        sections.append(f"FILE: {spec.path}")
        sections.append(f"ABSOLUTE_PATH: {path}")
        sections.append(f"PURPOSE: {spec.purpose}")
        sections.append(f"EXCERPT_RANGE: 1-{len(excerpt)} of {total_line_count}")
        sections.append("=" * 80)
        for index, line in enumerate(excerpt, start=1):
            sections.append(f"{index:04d}: {line}")
        sections.append("")

    return "\n".join(sections).rstrip() + "\n"


def main() -> int:
    OUTPUT_PATH.write_text(build_sampler(), encoding="utf-8")
    print(OUTPUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
