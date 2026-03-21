from __future__ import annotations

import tkinter as tk
from tkinter import scrolledtext

from src.ui import theme


class LogPanel(tk.Frame):
    def __init__(self, master, **kwargs):
        super().__init__(master, bg=theme.BG_MID, **kwargs)
        self.text = scrolledtext.ScrolledText(
            self,
            wrap="word",
            bg=theme.BG_LIGHT,
            fg=theme.TEXT_PRIMARY,
            insertbackground=theme.CYAN,
            font=theme.FONT_BODY,
            relief="flat",
            borderwidth=0,
        )
        self.text.pack(fill="both", expand=True)

    def set_text(self, content: str) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.text.configure(state="disabled")
