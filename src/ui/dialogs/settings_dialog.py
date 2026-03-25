"""Application settings modal."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from src.core.agent.model_roles import (
    CODING_ROLE,
    EMBEDDING_ROLE,
    FAST_PROBE_ROLE,
    PLANNER_ROLE,
    PRIMARY_CHAT_ROLE,
    RECOVERY_PLANNER_ROLE,
    REVIEW_ROLE,
    ROLE_LABELS,
)
from src.core.agent.probe_decision import (
    INTENT_PROBE,
    RELEVANCE_PROBE,
    LANGUAGE_PROBE,
    SUMMARY_PROBE,
)
from src.ui import theme as T

PROBE_TYPE_LABELS = {
    INTENT_PROBE: "Intent Classify",
    RELEVANCE_PROBE: "Relevance Pick",
    LANGUAGE_PROBE: "Language Detect",
    SUMMARY_PROBE: "Summary",
}
_PROBE_FALLBACK = "(use Fast Probe model)"


class SettingsDialog(tk.Toplevel):
    """Tabbed settings dialog for app-wide preferences."""

    def __init__(
        self,
        parent,
        *,
        available_models: list[str],
        initial_model_roles: dict[str, str],
        initial_tool_round_limit: int,
        initial_gui_launch_policy: str,
        initial_planning_enabled: bool,
        initial_recovery_planning_enabled: bool,
        initial_probe_models: dict[str, str] | None = None,
        initial_toolbox_root: str = "",
    ):
        super().__init__(parent)
        self.title("Settings")
        self.configure(bg=T.BG_DARK)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result: dict | None = None

        merged_models = [model for model in available_models if model]
        merged_models.extend(value for value in initial_model_roles.values() if value)
        self._available_models = list(dict.fromkeys(merged_models))
        self._tool_round_limit = tk.IntVar(value=max(1, int(initial_tool_round_limit)))
        self._gui_launch_policy = tk.StringVar(value=initial_gui_launch_policy or "ask")
        self._planning_enabled = tk.IntVar(value=1 if initial_planning_enabled else 0)
        self._recovery_planning_enabled = tk.IntVar(value=1 if initial_recovery_planning_enabled else 0)
        self._toolbox_root_var = tk.StringVar(value=initial_toolbox_root or "")
        self._role_vars = {
            PRIMARY_CHAT_ROLE: tk.StringVar(value=initial_model_roles.get(PRIMARY_CHAT_ROLE, "")),
            PLANNER_ROLE: tk.StringVar(value=initial_model_roles.get(PLANNER_ROLE, "")),
            RECOVERY_PLANNER_ROLE: tk.StringVar(value=initial_model_roles.get(RECOVERY_PLANNER_ROLE, "")),
            CODING_ROLE: tk.StringVar(value=initial_model_roles.get(CODING_ROLE, "")),
            REVIEW_ROLE: tk.StringVar(value=initial_model_roles.get(REVIEW_ROLE, "")),
            FAST_PROBE_ROLE: tk.StringVar(value=initial_model_roles.get(FAST_PROBE_ROLE, "")),
            EMBEDDING_ROLE: tk.StringVar(value=initial_model_roles.get(EMBEDDING_ROLE, "")),
        }
        pm = initial_probe_models or {}
        self._probe_model_vars = {
            INTENT_PROBE: tk.StringVar(value=pm.get(INTENT_PROBE, _PROBE_FALLBACK)),
            RELEVANCE_PROBE: tk.StringVar(value=pm.get(RELEVANCE_PROBE, _PROBE_FALLBACK)),
            LANGUAGE_PROBE: tk.StringVar(value=pm.get(LANGUAGE_PROBE, _PROBE_FALLBACK)),
            SUMMARY_PROBE: tk.StringVar(value=pm.get(SUMMARY_PROBE, _PROBE_FALLBACK)),
        }

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
        models_tab = tk.Frame(notebook, bg=T.BG_DARK)
        tools_tab = tk.Frame(notebook, bg=T.BG_DARK)
        gui_tab = tk.Frame(notebook, bg=T.BG_DARK)
        safety_tab = tk.Frame(notebook, bg=T.BG_DARK)

        notebook.add(general_tab, text="General")
        notebook.add(models_tab, text="Models")
        notebook.add(tools_tab, text="Tools")
        notebook.add(gui_tab, text="GUI / Tkinter")
        notebook.add(safety_tab, text="Safety")

        self._build_general_tab(general_tab)
        self._build_models_tab(models_tab)
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

        card = self._card(parent, "PLANNING STAGES")
        tk.Checkbutton(
            card,
            text="Use planner model before non-trivial execution loops",
            variable=self._planning_enabled,
            bg=T.BG_MID,
            fg=T.TEXT_PRIMARY,
            activebackground=T.BG_MID,
            activeforeground=T.CYAN,
            selectcolor=T.BG_LIGHT,
            font=T.FONT_BODY,
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=10, pady=(2, 4))
        tk.Checkbutton(
            card,
            text="Ask the recovery planner for a different approach after repeated failures",
            variable=self._recovery_planning_enabled,
            bg=T.BG_MID,
            fg=T.TEXT_PRIMARY,
            activebackground=T.BG_MID,
            activeforeground=T.CYAN,
            selectcolor=T.BG_LIGHT,
            font=T.FONT_BODY,
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=10, pady=(0, 4))
        tk.Label(
            card,
            text=(
                "This phase establishes model-role slots and explicit planner controls.\n"
                "The full initial-plan and repeated-failure recovery loop will build on these settings."
            ),
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_MID,
            anchor="w",
            justify="left",
            wraplength=420,
        ).pack(fill="x", padx=10, pady=(2, 10))

    def _build_models_tab(self, parent) -> None:
        card = self._card(parent, "MODEL ROLE SLOTS")
        tk.Label(
            card,
            text=(
                "Assign models by responsibility. This makes it easy to plug in stronger planners,\n"
                "specialist coders, or lightweight probe models without rewriting the app."
            ),
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_MID,
            anchor="w",
            justify="left",
            wraplength=420,
        ).pack(fill="x", padx=10, pady=(0, 8))

        wrap = tk.Frame(card, bg=T.BG_MID)
        wrap.pack(fill="x", padx=10, pady=(0, 10))
        wrap.columnconfigure(1, weight=1)
        row = 0
        for role in (
            PRIMARY_CHAT_ROLE,
            PLANNER_ROLE,
            RECOVERY_PLANNER_ROLE,
            CODING_ROLE,
            REVIEW_ROLE,
            FAST_PROBE_ROLE,
            EMBEDDING_ROLE,
        ):
            tk.Label(
                wrap,
                text=ROLE_LABELS[role],
                font=T.FONT_SMALL,
                fg=T.TEXT_PRIMARY,
                bg=T.BG_MID,
                anchor="w",
            ).grid(row=row, column=0, sticky="w", pady=(0, 6))
            combo = ttk.Combobox(
                wrap,
                textvariable=self._role_vars[role],
                values=self._available_models,
                state="readonly",
                width=32,
            )
            combo.grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=(0, 6))
            row += 1

        tk.Label(
            card,
            text=(
                "Typical pattern:\n"
                "- Primary Chat / Coding / Review = your default worker model\n"
                "- Planner = a smaller fast strategist\n"
                "- Recovery Planner = a larger deeper strategist when the worker gets stuck"
            ),
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_MID,
            anchor="w",
            justify="left",
            wraplength=420,
        ).pack(fill="x", padx=10, pady=(0, 10))

        # ── Per-Probe Model Overrides ──
        probe_card = self._card(parent, "PROBE MODEL OVERRIDES")
        tk.Label(
            probe_card,
            text=(
                "Assign tiny models to individual probe tasks. Each defaults to the\n"
                "Fast Probe slot above. Use 0.5B-2B models for speed on simple tasks."
            ),
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_MID,
            anchor="w",
            justify="left",
            wraplength=420,
        ).pack(fill="x", padx=10, pady=(0, 8))

        probe_wrap = tk.Frame(probe_card, bg=T.BG_MID)
        probe_wrap.pack(fill="x", padx=10, pady=(0, 10))
        probe_wrap.columnconfigure(1, weight=1)
        probe_models_with_fallback = [_PROBE_FALLBACK] + self._available_models
        prow = 0
        for probe_type in (INTENT_PROBE, RELEVANCE_PROBE, LANGUAGE_PROBE, SUMMARY_PROBE):
            tk.Label(
                probe_wrap,
                text=PROBE_TYPE_LABELS[probe_type],
                font=T.FONT_SMALL,
                fg=T.TEXT_PRIMARY,
                bg=T.BG_MID,
                anchor="w",
            ).grid(row=prow, column=0, sticky="w", pady=(0, 6))
            combo = ttk.Combobox(
                probe_wrap,
                textvariable=self._probe_model_vars[probe_type],
                values=probe_models_with_fallback,
                state="readonly",
                width=32,
            )
            combo.grid(row=prow, column=1, sticky="ew", padx=(10, 0), pady=(0, 6))
            prow += 1

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

        toolbox_card = self._card(parent, "EXTERNAL TOOLBOX ROOT")
        tk.Label(
            toolbox_card,
            text=(
                "Optional path to an external tool library directory.\n"
                "Python scripts in this folder with valid metadata headers are loaded\n"
                "as agent tools alongside sandbox-local tools."
            ),
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_MID,
            anchor="w",
            justify="left",
            wraplength=420,
        ).pack(fill="x", padx=10, pady=(0, 6))

        tb_row = tk.Frame(toolbox_card, bg=T.BG_MID)
        tb_row.pack(fill="x", padx=10, pady=(0, 4))

        tb_entry = tk.Entry(
            tb_row,
            textvariable=self._toolbox_root_var,
            font=T.FONT_SMALL,
            fg=T.TEXT_INPUT,
            bg=T.BG_LIGHT,
            insertbackground=T.CYAN,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=T.BORDER,
            highlightcolor=T.BORDER_GLOW,
            width=40,
        )
        tb_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        def _pick_toolbox():
            from tkinter import filedialog as _fd
            path = _fd.askdirectory(
                title="Select External Toolbox Root",
                initialdir=self._toolbox_root_var.get() or ".",
                parent=self,
            )
            if path:
                self._toolbox_root_var.set(path)

        tk.Button(
            tb_row,
            text="Browse",
            font=T.FONT_SMALL,
            fg=T.CYAN,
            bg=T.BG_LIGHT,
            activebackground=T.BG_SURFACE,
            activeforeground=T.CYAN,
            relief="flat",
            bd=0,
            padx=8,
            pady=3,
            cursor="hand2",
            command=_pick_toolbox,
        ).pack(side="left")

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
        # Build probe_models dict — strip fallback sentinel
        probe_models = {}
        for pt, var in self._probe_model_vars.items():
            val = var.get().strip()
            if val and val != _PROBE_FALLBACK:
                probe_models[pt] = val
        self.result = {
            "model_roles": {role: var.get().strip() for role, var in self._role_vars.items()},
            "max_tool_rounds": rounds,
            "gui_launch_policy": self._gui_launch_policy.get() or "ask",
            "planning_enabled": bool(self._planning_enabled.get()),
            "recovery_planning_enabled": bool(self._recovery_planning_enabled.get()),
            "probe_models": probe_models,
            "toolbox_root": self._toolbox_root_var.get().strip(),
        }
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()
