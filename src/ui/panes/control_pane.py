"""Primary workstation shell.

This pane is intentionally shallow. It composes three owned visual regions:
  left rail      -> workspace/session/sandbox/git controls
  center area    -> chat + compose/CLI dock
  right workbench-> prompt context, sources, inspect, tools, evidence bag
"""

from __future__ import annotations

import tkinter as tk

from src.ui import theme as T
from src.ui.panes.interaction_shell import InteractionShell
from src.ui.panes.prompt_workbench import PromptWorkbench
from src.ui.panes.workspace_rail import WorkspaceRail

SASH_OPTS = dict(
    sashwidth=6,
    sashrelief="raised",
    sashpad=1,
)


class ControlPane(tk.Frame):
    """Main workstation shell with left rail, center interaction area, and right workbench."""

    def __init__(
        self,
        parent,
        on_submit=None,
        on_stop=None,
        on_model_select=None,
        on_model_refresh=None,
        on_faux_click=None,
        on_session_new=None,
        on_session_select=None,
        on_session_rename=None,
        on_session_delete=None,
        on_session_branch=None,
        on_session_policy=None,
        on_sandbox_pick=None,
        on_import=None,
        on_edit_project_brief=None,
        on_edit_prompt_overrides=None,
        on_cli_command=None,
        on_docker_toggle=None,
        on_docker_build=None,
        on_docker_start=None,
        on_docker_stop=None,
        on_docker_destroy=None,
        on_vcs_snapshot=None,
        on_reload_tools=None,
        on_reload_prompt_docs=None,
        on_prompt_source_saved=None,
        on_set_tool_round_limit=None,
        on_bag_refresh=None,
        initial_tool_round_limit: int = 12,
        **kw,
    ):
        kw.setdefault("bg", T.BG_DARK)
        super().__init__(parent, **kw)
        self._layout_initialized = False
        self._layout_apply_pending = False

        self._main_work_area = tk.PanedWindow(
            self,
            orient="horizontal",
            bg=T.BORDER,
            bd=0,
            **SASH_OPTS,
        )
        self._main_work_area.pack(fill="both", expand=True)

        self.workspace_rail = WorkspaceRail(
            self._main_work_area,
            on_model_select=on_model_select,
            on_model_refresh=on_model_refresh,
            on_session_new=on_session_new,
            on_session_select=on_session_select,
            on_session_rename=on_session_rename,
            on_session_delete=on_session_delete,
            on_session_branch=on_session_branch,
            on_session_policy=on_session_policy,
            on_sandbox_pick=on_sandbox_pick,
            on_import=on_import,
            on_edit_project_brief=on_edit_project_brief,
            on_edit_prompt_overrides=on_edit_prompt_overrides,
            on_docker_toggle=on_docker_toggle,
            on_docker_build=on_docker_build,
            on_docker_start=on_docker_start,
            on_docker_stop=on_docker_stop,
            on_docker_destroy=on_docker_destroy,
            on_vcs_snapshot=on_vcs_snapshot,
        )
        self.interaction_shell = InteractionShell(
            self._main_work_area,
            on_submit=on_submit,
            on_stop=on_stop,
            on_faux_click=on_faux_click,
            on_cli_command=on_cli_command,
        )
        self.prompt_workbench = PromptWorkbench(
            self._main_work_area,
            on_reload_tools=on_reload_tools,
            on_reload_prompt_docs=on_reload_prompt_docs,
            on_prompt_source_saved=on_prompt_source_saved,
            on_set_tool_round_limit=on_set_tool_round_limit,
            on_bag_refresh=on_bag_refresh,
            initial_tool_round_limit=initial_tool_round_limit,
        )

        self._main_work_area.add(self.workspace_rail, stretch="never", width=300)
        self._main_work_area.add(self.interaction_shell, stretch="always", width=780)
        self._main_work_area.add(self.prompt_workbench, stretch="never", width=360)
        self._main_work_area.paneconfigure(self.workspace_rail, minsize=260)
        self._main_work_area.paneconfigure(self.interaction_shell, minsize=520)
        self._main_work_area.paneconfigure(self.prompt_workbench, minsize=300)

        # Back-compat aliases for callers outside the UI domain.
        self.model_picker = self.workspace_rail.model_picker
        self.session_panel = self.workspace_rail.session_panel
        self.docker_panel = self.workspace_rail.docker_panel
        self.vcs_panel = self.workspace_rail.vcs_panel
        self.resources = self.workspace_rail.resources
        self.chat_pane = self.interaction_shell.chat_pane
        self.input_pane = self.interaction_shell.input_pane
        self.faux_buttons = self.interaction_shell.faux_buttons
        self.cli_pane = self.interaction_shell.cli_pane
        self.prompt_preview = self.prompt_workbench.prompt_preview
        self.response_preview = self.prompt_workbench.response_preview
        self.system_prompt_preview = self.prompt_workbench.system_prompt_preview
        self.inspect_prompt_preview = self.prompt_workbench.inspect_prompt_preview
        self.inspect_response_preview = self.prompt_workbench.inspect_response_preview
        self.inspect_sources_preview = self.prompt_workbench.inspect_sources_preview

        self.bind("<Configure>", self._on_shell_configure)
        self.after(120, self._apply_default_layout)
        self.after(320, self._apply_default_layout)

    def _apply_default_layout(self) -> None:
        self._layout_apply_pending = False
        total_width = self._main_work_area.winfo_width()
        if total_width >= 1080:
            left_width = max(260, int(total_width * 0.20))
            right_width = max(300, int(total_width * 0.25))
            sash_0 = left_width
            sash_1 = max(sash_0 + 520, total_width - right_width)
            sash_1 = min(sash_1, total_width - 300)
            self._main_work_area.sash_place(0, sash_0, 0)
            self._main_work_area.sash_place(1, sash_1, 0)
            self._layout_initialized = True

    def _on_shell_configure(self, _event=None) -> None:
        if not self._layout_initialized:
            self._schedule_default_layout()

    def _schedule_default_layout(self) -> None:
        if self._layout_apply_pending:
            return
        self._layout_apply_pending = True
        self.after_idle(self._apply_default_layout)

    def set_project_name(self, name: str) -> None:
        self.workspace_rail.set_project_name(name)

    def set_model_name(self, name: str) -> None:
        self.workspace_rail.set_model_name(name)

    def set_session_title(self, title: str) -> None:
        self.workspace_rail.set_session_title(title)

    def set_tool_round_limit(self, value: int) -> None:
        self.prompt_workbench.set_tool_round_limit(value)

    def set_tool_count(self, count: int, tool_names: list[str] | None = None) -> None:
        self.prompt_workbench.set_tool_count(count, tool_names)

    def set_prompt_inspector(self, prompt_text: str, sources_text: str) -> None:
        self.prompt_workbench.set_prompt_inspector(prompt_text, sources_text)

    def set_last_prompt(self, text: str) -> None:
        self.prompt_workbench.set_last_prompt(text)

    def set_last_response(self, text: str) -> None:
        self.prompt_workbench.set_last_response(text)

    def get_loop_mode(self) -> str | None:
        return self.interaction_shell.get_loop_mode()

    def set_loop_mode(self, mode: str | None) -> str:
        return self.interaction_shell.set_loop_mode(mode)

    def set_stop_enabled(self, enabled: bool) -> None:
        self.interaction_shell.set_stop_enabled(enabled)

    def set_stop_requested(self, requested: bool) -> None:
        self.interaction_shell.set_stop_requested(requested)

    def set_evidence_bag_display(self, content: str, *, enabled: bool = True) -> None:
        self.prompt_workbench.set_evidence_bag_display(content, enabled=enabled)

    def cycle_workspace_tabs(self) -> None:
        self.workspace_rail.cycle_tabs()

    def get_context_menu_targets(self) -> list[tk.Text]:
        return self.prompt_workbench.context_menu_targets()

    @property
    def current_project_name(self) -> str:
        return self.workspace_rail.current_project_name

    @property
    def current_model_name(self) -> str:
        return self.workspace_rail.current_model_name

    @property
    def current_session_title(self) -> str:
        return self.workspace_rail.current_session_title

    @property
    def last_prompt_text(self) -> str:
        return self.prompt_workbench.last_prompt_text

    @property
    def last_response_text(self) -> str:
        return self.prompt_workbench.last_response_text
