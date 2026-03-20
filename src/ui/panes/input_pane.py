"""User input pane — multi-line text entry with submit and token estimate."""

import tkinter as tk
from src.ui import theme as T
from src.core.utils.text_metrics import estimate_tokens


class InputPane(tk.Frame):
    """Multi-line user input with live token estimate and submit button."""

    def __init__(self, parent, on_submit=None, **kw):
        kw.setdefault("bg", T.BG_DARK)
        super().__init__(parent, **kw)
        self._on_submit = on_submit

        header = tk.Label(self, text="INPUT", font=T.FONT_SMALL,
                          fg=T.TEXT_DIM, bg=T.BG_DARK)
        header.pack(anchor="w", padx=8, pady=(6, 2))

        # Text input
        self._text = tk.Text(
            self, wrap="word", font=T.FONT_INPUT,
            fg=T.TEXT_INPUT, bg=T.BG_LIGHT,
            insertbackground=T.CYAN, relief="flat", bd=0,
            highlightthickness=1, highlightcolor=T.BORDER_GLOW,
            highlightbackground=T.BORDER,
            height=5, padx=8, pady=6,
        )
        self._text.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self._text.bind("<KeyRelease>", self._update_token_count)
        self._text.bind("<Control-Return>", self._handle_submit)
        self._text.bind("<Alt-Return>", self._handle_submit)

        # Bottom row: token count + submit
        bottom = tk.Frame(self, bg=T.BG_DARK)
        bottom.pack(fill="x", padx=8, pady=(0, 8))

        self._token_label = tk.Label(bottom, text="Approx tokens: 0",
                                      font=T.FONT_SMALL, fg=T.TEXT_DIM, bg=T.BG_DARK)
        self._token_label.pack(side="left")

        self._submit_btn = tk.Button(
            bottom, text="SEND ⟩", font=T.FONT_BUTTON,
            fg=T.BG_DARK, bg=T.CYAN, activebackground=T.GREEN,
            activeforeground=T.BG_DARK, relief="flat", bd=0,
            padx=16, pady=4, cursor="hand2",
            command=self._handle_submit,
        )
        self._submit_btn.pack(side="right")
        self._submit_btn.bind("<Enter>", lambda e: self._submit_btn.config(bg=T.GREEN))
        self._submit_btn.bind("<Leave>", lambda e: self._submit_btn.config(bg=T.CYAN))

    def _update_token_count(self, _event=None) -> None:
        text = self._text.get("1.0", "end-1c")
        count = estimate_tokens(text)
        self._token_label.config(text=f"Approx tokens: {count}")

    def _handle_submit(self, _event=None) -> None:
        text = self._text.get("1.0", "end-1c").strip()
        if text and self._on_submit:
            self._text.delete("1.0", "end")
            self._update_token_count()
            self._on_submit(text)
        return "break"  # prevent newline on Ctrl+Enter

    def get_text(self) -> str:
        return self._text.get("1.0", "end-1c").strip()

    def set_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self._text.config(state=state)
        self._submit_btn.config(state=state)
