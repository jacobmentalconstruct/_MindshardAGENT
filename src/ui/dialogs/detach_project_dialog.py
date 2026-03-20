"""Detach project dialog with sidecar retention choice."""

import tkinter as tk

from src.ui import theme as T


class DetachProjectDialog(tk.Toplevel):
    """Modal detach confirmation with a keep-sidecar option."""

    def __init__(self, parent, project_name: str, archive_dir: str):
        super().__init__(parent)
        self.title("Detach Project")
        self.configure(bg=T.BG_DARK)
        self.resizable(False, False)
        self.grab_set()

        self._result: dict | None = None
        self._keep_var = tk.BooleanVar(value=False)

        tk.Label(
            self,
            text="DETACH PROJECT",
            font=(T.FONT_FAMILY, 14, "bold"),
            fg=T.AMBER,
            bg=T.BG_DARK,
        ).pack(padx=20, pady=(16, 4))
        tk.Label(
            self,
            text=f"Project: {project_name}",
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_DARK,
        ).pack(padx=20, pady=(0, 12))

        body = tk.Frame(self, bg=T.BG_DARK)
        body.pack(fill="both", expand=True, padx=20, pady=(0, 12))

        tk.Label(
            body,
            text=(
                "This will create a final snapshot, archive `.mindshard/` to the memory vault, "
                "and detach the current working copy.\n\n"
                "Project files are not modified."
            ),
            font=T.FONT_SMALL,
            fg=T.TEXT_PRIMARY,
            bg=T.BG_DARK,
            justify="left",
            wraplength=420,
        ).pack(anchor="w")

        tk.Label(
            body,
            text=f"Archive location: {archive_dir}",
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_DARK,
            justify="left",
            wraplength=420,
        ).pack(anchor="w", pady=(10, 12))

        keep = tk.Checkbutton(
            body,
            text="Keep the full .mindshard sidecar in the working copy after detach",
            variable=self._keep_var,
            font=T.FONT_SMALL,
            fg=T.TEXT_PRIMARY,
            bg=T.BG_DARK,
            activebackground=T.BG_DARK,
            activeforeground=T.CYAN,
            selectcolor=T.BG_LIGHT,
            wraplength=420,
            justify="left",
        )
        keep.pack(anchor="w")

        tk.Frame(self, bg=T.BORDER, height=1).pack(fill="x", padx=16)
        btn_row = tk.Frame(self, bg=T.BG_DARK)
        btn_row.pack(fill="x", padx=20, pady=12)

        tk.Button(
            btn_row,
            text="Cancel",
            font=T.FONT_BUTTON,
            fg=T.TEXT_DIM,
            bg=T.BG_LIGHT,
            relief="flat",
            bd=0,
            padx=16,
            pady=4,
            cursor="hand2",
            command=self._cancel,
        ).pack(side="left")

        tk.Button(
            btn_row,
            text="DETACH",
            font=T.FONT_BUTTON,
            fg=T.BG_DARK,
            bg=T.AMBER,
            activebackground=T.GREEN,
            activeforeground=T.BG_DARK,
            relief="flat",
            bd=0,
            padx=16,
            pady=4,
            cursor="hand2",
            command=self._confirm,
        ).pack(side="right")

        self.bind("<Return>", lambda e: self._confirm())
        self.bind("<Escape>", lambda e: self._cancel())

        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width() // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{pw - w // 2}+{ph - h // 2}")
        self.wait_window()

    def _confirm(self):
        self._result = {"confirmed": True, "keep_sidecar": bool(self._keep_var.get())}
        self.destroy()

    def _cancel(self):
        self._result = {"confirmed": False, "keep_sidecar": False}
        self.destroy()

    @property
    def result(self) -> dict | None:
        return self._result
