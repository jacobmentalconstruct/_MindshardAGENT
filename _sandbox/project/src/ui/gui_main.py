"""Main GUI window — composes the Tkinter shell layout.

Layout:
  ┌─────────────────────────────────┬──────────────────┐
  │  Title bar / status strip       │                  │
  ├─────────────────────────────────┤  Right Column    │
  │                                 │  - Model picker  │
  │  Chat transcript (scrollable)   │  - Resources     │
  │                                 │  - Prompt preview│
  │                                 │  - Input box     │
  ├─────────────────┬───────────────┤  - Faux buttons  │
  │  Activity log   │  CLI panel    │                  │
  └─────────────────┴───────────────┴──────────────────┘
"""

import tkinter as tk
from tkinter import filedialog

from src.ui import theme as T
from src.ui.ui_state import UIState
from src.ui.panes.chat_pane import ChatPane
from src.ui.panes.activity_log_pane import ActivityLogPane
from src.ui.panes.cli_pane import CLIPane
from src.ui.panes.control_pane import ControlPane
from src.core.runtime.activity_stream import ActivityStream, ActivityEntry
from src.core.runtime.runtime_logger import get_logger

log = get_logger("gui")


class MainWindow:
    """Top-level application window."""

    def __init__(self, root: tk.Tk, ui_state: UIState, activity: ActivityStream,
                 on_submit=None, on_model_select=None, on_model_refresh=None,
                 on_close=None, on_cli_command=None,
                 on_session_new=None, on_session_select=None,
                 on_session_rename=None, on_session_delete=None,
                 on_session_branch=None, on_sandbox_pick=None):
        self.root = root
        self.ui_state = ui_state
        self.activity = activity
        self._on_close = on_close

        # ── Window setup ──────────────────────────────────
        root.title("AgenticTOOLBOX — Sandboxed Agent Shell")
        root.configure(bg=T.BG_DARK)
        root.minsize(1000, 650)
        root.protocol("WM_DELETE_WINDOW", self._handle_close)

        # ── Style the ttk combobox to match theme ─────────
        style = tk.ttk.Style() if hasattr(tk, "ttk") else None
        try:
            from tkinter import ttk
            style = ttk.Style()
            style.theme_use("clam")
            style.configure("TCombobox",
                            fieldbackground=T.BG_LIGHT,
                            background=T.BG_LIGHT,
                            foreground=T.TEXT_PRIMARY,
                            selectbackground=T.BG_SURFACE,
                            selectforeground=T.CYAN)
        except Exception:
            pass

        # ── Title bar ─────────────────────────────────────
        self._title_bar = tk.Frame(root, bg=T.BG_MID, height=40)
        self._title_bar.pack(fill="x")
        self._title_bar.pack_propagate(False)

        tk.Label(self._title_bar, text="◆ AGENTIC TOOLBOX",
                 font=T.FONT_TITLE, fg=T.CYAN, bg=T.BG_MID).pack(side="left", padx=12)

        self._model_label = tk.Label(self._title_bar, text="model: (none)",
                                      font=T.FONT_SMALL, fg=T.PURPLE, bg=T.BG_MID)
        self._model_label.pack(side="left", padx=20)

        self._session_label = tk.Label(self._title_bar, text="session: New Session",
                                        font=T.FONT_SMALL, fg=T.TEXT_DIM, bg=T.BG_MID)
        self._session_label.pack(side="left", padx=12)

        self._sandbox_label = tk.Label(self._title_bar, text="sandbox: (not set)",
                                        font=T.FONT_SMALL, fg=T.TEXT_DIM, bg=T.BG_MID)
        self._sandbox_label.pack(side="right", padx=12)

        self._save_indicator = tk.Label(self._title_bar, text="●",
                                         font=T.FONT_SMALL, fg=T.GREEN, bg=T.BG_MID)
        self._save_indicator.pack(side="right", padx=6)

        # ── Glow line under title ─────────────────────────
        tk.Frame(root, bg=T.CYAN, height=1).pack(fill="x")

        # ── Main body ─────────────────────────────────────
        body = tk.PanedWindow(root, orient="horizontal",
                               bg=T.BG_DARK, sashwidth=3, sashrelief="flat",
                               bd=0)
        body.pack(fill="both", expand=True)

        # Left column: chat + bottom panels (activity log + CLI)
        left_col = tk.PanedWindow(body, orient="vertical",
                                   bg=T.BG_DARK, sashwidth=3, sashrelief="flat",
                                   bd=0)

        self.chat_pane = ChatPane(left_col)
        left_col.add(self.chat_pane, stretch="always")

        # Bottom panel: activity log side-by-side with CLI
        bottom_panels = tk.PanedWindow(left_col, orient="horizontal",
                                        bg=T.BG_DARK, sashwidth=3, sashrelief="flat",
                                        bd=0)

        self.activity_pane = ActivityLogPane(bottom_panels)
        bottom_panels.add(self.activity_pane, stretch="always")

        self.cli_pane = CLIPane(bottom_panels, on_command=on_cli_command)
        bottom_panels.add(self.cli_pane, stretch="always")

        left_col.add(bottom_panels, stretch="never", height=220)

        body.add(left_col, stretch="always", width=800)

        # Right column: controls
        self.control_pane = ControlPane(
            body,
            on_submit=on_submit,
            on_model_select=on_model_select,
            on_model_refresh=on_model_refresh,
            on_faux_click=self._handle_faux_click,
            on_session_new=on_session_new,
            on_session_select=on_session_select,
            on_session_rename=on_session_rename,
            on_session_delete=on_session_delete,
            on_session_branch=on_session_branch,
            on_sandbox_pick=on_sandbox_pick,
        )
        body.add(self.control_pane, stretch="never", width=380)

        # ── Bottom status strip ───────────────────────────
        tk.Frame(root, bg=T.BORDER, height=1).pack(fill="x")
        self._status_bar = tk.Frame(root, bg=T.BG_MID, height=24)
        self._status_bar.pack(fill="x")
        self._status_bar.pack_propagate(False)
        self._status_text = tk.Label(self._status_bar, text="Ready",
                                      font=T.FONT_SMALL, fg=T.TEXT_DIM, bg=T.BG_MID)
        self._status_text.pack(side="left", padx=10)

        # ── Connect activity stream to log pane ───────────
        activity.subscribe(self._on_activity)

        log.info("GUI initialized")

    def _on_activity(self, entry: ActivityEntry) -> None:
        try:
            self.activity_pane.append_entry(entry)
        except tk.TclError:
            pass  # widget may be destroyed during shutdown

    def _handle_close(self) -> None:
        if self._on_close:
            self._on_close()
        self.root.destroy()

    def _handle_faux_click(self, label: str) -> None:
        self.activity.info("ui", f"Button '{label}' clicked (reserved)")

    def set_model(self, name: str) -> None:
        self._model_label.config(text=f"model: {name}")

    def set_session_title(self, title: str) -> None:
        self._session_label.config(text=f"session: {title}")

    def set_sandbox_path(self, path: str) -> None:
        short = path if len(path) < 40 else "..." + path[-37:]
        self._sandbox_label.config(text=f"sandbox: {short}")

    def set_save_dirty(self, dirty: bool) -> None:
        color = T.AMBER if dirty else T.GREEN
        self._save_indicator.config(fg=color)

    def set_status(self, text: str) -> None:
        self._status_text.config(text=text)
