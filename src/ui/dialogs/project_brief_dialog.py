"""Project Brief dialog — used for attach and later brief editing."""

import tkinter as tk
from src.ui import theme as T


class ProjectBriefDialog(tk.Toplevel):
    """Modal dialog to collect project brief before attaching."""

    def __init__(
        self,
        parent,
        project_name: str = "",
        is_self_edit: bool = False,
        initial_data: dict | None = None,
        submit_label: str = "ATTACH PROJECT",
        title_text: str = "PROJECT BRIEF",
    ):
        super().__init__(parent)
        self.title("Project Brief")
        self.configure(bg=T.BG_DARK)
        self.resizable(False, False)
        self.grab_set()  # modal

        self._result: dict | None = None
        initial_data = initial_data or {}
        initial_display_name = initial_data.get("display_name", project_name)

        # Header
        tk.Label(self, text=title_text, font=(T.FONT_FAMILY, 14, "bold"),
                 fg=T.CYAN, bg=T.BG_DARK).pack(padx=20, pady=(16, 4))
        tk.Label(self, text=f"Project: {project_name}",
                 font=T.FONT_SMALL, fg=T.TEXT_DIM, bg=T.BG_DARK).pack(padx=20, pady=(0, 12))
        tk.Frame(self, bg=T.BORDER, height=1).pack(fill="x", padx=16)

        form = tk.Frame(self, bg=T.BG_DARK)
        form.pack(fill="both", expand=True, padx=20, pady=12)

        def _field(label, height=1, required=False):
            lbl_text = label + (" *" if required else "")
            tk.Label(form, text=lbl_text, font=T.FONT_SMALL,
                     fg=T.TEXT_DIM if not required else T.AMBER,
                     bg=T.BG_DARK, anchor="w").pack(fill="x", pady=(8, 2))
            if height == 1:
                e = tk.Entry(form, font=T.FONT_INPUT, fg=T.TEXT_INPUT,
                             bg=T.BG_LIGHT, insertbackground=T.CYAN,
                             relief="flat", bd=0, highlightthickness=1,
                             highlightbackground=T.BORDER, highlightcolor=T.BORDER_GLOW)
                e.pack(fill="x", ipady=4)
            else:
                e = tk.Text(form, font=T.FONT_INPUT, fg=T.TEXT_INPUT,
                            bg=T.BG_LIGHT, insertbackground=T.CYAN,
                            relief="flat", bd=0, highlightthickness=1,
                            highlightbackground=T.BORDER, highlightcolor=T.BORDER_GLOW,
                            height=height, padx=4, pady=4)
                e.pack(fill="x")
            return e

        self._display_name = _field("Display name *", required=True)
        self._display_name.insert(0, initial_display_name)
        self._purpose = _field("Project purpose *", height=2, required=True)
        if initial_data.get("project_purpose"):
            self._purpose.insert("1.0", initial_data["project_purpose"])
        self._goal = _field("Current goal *", height=2, required=True)
        if initial_data.get("current_goal"):
            self._goal.insert("1.0", initial_data["current_goal"])
        self._ptype = _field("Project type (e.g. Python app, web app, CLI tool)")
        self._ptype.insert(0, initial_data.get("project_type", "General") or "General")
        self._constraints = _field("Constraints / off-limits (optional)")
        if initial_data.get("constraints"):
            self._constraints.insert("1.0", initial_data["constraints"])

        # Profile selector
        tk.Label(form, text="Profile", font=T.FONT_SMALL,
                 fg=T.TEXT_DIM, bg=T.BG_DARK, anchor="w").pack(fill="x", pady=(8, 2))
        profile_frame = tk.Frame(form, bg=T.BG_DARK)
        profile_frame.pack(fill="x")
        self._profile_var = tk.StringVar(
            value=initial_data.get("profile", "self_edit" if is_self_edit else "standard")
        )
        for val, label in [("standard", "Standard"), ("self_edit", "Self-edit (working on MindshardAGENT itself)")]:
            rb = tk.Radiobutton(profile_frame, text=label, variable=self._profile_var, value=val,
                                font=T.FONT_SMALL, fg=T.TEXT_PRIMARY, bg=T.BG_DARK,
                                selectcolor=T.BG_LIGHT, activebackground=T.BG_DARK,
                                activeforeground=T.CYAN)
            rb.pack(anchor="w")

        # Buttons
        tk.Frame(self, bg=T.BORDER, height=1).pack(fill="x", padx=16)
        btn_row = tk.Frame(self, bg=T.BG_DARK)
        btn_row.pack(fill="x", padx=20, pady=12)

        tk.Button(btn_row, text="Cancel", font=T.FONT_BUTTON,
                  fg=T.TEXT_DIM, bg=T.BG_LIGHT, relief="flat", bd=0,
                  padx=16, pady=4, cursor="hand2",
                  command=self._cancel).pack(side="left")

        tk.Button(btn_row, text=submit_label, font=T.FONT_BUTTON,
                  fg=T.BG_DARK, bg=T.CYAN, activebackground=T.GREEN,
                  activeforeground=T.BG_DARK, relief="flat", bd=0,
                  padx=16, pady=4, cursor="hand2",
                  command=self._submit).pack(side="right")

        self.bind("<Return>", lambda e: self._submit())
        self.bind("<Escape>", lambda e: self._cancel())

        # Center on parent
        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width() // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{pw - w // 2}+{ph - h // 2}")

        self.wait_window()

    def _get_text(self, widget) -> str:
        if isinstance(widget, tk.Text):
            return widget.get("1.0", "end-1c").strip()
        return widget.get().strip()

    def _submit(self):
        display_name = self._get_text(self._display_name)
        purpose = self._get_text(self._purpose)
        goal = self._get_text(self._goal)
        if not display_name or not purpose or not goal:
            # Highlight required fields
            return
        self._result = {
            "display_name": display_name,
            "project_purpose": purpose,
            "current_goal": goal,
            "project_type": self._get_text(self._ptype) or "General",
            "constraints": self._get_text(self._constraints),
            "profile": self._profile_var.get(),
        }
        self.destroy()

    def _cancel(self):
        self._result = None
        self.destroy()

    @property
    def result(self) -> dict | None:
        return self._result
