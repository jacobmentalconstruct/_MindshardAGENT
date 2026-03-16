"""Inline metadata tag row for display beneath messages."""

import tkinter as tk
from src.ui import theme as T


class MetadataTagRow(tk.Frame):
    """Horizontal row of small key:value metadata tags."""

    def __init__(self, parent, tags: dict[str, str] | None = None, **kw):
        kw.setdefault("bg", T.BG_MID)
        super().__init__(parent, **kw)
        if tags:
            self.set_tags(tags)

    def set_tags(self, tags: dict[str, str]) -> None:
        for child in self.winfo_children():
            child.destroy()
        for key, val in tags.items():
            lbl = tk.Label(self, text=f"{key}: {val}", font=T.FONT_SMALL,
                           fg=T.TEXT_DIM, bg=self.cget("bg"), padx=6)
            lbl.pack(side="left")
