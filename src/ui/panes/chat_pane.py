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

        # Mouse wheel scrolling — bind to canvas and inner frame only,
        # not bind_all which would steal scroll events from every other widget.
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._inner.bind("<MouseWheel>", self._on_mousewheel)

        # Active streaming card (set by begin_stream, cleared by end_stream)
        self._stream_card = None
        self._messages: list[dict[str, str]] = []
        self._stream_index: int | None = None

        # Auto-scroll state — True while streaming unless user scrolls away.
        # Restored to True automatically when user scrolls back to the bottom.
        self._auto_scroll: bool = True

        # Scrollbar drag also counts as manual scroll
        self._scrollbar.bind("<B1-ButtonRelease>", lambda e: self._sync_auto_scroll())

    def _on_canvas_resize(self, event) -> None:
        self._canvas.itemconfig(self._window_id, width=event.width)

    def _on_mousewheel(self, event) -> None:
        self._canvas.yview_scroll(-1 * (event.delta // 120), "units")
        self._sync_auto_scroll()

    def _sync_auto_scroll(self) -> None:
        """Re-enable auto-scroll when at the bottom; disable when scrolled away."""
        try:
            _, bottom = self._canvas.yview()
            self._auto_scroll = bottom >= 0.999
        except Exception:
            pass

    def add_message(self, role: str, content: str, metadata: dict | None = None) -> ChatMessageCard:
        card = ChatMessageCard(self._inner, role=role, content=content, metadata=metadata)
        card.pack(fill="x", padx=6, pady=3)
        # Propagate scroll to canvas for all child widgets in the card
        for widget in [card] + card.winfo_children():
            widget.bind("<MouseWheel>", self._on_mousewheel)
        self._messages.append({"role": role, "content": content})
        return card

    def scroll_to_bottom(self) -> None:
        """Flush layout and scroll to the latest message. Call once after bulk add_message."""
        self._canvas.update_idletasks()
        self._canvas.yview_moveto(1.0)

    def clear(self) -> None:
        for child in self._inner.winfo_children():
            child.destroy()
        self._stream_card = None
        self._stream_index = None
        self._messages.clear()

    def export_messages(self, limit: int = 0) -> list[dict[str, str]]:
        messages = list(self._messages)
        if limit and limit > 0:
            messages = messages[-limit:]
        return messages

    # ── Streaming protocol ────────────────────────────────────────────────────

    def begin_stream(self) -> None:
        """Add a placeholder assistant card and prepare for incremental updates.

        Owns: card creation, initial scroll, stream card reference.
        Callers use update_stream/end_stream — never touch _stream_card directly.
        """
        self._auto_scroll = True  # always chase bottom when a new stream starts
        self._stream_card = self.add_message("assistant", "Thinking...")
        self._stream_index = len(self._messages) - 1
        self.scroll_to_bottom()

    def update_stream(self, content: str) -> None:
        """Update the active streaming card with accumulated content.

        Auto-scrolls to the bottom on each token unless the user has manually
        scrolled away, in which case the position is left undisturbed.
        Scrolling back to the bottom re-engages auto-scroll automatically.
        """
        if self._stream_card is None:
            return
        try:
            self._stream_card.update_streaming_content(content)
            if self._stream_index is not None and 0 <= self._stream_index < len(self._messages):
                self._messages[self._stream_index]["content"] = content
            self._inner.update_idletasks()
            self._canvas.configure(scrollregion=self._canvas.bbox("all"))
            if self._auto_scroll:
                self._canvas.yview_moveto(1.0)
        except Exception:
            pass

    def end_stream(self, content: str) -> None:
        """Finalize the streaming card with the complete response text."""
        self.update_stream(content)
        self._stream_card = None
        self._stream_index = None
