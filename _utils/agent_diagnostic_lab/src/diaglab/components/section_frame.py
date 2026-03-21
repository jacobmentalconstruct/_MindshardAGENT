from __future__ import annotations

import tkinter as tk

from src.ui import theme


class SectionFrame(tk.Frame):
    def __init__(self, master, title: str, **kwargs):
        super().__init__(master, bg=theme.BG_DARK, highlightbackground=theme.BORDER, highlightthickness=1, **kwargs)
        self.columnconfigure(0, weight=1)
        title_label = tk.Label(
            self,
            text=title,
            bg=theme.BG_DARK,
            fg=theme.CYAN,
            font=theme.FONT_HEADING,
            anchor="w",
        )
        title_label.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))
        self.body = tk.Frame(self, bg=theme.BG_MID)
        self.body.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.rowconfigure(1, weight=1)
