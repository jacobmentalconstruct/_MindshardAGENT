"""Reserved button panel for future actions.

Buttons are styled but mostly inert in v1. They provide visual
structure and respond to hover for feel.
"""

import tkinter as tk
from src.ui import theme as T


_PLACEHOLDER_LABELS = ["Attach Self", "Sync to Source", "Add Ref", "Add Parts", "Detach", "Clear"]


class FauxButtonPanel(tk.Frame):
    """Grid of reserved action buttons with cyberpunk styling."""

    def __init__(self, parent, on_click=None, **kw):
        kw.setdefault("bg", T.BG_DARK)
        super().__init__(parent, **kw)
        self._on_click = on_click

        header = tk.Label(self, text="ACTIONS", font=T.FONT_SMALL,
                          fg=T.TEXT_DIM, bg=T.BG_DARK)
        header.pack(anchor="w", padx=8, pady=(6, 4))

        grid = tk.Frame(self, bg=T.BG_DARK)
        grid.pack(fill="x", padx=8, pady=(0, 8))

        for i, label in enumerate(_PLACEHOLDER_LABELS):
            btn = tk.Button(
                grid, text=label, font=T.FONT_BUTTON,
                fg=T.CYAN, bg=T.BG_LIGHT, activebackground=T.BG_SURFACE,
                activeforeground=T.GREEN, relief="flat", bd=0,
                width=8, height=1, cursor="hand2",
                command=lambda l=label: self._handle_click(l),
            )
            row, col = divmod(i, 3)
            btn.grid(row=row, column=col, padx=3, pady=3, sticky="ew")
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg=T.BG_SURFACE, fg=T.GREEN))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg=T.BG_LIGHT, fg=T.CYAN))

        for c in range(3):
            grid.columnconfigure(c, weight=1)

    def _handle_click(self, label: str) -> None:
        if self._on_click:
            self._on_click(label)
