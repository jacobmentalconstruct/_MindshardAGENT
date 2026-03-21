"""Modal approval dialog for agent-triggered local GUI launches."""

from __future__ import annotations

import tkinter as tk

from src.ui import theme as T


class GuiLaunchDialog(tk.Toplevel):
    """Ask the user whether an agent-triggered GUI window should be allowed."""

    def __init__(self, parent, *, command: str, target_path: str = "", reason: str = ""):
        super().__init__(parent)
        self.title("Allow Local Window?")
        self.configure(bg=T.BG_DARK)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result: str = "deny"

        shell = tk.Frame(self, bg=T.BG_DARK)
        shell.pack(fill="both", expand=True, padx=16, pady=14)

        tk.Label(
            shell,
            text="GUI LAUNCH APPROVAL",
            font=T.FONT_HEADING,
            fg=T.AMBER,
            bg=T.BG_DARK,
        ).pack(anchor="w", pady=(0, 8))

        tk.Label(
            shell,
            text=(
                "The agent wants to open a local desktop window. "
                "Only allow this if you intended to test a GUI script."
            ),
            font=T.FONT_SMALL,
            fg=T.TEXT_PRIMARY,
            bg=T.BG_DARK,
            justify="left",
            wraplength=460,
        ).pack(anchor="w")

        card = tk.Frame(
            shell,
            bg=T.BG_MID,
            highlightthickness=1,
            highlightbackground=T.BORDER,
            highlightcolor=T.BORDER,
        )
        card.pack(fill="x", pady=12)

        tk.Label(
            card,
            text="COMMAND",
            font=T.FONT_SMALL,
            fg=T.CYAN,
            bg=T.BG_MID,
        ).pack(anchor="w", padx=10, pady=(8, 2))

        tk.Label(
            card,
            text=command,
            font=T.FONT_SMALL,
            fg=T.TEXT_BRIGHT,
            bg=T.BG_MID,
            justify="left",
            wraplength=440,
        ).pack(anchor="w", padx=10)

        if target_path:
            tk.Label(
                card,
                text="SCRIPT",
                font=T.FONT_SMALL,
                fg=T.CYAN,
                bg=T.BG_MID,
            ).pack(anchor="w", padx=10, pady=(10, 2))
            tk.Label(
                card,
                text=target_path,
                font=T.FONT_SMALL,
                fg=T.TEXT_DIM,
                bg=T.BG_MID,
                justify="left",
                wraplength=440,
            ).pack(anchor="w", padx=10)

        if reason:
            tk.Label(
                card,
                text="WHY IT WAS FLAGGED",
                font=T.FONT_SMALL,
                fg=T.CYAN,
                bg=T.BG_MID,
            ).pack(anchor="w", padx=10, pady=(10, 2))
            tk.Label(
                card,
                text=reason,
                font=T.FONT_SMALL,
                fg=T.TEXT_DIM,
                bg=T.BG_MID,
                justify="left",
                wraplength=440,
            ).pack(anchor="w", padx=10, pady=(0, 10))

        btn_row = tk.Frame(shell, bg=T.BG_DARK)
        btn_row.pack(fill="x")

        tk.Button(
            btn_row,
            text="Deny",
            font=T.FONT_BUTTON,
            fg=T.TEXT_DIM,
            bg=T.BG_LIGHT,
            activebackground=T.BG_SURFACE,
            activeforeground=T.TEXT_PRIMARY,
            relief="flat",
            bd=0,
            padx=14,
            pady=4,
            cursor="hand2",
            command=self._deny,
        ).pack(side="left")

        tk.Button(
            btn_row,
            text="Always Allow",
            font=T.FONT_BUTTON,
            fg=T.BG_DARK,
            bg=T.GREEN,
            activebackground=T.CYAN,
            activeforeground=T.BG_DARK,
            relief="flat",
            bd=0,
            padx=14,
            pady=4,
            cursor="hand2",
            command=self._always_allow,
        ).pack(side="right")

        tk.Button(
            btn_row,
            text="Allow Once",
            font=T.FONT_BUTTON,
            fg=T.BG_DARK,
            bg=T.CYAN,
            activebackground=T.GREEN,
            activeforeground=T.BG_DARK,
            relief="flat",
            bd=0,
            padx=14,
            pady=4,
            cursor="hand2",
            command=self._allow_once,
        ).pack(side="right", padx=(0, 8))

        self.bind("<Escape>", lambda _e: self._deny())
        self.bind("<Return>", lambda _e: self._allow_once())

        self.update_idletasks()
        self.geometry(f"+{parent.winfo_rootx() + 100}+{parent.winfo_rooty() + 80}")
        self.wait_window(self)

    def _deny(self) -> None:
        self.result = "deny"
        self.destroy()

    def _allow_once(self) -> None:
        self.result = "allow_once"
        self.destroy()

    def _always_allow(self) -> None:
        self.result = "always_allow"
        self.destroy()
