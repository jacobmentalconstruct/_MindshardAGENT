"""User input pane — multi-line text entry with submit and stop controls."""

import tkinter as tk
from src.ui import theme as T
from src.core.utils.text_metrics import estimate_tokens


class InputPane(tk.Frame):
    """Multi-line user input with live token estimate and action buttons."""

    def __init__(self, parent, on_submit=None, on_stop=None, **kw):
        kw.setdefault("bg", T.BG_DARK)
        super().__init__(parent, **kw)
        self._on_submit = on_submit
        self._on_stop = on_stop

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

        # Bottom row: token count + actions
        bottom = tk.Frame(self, bg=T.BG_DARK)
        bottom.pack(fill="x", padx=8, pady=(0, 8))

        self._token_label = tk.Label(bottom, text="Approx tokens: 0",
                                      font=T.FONT_SMALL, fg=T.TEXT_DIM, bg=T.BG_DARK)
        self._token_label.pack(side="left")

        self._stop_btn = tk.Button(
            bottom, text="STOP", font=T.FONT_BUTTON,
            fg=T.TEXT_PRIMARY, bg=T.RED, activebackground=T.AMBER,
            activeforeground=T.BG_DARK, relief="flat", bd=0,
            padx=14, pady=4, cursor="hand2",
            command=self._handle_stop,
            state="disabled",
        )
        self._stop_btn.pack(side="right", padx=(0, 8))
        self._stop_btn.bind("<Enter>", lambda e: self._stop_btn.config(bg=T.AMBER) if str(self._stop_btn.cget("state")) == "normal" else None)
        self._stop_btn.bind("<Leave>", lambda e: self._stop_btn.config(bg=T.RED) if str(self._stop_btn.cget("state")) == "normal" else None)

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

    def _handle_stop(self) -> None:
        if self._on_stop:
            self._on_stop()

    def get_text(self) -> str:
        return self._text.get("1.0", "end-1c").strip()

    def set_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self._text.config(state=state)
        self._submit_btn.config(state=state)

    def is_enabled(self) -> bool:
        return str(self._text.cget("state")) == "normal"

    def set_text(self, text: str) -> None:
        """Replace the current input content with the given text."""
        current_state = str(self._text.cget("state"))
        self._text.config(state="normal")
        self._text.delete("1.0", "end")
        self._text.insert("1.0", text)
        if current_state == "disabled":
            self._text.config(state="disabled")
        self._update_token_count()

    def focus_input(self) -> None:
        """Move keyboard focus to the text input field."""
        self._text.focus_set()
        self._text.mark_set("insert", "end")

    def submit(self) -> bool:
        """Submit the current input content if possible."""
        text = self.get_text()
        if not text or not self.is_enabled():
            return False
        self._handle_submit()
        return True

    def set_stop_enabled(self, enabled: bool) -> None:
        self._stop_btn.config(state="normal" if enabled else "disabled")
        if not enabled:
            self.set_stop_requested(False)

    def set_stop_requested(self, requested: bool) -> None:
        if requested:
            self._stop_btn.config(text="STOPPING...", bg=T.AMBER, fg=T.BG_DARK, state="disabled")
        else:
            self._stop_btn.config(text="STOP", bg=T.RED, fg=T.TEXT_PRIMARY)
