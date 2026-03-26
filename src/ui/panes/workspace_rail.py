"""Left-side workspace/session/sandbox/git rail."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from src.ui import theme as T
from src.ui.widgets.docker_panel import DockerPanel
from src.ui.widgets.model_picker import ModelPicker
from src.ui.widgets.prompt_widgets import ResourceBlock, SummaryCard
from src.ui.widgets.session_panel import SessionPanel
from src.ui.widgets.vcs_panel import VCSPanel


def _noop():
    """Sentinel used in place of anonymous lambda no-ops."""


class WorkspaceRail(tk.Frame):
    """Owns the left workspace/session/sandbox/git shell."""

    def __init__(
        self,
        parent,
        *,
        on_model_select=None,
        on_model_refresh=None,
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
        on_docker_toggle=None,
        on_docker_build=None,
        on_docker_start=None,
        on_docker_stop=None,
        on_docker_destroy=None,
        on_vcs_snapshot=None,
        **kw,
    ):
        kw.setdefault("bg", T.BG_DARK)
        super().__init__(parent, **kw)

        self._current_model_name = "(none)"
        self._current_session_title = "New Session"
        self._current_project_name = ""

        tk.Label(
            self,
            text="WORKSPACE",
            font=T.FONT_HEADING,
            fg=T.CYAN,
            bg=T.BG_DARK,
        ).pack(anchor="w", padx=10, pady=(8, 4))

        self._left_notebook = ttk.Notebook(self)
        self._left_notebook.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        session_tab = tk.Frame(self._left_notebook, bg=T.BG_DARK)
        sandbox_tab = tk.Frame(self._left_notebook, bg=T.BG_DARK)
        git_tab = tk.Frame(self._left_notebook, bg=T.BG_DARK)
        self._left_notebook.add(session_tab, text="Session")
        self._left_notebook.add(sandbox_tab, text="Sandbox")
        self._left_notebook.add(git_tab, text="Git")

        self._session_summary_card = SummaryCard(session_tab, title="CURRENT SESSION", accent=T.GREEN)
        self._session_summary_card.pack(fill="x", padx=4, pady=(4, 2))

        self.model_picker = ModelPicker(
            session_tab,
            on_select=on_model_select,
            on_refresh=on_model_refresh,
        )
        self.model_picker.pack(fill="x", padx=4, pady=(4, 2))

        tk.Frame(session_tab, bg=T.BORDER, height=1).pack(fill="x", padx=8, pady=4)

        self.session_panel = SessionPanel(
            session_tab,
            on_new=on_session_new,
            on_select=on_session_select,
            on_rename=on_session_rename,
            on_delete=on_session_delete,
            on_branch=on_session_branch,
            on_policy=on_session_policy,
        )
        self.session_panel.pack(fill="both", expand=True, padx=4, pady=2)

        self.docker_panel = DockerPanel(
            sandbox_tab,
            on_toggle=on_docker_toggle,
            on_build=on_docker_build,
            on_start=on_docker_start,
            on_stop=on_docker_stop,
            on_destroy=on_docker_destroy,
        )
        self.docker_panel.pack(fill="x", padx=4, pady=(4, 2))

        self._sandbox_summary_card = SummaryCard(
            sandbox_tab,
            title="PROJECT STATUS",
            accent=T.AMBER,
        )
        self._sandbox_summary_card.pack(fill="x", padx=4, pady=(0, 2))

        tk.Frame(sandbox_tab, bg=T.BORDER, height=1).pack(fill="x", padx=8, pady=4)

        self.resources = ResourceBlock(sandbox_tab)
        self.resources.pack(fill="x", padx=4, pady=2)

        tk.Frame(sandbox_tab, bg=T.BORDER, height=1).pack(fill="x", padx=8, pady=4)

        proj_header = tk.Label(
            sandbox_tab,
            text="PROJECT",
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_DARK,
        )
        proj_header.pack(anchor="w", padx=12, pady=(4, 2))

        proj_name_frame = tk.Frame(sandbox_tab, bg=T.BG_MID, bd=0)
        proj_name_frame.pack(fill="x", padx=8, pady=(0, 4))

        tk.Label(proj_name_frame, text="◆", font=T.FONT_SMALL, fg=T.CYAN, bg=T.BG_MID).pack(
            side="left",
            padx=(8, 4),
            pady=4,
        )
        self._project_name_label = tk.Label(
            proj_name_frame,
            text="No project set",
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_MID,
            anchor="w",
        )
        self._project_name_label.pack(side="left", fill="x", expand=True, pady=4)

        btn_row = tk.Frame(sandbox_tab, bg=T.BG_DARK)
        btn_row.pack(fill="x", padx=8, pady=(0, 4))

        open_btn = self._make_action_button(
            btn_row,
            text="OPEN PROJECT",
            fg=T.AMBER,
            command=on_sandbox_pick if on_sandbox_pick else _noop,
        )
        open_btn.pack(side="left", fill="x", expand=True, padx=(0, 2))

        import_btn = self._make_action_button(
            btn_row,
            text="ADD REF",
            fg=T.PURPLE,
            command=on_import if on_import else _noop,
        )
        import_btn.pack(side="left", fill="x", expand=True, padx=(2, 0))

        edit_btn_row = tk.Frame(sandbox_tab, bg=T.BG_DARK)
        edit_btn_row.pack(fill="x", padx=8, pady=(0, 4))

        edit_brief_btn = self._make_action_button(
            edit_btn_row,
            text="EDIT BRIEF",
            fg=T.CYAN,
            active_fg=T.GREEN,
            command=on_edit_project_brief if on_edit_project_brief else _noop,
        )
        edit_brief_btn.pack(side="left", fill="x", expand=True, padx=(0, 2))

        edit_prompts_btn = self._make_action_button(
            edit_btn_row,
            text="EDIT PROMPTS",
            fg=T.AMBER,
            command=on_edit_prompt_overrides if on_edit_prompt_overrides else _noop,
        )
        edit_prompts_btn.pack(side="left", fill="x", expand=True, padx=(2, 0))

        self.vcs_panel = VCSPanel(git_tab, on_snapshot=on_vcs_snapshot)
        self.vcs_panel.pack(fill="both", expand=True)

        self._update_workspace_summaries()

    def _make_action_button(self, parent, *, text: str, fg: str, command, active_fg: str | None = None) -> tk.Button:
        btn = tk.Button(
            parent,
            text=text,
            font=T.FONT_BUTTON,
            fg=fg,
            bg=T.BG_LIGHT,
            activebackground=T.BG_SURFACE,
            activeforeground=active_fg or fg,
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=command,
        )
        btn.bind("<Enter>", lambda _e, b=btn: b.config(bg=T.BG_SURFACE))
        btn.bind("<Leave>", lambda _e, b=btn: b.config(bg=T.BG_LIGHT))
        return btn

    def _update_workspace_summaries(self) -> None:
        self._session_summary_card.set_body(
            f"Session: {self._current_session_title}\nModel: {self._current_model_name}"
        )
        project_text = self._current_project_name or "No project attached"
        self._sandbox_summary_card.set_body(
            f"{project_text}\nUse Sandbox for project state and prompt overrides."
        )

    def set_project_name(self, name: str) -> None:
        self._current_project_name = name or ""
        self._project_name_label.config(
            text=name or "No project set",
            fg=T.TEXT_PRIMARY if name else T.TEXT_DIM,
        )
        self._update_workspace_summaries()

    def set_model_name(self, name: str) -> None:
        self._current_model_name = name or "(none)"
        self._update_workspace_summaries()

    def set_session_title(self, title: str) -> None:
        self._current_session_title = title or "New Session"
        self._update_workspace_summaries()

    def cycle_tabs(self) -> None:
        tabs = self._left_notebook.tabs()
        if not tabs:
            return
        current = self._left_notebook.select()
        try:
            index = tabs.index(current)
        except ValueError:
            index = -1
        self._left_notebook.select(tabs[(index + 1) % len(tabs)])

    @property
    def current_project_name(self) -> str:
        return self._current_project_name

    @property
    def current_model_name(self) -> str:
        return self._current_model_name

    @property
    def current_session_title(self) -> str:
        return self._current_session_title
