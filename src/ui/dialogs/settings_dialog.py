"""Application settings modal."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from src.ui import theme as T


class SettingsDialog(tk.Toplevel):
    """Tabbed settings dialog for app-wide preferences."""

    def __init__(
        self,
        parent,
        *,
        initial_tool_round_limit: int,
        initial_gui_launch_policy: str,
    ):
        super().__init__(parent)
        self.title("Settings")
        self.configure(bg=T.BG_DARK)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result: dict | None = None

        self._tool_round_limit = tk.IntVar(value=max(1, int(initial_tool_round_limit)))
        self._gui_launch_policy = tk.StringVar(value=initial_gui_launch_policy or "ask")

        shell = tk.Frame(self, bg=T.BG_DARK)
        shell.pack(fill="both", expand=True, padx=12, pady=12)

        header = tk.Frame(shell, bg=T.BG_DARK)
        header.pack(fill="x", pady=(0, 8))
        tk.Label(
            header,
            text="SETTINGS",
            font=T.FONT_HEADING,
            fg=T.CYAN,
            bg=T.BG_DARK,
        ).pack(side="left")

        notebook = ttk.Notebook(shell)
        notebook.pack(fill="both", expand=True)

        general_tab = tk.Frame(notebook, bg=T.BG_DARK)
        tools_tab = tk.Frame(notebook, bg=T.BG_DARK)
        gui_tab = tk.Frame(notebook, bg=T.BG_DARK)
        safety_tab = tk.Frame(notebook, bg=T.BG_DARK)

        notebook.add(general_tab, text="General")
        notebook.add(tools_tab, text="Tools")
        notebook.add(gui_tab, text="GUI / Tkinter")
        notebook.add(safety_tab, text="Safety")

        self._build_general_tab(general_tab)
        self._build_tools_tab(tools_tab)
        self._build_gui_tab(gui_tab)
        self._build_safety_tab(safety_tab)

        footer = tk.Frame(shell, bg=T.BG_DARK)
        footer.pack(fill="x", pady=(10, 0))

        cancel_btn = tk.Button(
            footer,
            text="Cancel",
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
            command=self._cancel,
        )
        cancel_btn.pack(side="right")

        save_btn = tk.Button(
            footer,
            text="Save",
            font=T.FONT_BUTTON,
            fg=T.BG_DARK,
            bg=T.CYAN,
            activebackground=T.GREEN,
            activeforeground=T.BG_DARK,
            relief="flat",
            bd=0,
            padx=18,
            pady=4,
            cursor="hand2",
            command=self._save,
        )
        save_btn.pack(side="right", padx=(0, 8))

        self.bind("<Escape>", lambda _e: self._cancel())
        self.bind("<Control-Return>", lambda _e: self._save())
        self.update_idletasks()
        self.geometry(f"+{parent.winfo_rootx() + 80}+{parent.winfo_rooty() + 60}")
        self.wait_window(self)

    def _card(self, parent, title: str) -> tk.Frame:
        card = tk.Frame(
            parent,
            bg=T.BG_MID,
            highlightthickness=1,
            highlightbackground=T.BORDER,
            highlightcolor=T.BORDER,
        )
        card.pack(fill="x", padx=8, pady=8)
        tk.Label(
            card,
            text=title,
            font=T.FONT_SMALL,
            fg=T.CYAN,
            bg=T.BG_MID,
        ).pack(anchor="w", padx=10, pady=(8, 4))
        return card

    def _build_general_tab(self, parent) -> None:
        card = self._card(parent, "ABOUT")
        tk.Label(
            card,
            text=(
                "App-wide preferences live here. Settings are persisted to app_config.json.\n"
                "Use this dialog for behavior that should be explicit and intentional."
            ),
            font=T.FONT_SMALL,
            fg=T.TEXT_PRIMARY,
            bg=T.BG_MID,
            anchor="w",
            justify="left",
            wraplength=420,
        ).pack(fill="x", padx=10, pady=(0, 10))

    def _build_tools_tab(self, parent) -> None:
        card = self._card(parent, "AGENT TOOL LOOP")
        tk.Label(
            card,
            text="Max Tool Rounds",
            font=T.FONT_SMALL,
            fg=T.TEXT_PRIMARY,
            bg=T.BG_MID,
            anchor="w",
        ).pack(fill="x", padx=10)

        row = tk.Frame(card, bg=T.BG_MID)
        row.pack(fill="x", padx=10, pady=(4, 6))
        spin = tk.Spinbox(
            row,
            from_=1,
            to=50,
            width=5,
            textvariable=self._tool_round_limit,
            font=T.FONT_SMALL,
            fg=T.TEXT_INPUT,
            bg=T.BG_LIGHT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=T.BORDER,
            highlightcolor=T.BORDER_GLOW,
            buttonbackground=T.BG_LIGHT,
        )
        spin.pack(side="left")

        tk.Label(
            card,
            text=(
                "Higher values let the agent keep exploring with tools longer.\n"
                "Escape can stop an active turn, but larger limits still mean more autonomy."
            ),
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_MID,
            anchor="w",
            justify="left",
            wraplength=420,
        ).pack(fill="x", padx=10, pady=(0, 10))

    def _build_gui_tab(self, parent) -> None:
        card = self._card(parent, "LOCAL WINDOW LAUNCHES")
        tk.Label(
            card,
            text="When the agent tries to open a local Tkinter / desktop window:",
            font=T.FONT_SMALL,
            fg=T.TEXT_PRIMARY,
            bg=T.BG_MID,
            anchor="w",
            justify="left",
            wraplength=420,
        ).pack(fill="x", padx=10, pady=(0, 6))

        for value, label, desc in [
            ("deny", "Block", "Never allow agent-triggered local windows."),
            ("ask", "Ask", "Show a HITL approval dialog before opening a local window."),
            ("allow", "Allow", "Allow local Tkinter windows without asking."),
        ]:
            radio = tk.Radiobutton(
                card,
                text=label,
                value=value,
                variable=self._gui_launch_policy,
                font=T.FONT_SMALL,
                fg=T.TEXT_PRIMARY,
                bg=T.BG_MID,
                selectcolor=T.BG_LIGHT,
                activebackground=T.BG_MID,
                activeforeground=T.CYAN,
                anchor="w",
                justify="left",
                highlightthickness=0,
            )
            radio.pack(fill="x", padx=10, pady=(0, 2))
            tk.Label(
                card,
                text=desc,
                font=T.FONT_SMALL,
                fg=T.TEXT_DIM,
                bg=T.BG_MID,
                anchor="w",
                justify="left",
                wraplength=390,
            ).pack(fill="x", padx=28, pady=(0, 4))

        tk.Label(
            card,
            text="Docker mode always blocks GUI launches because desktop windows will not display meaningfully.",
            font=T.FONT_SMALL,
            fg=T.AMBER,
            bg=T.BG_MID,
            anchor="w",
            justify="left",
            wraplength=420,
        ).pack(fill="x", padx=10, pady=(2, 10))

    def _build_safety_tab(self, parent) -> None:
        card = self._card(parent, "NEXT SAFETY PHASE")
        tk.Label(
            card,
            text=(
                "Reserved for the upcoming CLI safety gate.\n\n"
                "Planned next:\n"
                "- require intentional enabling of agent CLI execution\n"
                "- make dangerous capabilities obvious to the user\n"
                "- keep high-power modes opt-in"
            ),
            font=T.FONT_SMALL,
            fg=T.TEXT_PRIMARY,
            bg=T.BG_MID,
            anchor="w",
            justify="left",
            wraplength=420,
        ).pack(fill="x", padx=10, pady=(0, 10))

    def _save(self) -> None:
        try:
            rounds = max(1, int(self._tool_round_limit.get()))
        except (tk.TclError, ValueError):
            rounds = 12
        self.result = {
            "max_tool_rounds": rounds,
            "gui_launch_policy": self._gui_launch_policy.get() or "ask",
        }
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()
