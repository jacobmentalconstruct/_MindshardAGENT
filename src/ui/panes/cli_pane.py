"""CLI panel — direct sandbox command entry for users and agents.

A terminal-like input/output panel that executes commands through
the sandbox CLI runner. Shows command history and results inline.
"""

import tkinter as tk
from src.ui import theme as T


class CLIPane(tk.Frame):
    """Terminal-style CLI input panel for sandbox commands."""

    def __init__(self, parent, on_command=None, **kw):
        kw.setdefault("bg", T.BG_DARK)
        super().__init__(parent, **kw)
        self._on_command = on_command
        self._cmd_history: list[str] = []
        self._history_idx = -1

        header = tk.Frame(self, bg=T.BG_DARK)
        header.pack(fill="x")
        tk.Label(header, text="SANDBOX CLI", font=T.FONT_HEADING,
                 fg=T.GREEN, bg=T.BG_DARK).pack(side="left", padx=10, pady=(6, 2))

        # Output area
        self._output = tk.Text(
            self, wrap="word", font=T.FONT_LOG,
            fg=T.GREEN, bg=T.BG_DEEPEST,
            relief="flat", bd=0, highlightthickness=1,
            highlightcolor=T.BORDER, highlightbackground=T.BORDER,
            insertbackground=T.GREEN, padx=8, pady=4,
            height=8, state="disabled",
        )
        self._output.pack(fill="both", expand=True, padx=4, pady=(2, 0))

        # Tags for output styling
        self._output.tag_configure("cmd", foreground=T.CYAN)
        self._output.tag_configure("stdout", foreground=T.GREEN)
        self._output.tag_configure("stderr", foreground=T.RED)
        self._output.tag_configure("info", foreground=T.TEXT_DIM)

        # Input row
        input_row = tk.Frame(self, bg=T.BG_DARK)
        input_row.pack(fill="x", padx=4, pady=(2, 6))

        tk.Label(input_row, text="$", font=T.FONT_BODY, fg=T.GREEN,
                 bg=T.BG_DARK).pack(side="left", padx=(8, 4))

        self._entry = tk.Entry(
            input_row, font=T.FONT_INPUT,
            fg=T.GREEN, bg=T.BG_LIGHT,
            insertbackground=T.GREEN, relief="flat",
            highlightthickness=1, highlightcolor=T.GREEN,
            highlightbackground=T.BORDER,
        )
        self._entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._entry.bind("<Return>", self._handle_submit)
        self._entry.bind("<Up>", self._history_up)
        self._entry.bind("<Down>", self._history_down)

        run_btn = tk.Button(
            input_row, text="RUN", font=T.FONT_BUTTON,
            fg=T.BG_DARK, bg=T.GREEN, activebackground=T.CYAN,
            relief="flat", bd=0, padx=10, cursor="hand2",
            command=self._handle_submit,
        )
        run_btn.pack(side="right")

    def _handle_submit(self, _event=None) -> None:
        cmd = self._entry.get().strip()
        if not cmd:
            return
        self._cmd_history.append(cmd)
        self._history_idx = -1
        self._entry.delete(0, "end")

        self._append_output(f"$ {cmd}\n", "cmd")

        if self._on_command:
            self._on_command(cmd)

    def _history_up(self, _event=None) -> None:
        if not self._cmd_history:
            return
        if self._history_idx == -1:
            self._history_idx = len(self._cmd_history) - 1
        elif self._history_idx > 0:
            self._history_idx -= 1
        self._entry.delete(0, "end")
        self._entry.insert(0, self._cmd_history[self._history_idx])

    def _history_down(self, _event=None) -> None:
        if self._history_idx == -1:
            return
        if self._history_idx < len(self._cmd_history) - 1:
            self._history_idx += 1
            self._entry.delete(0, "end")
            self._entry.insert(0, self._cmd_history[self._history_idx])
        else:
            self._history_idx = -1
            self._entry.delete(0, "end")

    def show_result(self, result: dict) -> None:
        stdout = result.get("stdout", "").strip()
        stderr = result.get("stderr", "").strip()
        exit_code = result.get("exit_code", -1)

        if stdout:
            self._append_output(stdout + "\n", "stdout")
        if stderr:
            self._append_output(stderr + "\n", "stderr")
        color = "info" if exit_code == 0 else "stderr"
        self._append_output(f"[exit {exit_code}]\n", color)

    def _append_output(self, text: str, tag: str = "") -> None:
        self._output.config(state="normal")
        if tag:
            self._output.insert("end", text, tag)
        else:
            self._output.insert("end", text)
        self._output.config(state="disabled")
        self._output.see("end")

    def clear(self) -> None:
        self._output.config(state="normal")
        self._output.delete("1.0", "end")
        self._output.config(state="disabled")
