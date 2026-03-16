"""Model selection dropdown with refresh button."""

import tkinter as tk
from tkinter import ttk
from src.ui import theme as T


class ModelPicker(tk.Frame):
    """Ollama model picker with refresh capability."""

    def __init__(self, parent, on_select=None, on_refresh=None, **kw):
        kw.setdefault("bg", T.BG_MID)
        super().__init__(parent, **kw)
        self._on_select = on_select
        self._on_refresh = on_refresh

        header = tk.Label(self, text="MODEL", font=T.FONT_HEADING,
                          fg=T.CYAN, bg=T.BG_MID)
        header.pack(anchor="w", padx=8, pady=(8, 4))

        row = tk.Frame(self, bg=T.BG_MID)
        row.pack(fill="x", padx=8, pady=2)

        self._var = tk.StringVar(value="(none)")
        self._combo = ttk.Combobox(row, textvariable=self._var, state="readonly",
                                    font=T.FONT_BODY, width=22)
        self._combo.pack(side="left", fill="x", expand=True)
        self._combo.bind("<<ComboboxSelected>>", self._handle_select)

        self._refresh_btn = tk.Button(
            row, text="⟳", font=T.FONT_BUTTON, width=3,
            bg=T.BG_LIGHT, fg=T.CYAN, activebackground=T.BG_SURFACE,
            activeforeground=T.GREEN, relief="flat", bd=0,
            command=self._handle_refresh,
        )
        self._refresh_btn.pack(side="right", padx=(6, 0))

        self._status = tk.Label(self, text="No models loaded", font=T.FONT_SMALL,
                                fg=T.TEXT_DIM, bg=T.BG_MID)
        self._status.pack(anchor="w", padx=8, pady=(2, 6))

    def set_models(self, models: list[str], selected: str = "") -> None:
        self._combo["values"] = models
        if selected and selected in models:
            self._var.set(selected)
        elif models:
            self._var.set(models[0])
        self._status.config(text=f"{len(models)} model(s) available")

    def get_selected(self) -> str:
        return self._var.get()

    def _handle_select(self, _event=None) -> None:
        if self._on_select:
            self._on_select(self._var.get())

    def _handle_refresh(self) -> None:
        self._status.config(text="Scanning...", fg=T.AMBER)
        if self._on_refresh:
            self._on_refresh()
