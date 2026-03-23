"""Main GUI window for the refactored workstation shell."""

import threading
import tkinter as tk
from tkinter import ttk

from src.core.runtime.activity_stream import ActivityEntry, ActivityStream
from src.core.runtime.runtime_logger import get_logger
from src.ui import theme as T
from src.ui.panes.activity_log_pane import ActivityLogPane
from src.ui.panes.control_pane import ControlPane
from src.ui.ui_state import UIState

log = get_logger("gui")

SASH_OPTS = dict(
    sashwidth=6,
    sashrelief="raised",
    sashpad=1,
)


class MainWindow:
    """Top-level application window."""

    def __init__(
        self,
        root: tk.Tk,
        ui_state: UIState,
        activity: ActivityStream,
        on_submit=None,
        on_model_select=None,
        on_model_refresh=None,
        on_close=None,
        on_cli_command=None,
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
        on_faux_click=None,
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
        on_open_settings=None,
        initial_tool_round_limit: int = 12,
        dpi_scale: float = 1.0,
    ):
        self.root = root
        self.ui_state = ui_state
        self.activity = activity
        self._on_close = on_close
        self._on_open_settings = on_open_settings
        self._vertical_layout_initialized = False
        self._layout_apply_pending = False
        self._closed = False

        root.title("MindshardAGENT — Sandboxed Agent Shell")
        root.configure(bg=T.BG_DARK)
        root.minsize(int(1180 * dpi_scale), int(720 * dpi_scale))
        root.protocol("WM_DELETE_WINDOW", self._handle_close)

        self._configure_ttk()

        self._title_bar = tk.Frame(root, bg=T.BG_MID, height=40)
        self._title_bar.pack(fill="x")
        self._title_bar.pack_propagate(False)

        tk.Label(
            self._title_bar,
            text="◆ AGENTIC TOOLBOX",
            font=T.FONT_TITLE,
            fg=T.CYAN,
            bg=T.BG_MID,
        ).pack(side="left", padx=12)

        self._model_label = tk.Label(
            self._title_bar,
            text="model: (none)",
            font=T.FONT_SMALL,
            fg=T.PURPLE,
            bg=T.BG_MID,
        )
        self._model_label.pack(side="left", padx=20)

        self._session_label = tk.Label(
            self._title_bar,
            text="session: New Session",
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_MID,
        )
        self._session_label.pack(side="left", padx=12)

        self._working_label = tk.Label(
            self._title_bar,
            text="working: (not set)",
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_MID,
        )
        self._working_label.pack(side="right", padx=12)

        self._source_label = tk.Label(
            self._title_bar,
            text="source: (none)",
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_MID,
        )
        self._source_label.pack(side="right", padx=4)

        self._save_indicator = tk.Label(
            self._title_bar,
            text="●",
            font=T.FONT_SMALL,
            fg=T.GREEN,
            bg=T.BG_MID,
        )
        self._save_indicator.pack(side="right", padx=6)

        self._settings_btn = tk.Button(
            self._title_bar,
            text="⚙",
            font=T.FONT_BUTTON,
            fg=T.CYAN,
            bg=T.BG_MID,
            activebackground=T.BG_LIGHT,
            activeforeground=T.GREEN,
            relief="flat",
            bd=0,
            padx=8,
            pady=2,
            cursor="hand2",
            command=self._handle_open_settings,
        )
        self._settings_btn.pack(side="right", padx=(6, 8))
        self._settings_btn.bind("<Enter>", lambda _e: self._settings_btn.config(bg=T.BG_LIGHT))
        self._settings_btn.bind("<Leave>", lambda _e: self._settings_btn.config(bg=T.BG_MID))

        tk.Frame(root, bg=T.CYAN, height=1).pack(fill="x")

        self._main_vertical_split = tk.PanedWindow(
            root,
            orient="vertical",
            bg=T.BORDER,
            bd=0,
            **SASH_OPTS,
        )
        self._main_vertical_split.pack(fill="both", expand=True)

        self.control_pane = ControlPane(
            self._main_vertical_split,
            on_submit=on_submit,
            on_model_select=on_model_select,
            on_model_refresh=on_model_refresh,
            on_faux_click=on_faux_click or self._handle_faux_click,
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
            on_cli_command=on_cli_command,
            on_docker_toggle=on_docker_toggle,
            on_docker_build=on_docker_build,
            on_docker_start=on_docker_start,
            on_docker_stop=on_docker_stop,
            on_docker_destroy=on_docker_destroy,
            on_vcs_snapshot=on_vcs_snapshot,
            on_reload_tools=on_reload_tools,
            on_reload_prompt_docs=on_reload_prompt_docs,
            on_prompt_source_saved=on_prompt_source_saved,
            on_set_tool_round_limit=on_set_tool_round_limit,
            initial_tool_round_limit=initial_tool_round_limit,
        )
        self._main_vertical_split.add(self.control_pane, stretch="always")

        self.activity_pane = ActivityLogPane(self._main_vertical_split)
        self._main_vertical_split.add(self.activity_pane, stretch="never", height=180)

        tk.Frame(root, bg=T.BORDER, height=1).pack(fill="x")
        self._status_bar = tk.Frame(root, bg=T.BG_MID, height=24)
        self._status_bar.pack(fill="x")
        self._status_bar.pack_propagate(False)
        self._status_text = tk.Label(
            self._status_bar,
            text="Ready",
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_MID,
        )
        self._status_text.pack(side="left", padx=10)

        self.chat_pane = self.control_pane.chat_pane
        self.cli_pane = self.control_pane.cli_pane

        activity.subscribe(self._on_activity)
        self._main_vertical_split.bind("<Configure>", self._on_layout_configure)
        self._schedule_default_layout()
        root.after(120, self._apply_default_layout)
        root.after(320, self._apply_default_layout)
        log.info("GUI initialized")

    def _configure_ttk(self) -> None:
        try:
            style = ttk.Style()
            style.theme_use("clam")
            style.configure(
                "TNotebook",
                background=T.BG_DARK,
                borderwidth=0,
                tabmargins=[2, 2, 2, 0],
            )
            style.configure(
                "TNotebook.Tab",
                background=T.BG_MID,
                foreground=T.TEXT_DIM,
                padding=(10, 5),
                borderwidth=0,
            )
            style.map(
                "TNotebook.Tab",
                background=[("selected", T.BG_LIGHT)],
                foreground=[("selected", T.CYAN)],
            )
            style.configure(
                "TCombobox",
                fieldbackground=T.BG_LIGHT,
                background=T.BG_LIGHT,
                foreground=T.TEXT_PRIMARY,
                selectbackground=T.BG_SURFACE,
                selectforeground=T.CYAN,
            )
        except Exception:
            pass

    def _apply_default_layout(self) -> None:
        self._layout_apply_pending = False
        total_height = self._main_vertical_split.winfo_height()
        if total_height >= 520:
            self._main_vertical_split.sash_place(0, 0, int(total_height * 0.84))
            self._vertical_layout_initialized = True

    def _on_layout_configure(self, _event=None) -> None:
        if not self._vertical_layout_initialized:
            self._schedule_default_layout()

    def _schedule_default_layout(self) -> None:
        if self._closed or self._layout_apply_pending:
            return
        self._layout_apply_pending = True
        try:
            self.root.after_idle(self._apply_default_layout)
        except tk.TclError:
            self._layout_apply_pending = False

    def _on_activity(self, entry: ActivityEntry) -> None:
        if self._closed:
            return

        def _append() -> None:
            if self._closed:
                return
            try:
                self.activity_pane.append_entry(entry)
            except tk.TclError:
                pass

        try:
            if threading.current_thread() is threading.main_thread():
                _append()
            else:
                self.root.after(0, _append)
        except tk.TclError:
            pass

    def _handle_close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._on_close:
            self._on_close()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _handle_faux_click(self, label: str) -> None:
        self.activity.info("ui", f"Button '{label}' clicked (reserved)")

    def _handle_open_settings(self) -> None:
        if self._on_open_settings:
            self._on_open_settings()

    def set_model(self, name: str) -> None:
        self._model_label.config(text=f"model: {name}")
        self.control_pane.set_model_name(name)

    def set_session_title(self, title: str) -> None:
        self._session_label.config(text=f"session: {title}")
        self.control_pane.set_session_title(title)

    def set_project_paths(self, source_path: str, working_path: str) -> None:
        if working_path:
            short_w = working_path if len(working_path) <= 35 else "..." + working_path[-32:]
            if source_path:
                self._working_label.config(text=f"working: {short_w}")
            else:
                self._working_label.config(text=f"working: {short_w} (in-place)")
        else:
            self._working_label.config(text="working: (not set)")

        if source_path:
            short_s = source_path if len(source_path) <= 35 else "..." + source_path[-32:]
            self._source_label.config(text=f"source: {short_s}")
        else:
            self._source_label.config(text="source: (none)")

    def set_sandbox_path(self, path: str) -> None:
        self.set_project_paths("", path)

    def set_project_name(self, name: str) -> None:
        if name:
            self.root.title(f"MindshardAGENT — {name}")
        else:
            self.root.title("MindshardAGENT — Sandboxed Agent Shell")
        self.control_pane.set_project_name(name)

    def set_save_dirty(self, dirty: bool) -> None:
        self._save_indicator.config(fg=T.AMBER if dirty else T.GREEN)

    def set_status(self, text: str) -> None:
        self._status_text.config(text=text)
