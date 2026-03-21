from __future__ import annotations

import tkinter as tk

from src.ui import theme


class MetricCard(tk.Frame):
    def __init__(self, master, title: str, value: str = "--", accent: str | None = None, **kwargs):
        super().__init__(master, bg=theme.BG_MID, highlightbackground=theme.BORDER, highlightthickness=1, **kwargs)
        self._title = tk.Label(self, text=title, bg=theme.BG_MID, fg=theme.TEXT_DIM, font=theme.FONT_SMALL)
        self._title.pack(anchor="w", padx=10, pady=(8, 2))
        self._value = tk.Label(
            self,
            text=value,
            bg=theme.BG_MID,
            fg=accent or theme.TEXT_BRIGHT,
            font=theme.FONT_TITLE,
            anchor="w",
        )
        self._value.pack(anchor="w", padx=10, pady=(0, 8))

    def set_value(self, value: str, accent: str | None = None) -> None:
        self._value.configure(text=value)
        if accent:
            self._value.configure(fg=accent)
