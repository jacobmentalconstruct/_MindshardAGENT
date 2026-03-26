"""App-layer project metadata and prompt-override edit shims."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.app_state import AppState


def on_edit_project_brief(s: AppState) -> None:
    from src.app_prompt import refresh_prompt_inspector, snapshot_prompt_state
    from src.ui.dialogs.project_brief_dialog import ProjectBriefDialog

    if not s.engine.project_meta:
        if s.ui_facade:
            s.ui_facade.post_system_message("No project attached.")
        return

    meta = s.engine.project_meta
    dlg = ProjectBriefDialog(
        s.root,
        project_name=meta.display_name,
        is_self_edit=meta.is_self_edit,
        initial_data=meta.brief_form_data(),
        submit_label="SAVE BRIEF",
        title_text="EDIT PROJECT BRIEF",
    )
    if dlg.result is None:
        return

    meta.update(dlg.result)
    display = meta.display_name
    source_path = meta.source_path or ""
    s.window.set_project_name(display)
    s.window.set_project_paths(source_path, s.config.sandbox_root)
    s.activity.info("project", f"Project brief updated: {display}")
    prompt_build = refresh_prompt_inspector(s, s.ui_state.last_user_input, announce=True)
    snapshot_prompt_state(s, "project brief updated", changed_path=meta.path, prompt_build=prompt_build)


def on_edit_prompt_overrides(s: AppState) -> None:
    from src.app_prompt import refresh_prompt_inspector, snapshot_prompt_state

    if not s.engine.project_meta:
        if s.ui_facade:
            s.ui_facade.post_system_message("No project attached.")
        return

    meta = s.engine.project_meta
    created = meta.ensure_prompt_override_scaffold()
    override_dir = meta.prompt_overrides_dir

    try:
        import os

        os.startfile(str(override_dir))  # type: ignore[attr-defined]
    except Exception:
        try:
            s.engine.run_cli(f'explorer "{override_dir}"')
        except Exception:
            pass

    if created:
        s.activity.info("prompt", f"Prompt override scaffold created at {override_dir}")
        prompt_build = refresh_prompt_inspector(s, s.ui_state.last_user_input, announce=True)
        snapshot_prompt_state(
            s,
            "prompt override scaffold created",
            changed_path=override_dir,
            prompt_build=prompt_build,
        )
    else:
        s.activity.info("prompt", f"Opened prompt overrides at {override_dir}")
        refresh_prompt_inspector(s, s.ui_state.last_user_input, announce=True)
