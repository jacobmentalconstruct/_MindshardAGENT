"""Prompt inspection and versioning callbacks — extracted from app.py."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from src.app_state import AppState


def prompt_sources_text(prompt_build: Any) -> str:
    lines = [
        f"Source fingerprint: {prompt_build.source_fingerprint[:12]}",
        f"Prompt fingerprint: {prompt_build.prompt_fingerprint[:12]}",
        "",
    ]
    if prompt_build.warnings:
        lines.append("Warnings:")
        for warning in prompt_build.warnings:
            lines.append(f"- {warning}")
        lines.append("")
    for section in prompt_build.sections:
        source = section.source_path or "(runtime)"
        lines.append(f"[{section.layer}] {section.name}")
        lines.append(source)
    return "\n".join(lines)


def set_prompt_inspector(s: AppState, prompt_build: Any) -> None:
    if not prompt_build:
        return
    s.window.control_pane.set_prompt_inspector(
        prompt_text=prompt_build.prompt,
        sources_text=prompt_sources_text(prompt_build),
    )


def refresh_prompt_inspector(s: AppState, user_text: str = "", *, announce: bool = False) -> Any:
    prompt_build = s.engine.preview_system_prompt(user_text=user_text)
    if prompt_build:
        set_prompt_inspector(s, prompt_build)
        if announce:
            s.activity.info(
                "prompt",
                f"Prompt docs reloaded ({prompt_build.source_fingerprint[:12]})",
            )
    return prompt_build


def snapshot_prompt_state(
    s: AppState,
    reason: str,
    *,
    changed_path: Optional[str | Path] = None,
    prompt_build: Any = None,
    notes: str = "",
) -> None:
    def _bg():
        snapshot = s.prompt_tuning.snapshot_current_state(
            reason=reason,
            sandbox_root=s.config.sandbox_root or "",
            changed_path=changed_path,
            prompt_build=prompt_build,
            notes=notes,
        )
        def _ui():
            if snapshot:
                s.activity.info("prompt", f"Prompt version snapshot saved ({snapshot.git_commit[:8]})")
            else:
                s.activity.warn("prompt", "Prompt version snapshot failed")
        s.root.after(0, _ui)
    threading.Thread(target=_bg, daemon=True, name="prompt-snapshot").start()


def on_prompt_source_saved(s: AppState, path: Path) -> None:
    prompt_build = refresh_prompt_inspector(s, s.ui_state.last_user_input, announce=True)
    snapshot_prompt_state(
        s,
        "prompt source saved",
        changed_path=path,
        prompt_build=prompt_build,
    )
