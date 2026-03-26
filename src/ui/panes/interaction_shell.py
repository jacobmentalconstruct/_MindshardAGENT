"""Center interaction shell: chat plus compose/CLI dock."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from src.ui import theme as T
from src.ui.panes.chat_pane import ChatPane
from src.ui.panes.cli_pane import CLIPane
from src.ui.panes.input_pane import InputPane
from src.ui.widgets.faux_button_panel import FauxButtonPanel

SASH_OPTS = dict(
    sashwidth=6,
    sashrelief="raised",
    sashpad=1,
)


class InteractionShell(tk.Frame):
    """Owns the center chat area and the compose/CLI bottom dock."""

    def __init__(self, parent, *, on_submit=None, on_stop=None, on_faux_click=None, on_cli_command=None, **kw):
        kw.setdefault("bg", T.BG_DARK)
        super().__init__(parent, **kw)
        self._layout_initialized = False
        self._layout_apply_pending = False

        tk.Label(
            self,
            text="INTERACTION",
            font=T.FONT_HEADING,
            fg=T.CYAN,
            bg=T.BG_DARK,
        ).pack(anchor="w", padx=10, pady=(8, 4))

        self._center_split = tk.PanedWindow(
            self,
            orient="vertical",
            bg=T.BORDER,
            bd=0,
            **SASH_OPTS,
        )
        self._center_split.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        self.chat_pane = ChatPane(self._center_split)
        self._center_split.add(self.chat_pane, stretch="always")
        self._center_split.paneconfigure(self.chat_pane, minsize=260)

        bottom_dock_frame = tk.Frame(self._center_split, bg=T.BG_DARK)
        self._center_split.add(bottom_dock_frame, stretch="never", height=250)
        self._center_split.paneconfigure(bottom_dock_frame, minsize=210)

        self._bottom_dock = ttk.Notebook(bottom_dock_frame)
        self._bottom_dock.pack(fill="both", expand=True)

        compose_tab = tk.Frame(self._bottom_dock, bg=T.BG_DARK)
        cli_tab = tk.Frame(self._bottom_dock, bg=T.BG_DARK)
        self._bottom_dock.add(compose_tab, text="Compose")
        self._bottom_dock.add(cli_tab, text="Sandbox CLI")

        compose_status_row = tk.Frame(compose_tab, bg=T.BG_DARK)
        compose_status_row.pack(fill="x", padx=8, pady=(6, 0))
        self._compose_status = tk.Label(
            compose_status_row,
            text="Compose prompt and submit from here.",
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_DARK,
        )
        self._compose_status.pack(side="left")

        tk.Label(
            compose_status_row, text="Mode:",
            font=T.FONT_SMALL, fg=T.TEXT_DIM, bg=T.BG_DARK,
        ).pack(side="right", padx=(0, 2))
        self._loop_mode_var = tk.StringVar(value="auto")
        loop_combo = ttk.Combobox(
            compose_status_row,
            textvariable=self._loop_mode_var,
            values=["auto", "tool_agent", "direct_chat", "planner_only", "thought_chain", "recovery_agent", "review_judge"],
            width=14,
            state="readonly",
        )
        loop_combo.pack(side="right", padx=(0, 4))

        self.input_pane = InputPane(compose_tab, on_submit=on_submit, on_stop=on_stop)
        self.input_pane.pack(fill="both", expand=True, padx=4, pady=(2, 0))

        self.faux_buttons = FauxButtonPanel(compose_tab, on_click=on_faux_click)
        self.faux_buttons.pack(fill="x", padx=4, pady=(0, 4))

        self.cli_pane = CLIPane(cli_tab, on_command=on_cli_command)
        self.cli_pane.pack(fill="both", expand=True, padx=4, pady=4)

        self.bind("<Configure>", self._on_shell_configure)
        self.after(120, self._apply_default_layout)
        self.after(320, self._apply_default_layout)

    def _apply_default_layout(self) -> None:
        self._layout_apply_pending = False
        center_height = self._center_split.winfo_height()
        if center_height >= 420:
            self._center_split.sash_place(0, 0, int(center_height * 0.72))
            self._layout_initialized = True

    def _on_shell_configure(self, _event=None) -> None:
        if not self._layout_initialized:
            self._schedule_default_layout()

    def _schedule_default_layout(self) -> None:
        if self._layout_apply_pending:
            return
        self._layout_apply_pending = True
        self.after_idle(self._apply_default_layout)

    def get_loop_mode(self) -> str | None:
        val = self._loop_mode_var.get()
        return val if val and val != "auto" else None

    def set_loop_mode(self, mode: str | None) -> str:
        allowed = {
            "auto",
            "tool_agent",
            "direct_chat",
            "planner_only",
            "thought_chain",
            "recovery_agent",
            "review_judge",
        }
        value = (mode or "auto").strip() or "auto"
        if value not in allowed:
            raise ValueError(f"Unsupported loop mode: {value}")
        self._loop_mode_var.set(value)
        return value

    def set_stop_enabled(self, enabled: bool) -> None:
        self.input_pane.set_stop_enabled(enabled)

    def set_stop_requested(self, requested: bool) -> None:
        self.input_pane.set_stop_requested(requested)
