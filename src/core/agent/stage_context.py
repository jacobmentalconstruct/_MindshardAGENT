"""Stage context assembly — merges pre-inference stage results for injection.

Takes gathered context, probe results, and planner output, and formats
them into a compact text block for injection into the primary model's
message history.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.agent.context_gatherer import GatheredContext
    from src.core.agent.execution_planner import PlannerStageResult
    from src.core.agent.probe_stage import ProbeStageResult


@dataclass(frozen=True)
class StageContext:
    """Combined output from all pre-inference stages."""

    gathered: GatheredContext | None = None
    probes: ProbeStageResult | None = None
    planner: PlannerStageResult | None = None


def format_stage_context(ctx: StageContext) -> str:
    """Format all stage results into a single injection block.

    Returns an empty string if no useful context was produced,
    so callers can skip injection entirely.
    """
    parts: list[str] = []

    if ctx.gathered:
        gathered_text = _format_gathered(ctx.gathered)
        if gathered_text:
            parts.append(gathered_text)

    if ctx.probes and ctx.probes.probes:
        probe_text = _format_probes(ctx.probes)
        if probe_text:
            parts.append(probe_text)

    if not parts:
        return ""

    return "\n\n".join(parts)


def _format_gathered(gathered: GatheredContext) -> str:
    """Format gathered workspace context."""
    lines: list[str] = []
    lines.append("## Workspace Context (pre-gathered)")

    if gathered.file_tree:
        lines.append(f"\nFile tree ({gathered.file_count} files):")
        # Indent tree lines for readability
        for tree_line in gathered.file_tree.splitlines():
            lines.append(f"  {tree_line}")

    if gathered.key_file_snippets:
        lines.append("\nKey files detected:")
        for fname, snippet in gathered.key_file_snippets.items():
            # Show just the first few lines as a summary
            preview_lines = snippet.splitlines()[:5]
            preview = "\n  ".join(preview_lines)
            lines.append(f"  {fname}:")
            lines.append(f"  {preview}")
            if len(snippet.splitlines()) > 5:
                lines.append(f"  ... ({len(snippet.splitlines())} lines total)")

    if gathered.project_brief:
        lines.append(f"\nProject brief:\n{gathered.project_brief}")

    if gathered.journal_summary:
        lines.append(f"\nRecent activity:\n{gathered.journal_summary}")

    return "\n".join(lines) if len(lines) > 1 else ""


def _format_probes(probes: ProbeStageResult) -> str:
    """Format probe results."""
    lines: list[str] = ["## Pre-analysis"]
    for probe in probes.probes:
        if probe.answer.strip():
            lines.append(f"- **{probe.question}**: {probe.answer.strip()}")
    return "\n".join(lines) if len(lines) > 1 else ""
