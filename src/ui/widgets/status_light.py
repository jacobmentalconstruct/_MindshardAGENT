"""Small colored status indicator dot."""

import tkinter as tk
from src.ui import theme as T


class StatusLight(tk.Canvas):
    """A small circular status indicator."""

    def __init__(self, parent, size: int = 12, color: str = T.TEXT_DIM, **kw):
        kw.setdefault("width", size + 4)
        kw.setdefault("height", size + 4)
        kw.setdefault("bg", T.BG_MID)
        kw.setdefault("highlightthickness", 0)
        super().__init__(parent, **kw)
        self._size = size
        self._oval = self.create_oval(2, 2, size + 2, size + 2, fill=color, outline="")

    def set_color(self, color: str) -> None:
        self.itemconfig(self._oval, fill=color)
