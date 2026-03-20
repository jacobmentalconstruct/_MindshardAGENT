"""Single chat message card for the transcript pane."""

import tkinter as tk
from src.ui import theme as T


# Role-specific styling
_ROLE_STYLES = {
    "user": {"accent": T.CYAN, "label": "YOU", "bg": T.BG_MID},
    "assistant": {"accent": T.PURPLE, "label": "AGENT", "bg": T.BG_AGENT},
    "tool": {"accent": T.MAGENTA, "label": "TOOL", "bg": T.BG_TOOL},
    "system": {"accent": T.AMBER, "label": "SYS", "bg": T.BG_MID},
}


class ChatMessageCard(tk.Frame):
    """A single message bubble in the chat transcript."""

    def __init__(self, parent, role: str, content: str, metadata: dict | None = None, **kw):
        style = _ROLE_STYLES.get(role, _ROLE_STYLES["system"])
        kw.setdefault("bg", style["bg"])
        super().__init__(parent, **kw)
        self.configure(padx=0, pady=0)

        # Left accent bar
        accent_bar = tk.Frame(self, bg=style["accent"], width=3)
        accent_bar.pack(side="left", fill="y")

        body = tk.Frame(self, bg=style["bg"])
        body.pack(side="left", fill="both", expand=True, padx=(8, 8), pady=(6, 6))

        # Role label
        role_lbl = tk.Label(body, text=style["label"], font=T.FONT_SMALL,
                            fg=style["accent"], bg=style["bg"])
        role_lbl.pack(anchor="w")

        # Message text
        self._msg = tk.Text(body, wrap="word", font=T.FONT_BODY,
                            fg=T.TEXT_PRIMARY, bg=style["bg"],
                            relief="flat", bd=0, highlightthickness=0,
                            padx=0, pady=4)
        self._msg.insert("1.0", content)
        self._msg.config(state="disabled")

        # Auto-height: count lines needed
        self._resize_to_content()
        self._msg.pack(fill="x", expand=True)

        # Metadata row (assistant messages)
        if metadata and role == "assistant":
            meta_frame = tk.Frame(body, bg=style["bg"])
            meta_frame.pack(fill="x", pady=(2, 0))
            for key, val in metadata.items():
                tag = tk.Label(meta_frame, text=f"{key}: {val}", font=T.FONT_SMALL,
                               fg=T.TEXT_DIM, bg=style["bg"], padx=6)
                tag.pack(side="left")

    @property
    def text_widget(self) -> tk.Text:
        """Access the internal Text widget for streaming updates."""
        return self._msg

    def _resize_to_content(self) -> None:
        """Resize the text widget height to fit its content."""
        content = self._msg.get("1.0", "end-1c")
        line_count = max(1, content.count("\n") + 1)
        char_width = 80
        for line in content.split("\n"):
            if len(line) > char_width:
                line_count += len(line) // char_width
        self._msg.config(height=min(line_count, 50))

    def update_streaming_content(self, content: str) -> None:
        """Update card content during streaming and auto-resize."""
        self._msg.config(state="normal")
        self._msg.delete("1.0", "end")
        self._msg.insert("1.0", content)
        self._msg.config(state="disabled")
        self._resize_to_content()
