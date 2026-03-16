"""Activity log pane — runtime terminal/log viewer.

Shows verbose internal activity: model requests, tool execution,
sandbox enforcement, errors/warnings. Styled as a low-level terminal.
"""

import tkinter as tk
from src.ui import theme as T
from src.core.runtime.activity_stream import ActivityEntry


_LEVEL_COLORS = {
    "INFO":  T.TEXT_DIM,
    "WARN":  T.AMBER,
    "ERROR": T.RED,
    "DEBUG": T.TEXT_DIM,
    "TOOL":  T.MAGENTA,
    "MODEL": T.PURPLE,
}


class ActivityLogPane(tk.Frame):
    """Terminal-style runtime activity viewer."""

    def __init__(self, parent, **kw):
        kw.setdefault("bg", T.BG_DARK)
        super().__init__(parent, **kw)

        header = tk.Frame(self, bg=T.BG_DARK)
        header.pack(fill="x")
        tk.Label(header, text="RUNTIME", font=T.FONT_HEADING,
                 fg=T.MAGENTA, bg=T.BG_DARK).pack(side="left", padx=10, pady=(6, 2))

        self._text = tk.Text(
            self, wrap="word", font=T.FONT_LOG,
            fg=T.TEXT_DIM, bg="#080c14",
            relief="flat", bd=0, highlightthickness=1,
            highlightcolor=T.BORDER, highlightbackground=T.BORDER,
            insertbackground=T.CYAN, padx=8, pady=4,
            state="disabled",
        )
        scrollbar = tk.Scrollbar(self, command=self._text.yview,
                                  bg=T.SCROLLBAR_BG, troughcolor=T.SCROLLBAR_BG)
        self._text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._text.pack(fill="both", expand=True, padx=(4, 0), pady=4)

        # Tag colors
        for level, color in _LEVEL_COLORS.items():
            self._text.tag_configure(level, foreground=color)
        self._text.tag_configure("TS", foreground="#3a4a6b")

    def append_entry(self, entry: ActivityEntry) -> None:
        self._text.config(state="normal")
        ts_short = entry.timestamp[11:19] if len(entry.timestamp) > 19 else entry.timestamp
        line = f"[{ts_short}] [{entry.level:<5}] {entry.source}: {entry.message}\n"
        start = self._text.index("end-1c")
        self._text.insert("end", line)

        # Apply tag for the level portion
        self._text.tag_add(entry.level, start, "end-1c")
        self._text.config(state="disabled")
        self._text.see("end")

    def clear(self) -> None:
        self._text.config(state="normal")
        self._text.delete("1.0", "end")
        self._text.config(state="disabled")
