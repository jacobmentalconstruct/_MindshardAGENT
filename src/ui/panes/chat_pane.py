"""Chat transcript pane — scrollable message history.

Displays user, assistant, tool, and system messages as styled cards.
Occupies the upper-left region of the main window.
"""

import tkinter as tk
from src.ui import theme as T
from src.ui.widgets.chat_message_card import ChatMessageCard


class ChatPane(tk.Frame):
    """Scrollable chat message transcript."""

    def __init__(self, parent, **kw):
        kw.setdefault("bg", T.BG_DARK)
        super().__init__(parent, **kw)

        # Header
        header = tk.Frame(self, bg=T.BG_DARK)
        header.pack(fill="x")
        tk.Label(header, text="CHAT", font=T.FONT_HEADING,
                 fg=T.CYAN, bg=T.BG_DARK).pack(side="left", padx=10, pady=(8, 4))

        # Scrollable canvas
        container = tk.Frame(self, bg=T.BG_DARK)
        container.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(container, bg=T.BG_DARK, highlightthickness=0, bd=0)
        self._scrollbar = tk.Scrollbar(container, orient="vertical",
                                        command=self._canvas.yview,
                                        bg=T.SCROLLBAR_BG, troughcolor=T.SCROLLBAR_BG,
                                        activebackground=T.SCROLLBAR_FG)
        self._inner = tk.Frame(self._canvas, bg=T.BG_DARK)

        self._inner.bind("<Configure>",
                         lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))

        self._window_id = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        # Resize inner frame width to match canvas
        self._canvas.bind("<Configure>", self._on_canvas_resize)

        # Mouse wheel scrolling
        self._canvas.bind_all("<MouseWheel>",
                              lambda e: self._canvas.yview_scroll(-1 * (e.delta // 120), "units"))

    def _on_canvas_resize(self, event) -> None:
        self._canvas.itemconfig(self._window_id, width=event.width)

    def add_message(self, role: str, content: str, metadata: dict | None = None) -> None:
        card = ChatMessageCard(self._inner, role=role, content=content, metadata=metadata)
        card.pack(fill="x", padx=6, pady=3)
        self._canvas.update_idletasks()
        self._canvas.yview_moveto(1.0)

    def clear(self) -> None:
        for child in self._inner.winfo_children():
            child.destroy()
