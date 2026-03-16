"""Right control pane — model picker, resource status, prompt preview, input, buttons.

Vertical stack in the right column of the main window.
"""

import tkinter as tk
from src.ui import theme as T
from src.ui.widgets.model_picker import ModelPicker
from src.ui.widgets.status_light import StatusLight
from src.ui.widgets.faux_button_panel import FauxButtonPanel
from src.ui.widgets.session_panel import SessionPanel
from src.ui.panes.input_pane import InputPane


class ResourceBlock(tk.Frame):
    """CPU/RAM/GPU status display."""

    def __init__(self, parent, **kw):
        kw.setdefault("bg", T.BG_MID)
        super().__init__(parent, **kw)

        header = tk.Label(self, text="RESOURCES", font=T.FONT_SMALL,
                          fg=T.TEXT_DIM, bg=T.BG_MID)
        header.pack(anchor="w", padx=8, pady=(6, 2))

        self._status_frame = tk.Frame(self, bg=T.BG_MID)
        self._status_frame.pack(fill="x", padx=8, pady=(0, 6))

        # Status light
        light_row = tk.Frame(self._status_frame, bg=T.BG_MID)
        light_row.pack(fill="x", pady=2)
        self._light = StatusLight(light_row, size=10, color=T.TEXT_DIM)
        self._light.pack(side="left")
        self._status_label = tk.Label(light_row, text="Idle", font=T.FONT_SMALL,
                                       fg=T.TEXT_DIM, bg=T.BG_MID)
        self._status_label.pack(side="left", padx=6)

        self._cpu_label = tk.Label(self._status_frame, text="CPU: --",
                                    font=T.FONT_SMALL, fg=T.TEXT_DIM, bg=T.BG_MID, anchor="w")
        self._cpu_label.pack(fill="x")
        self._ram_label = tk.Label(self._status_frame, text="RAM: --",
                                    font=T.FONT_SMALL, fg=T.TEXT_DIM, bg=T.BG_MID, anchor="w")
        self._ram_label.pack(fill="x")
        self._gpu_label = tk.Label(self._status_frame, text="GPU: --",
                                    font=T.FONT_SMALL, fg=T.TEXT_DIM, bg=T.BG_MID, anchor="w")
        self._gpu_label.pack(fill="x")

    def update_stats(self, cpu: float, ram_used: float, ram_total: float,
                     gpu_available: bool, vram_used: float, vram_total: float) -> None:
        self._cpu_label.config(text=f"CPU: {cpu:.0f}%")
        self._ram_label.config(text=f"RAM: {ram_used:.1f} / {ram_total:.1f} GB")

        if gpu_available:
            self._gpu_label.config(text=f"VRAM: {vram_used:.1f} / {vram_total:.1f} GB")
        else:
            self._gpu_label.config(text="GPU: unavailable")

        # Color coding
        if cpu > 85:
            self._light.set_color(T.RED)
            self._status_label.config(text="Heavy load", fg=T.RED)
        elif cpu > 60:
            self._light.set_color(T.AMBER)
            self._status_label.config(text="Moderate", fg=T.AMBER)
        else:
            self._light.set_color(T.GREEN)
            self._status_label.config(text="OK", fg=T.GREEN)


class PromptPreview(tk.Frame):
    """Shows the last user prompt for quick reference."""

    def __init__(self, parent, **kw):
        kw.setdefault("bg", T.BG_MID)
        super().__init__(parent, **kw)

        header = tk.Label(self, text="LAST PROMPT", font=T.FONT_SMALL,
                          fg=T.TEXT_DIM, bg=T.BG_MID)
        header.pack(anchor="w", padx=8, pady=(6, 2))

        self._text = tk.Text(
            self, wrap="word", font=T.FONT_SMALL,
            fg=T.TEXT_DIM, bg=T.BG_LIGHT,
            relief="flat", bd=0, highlightthickness=0,
            height=4, padx=6, pady=4, state="disabled",
        )
        self._text.pack(fill="both", expand=True, padx=8, pady=(0, 6))

    def set_text(self, text: str) -> None:
        self._text.config(state="normal")
        self._text.delete("1.0", "end")
        self._text.insert("1.0", text[:500])
        self._text.config(state="disabled")


class ControlPane(tk.Frame):
    """Right-side control column stacking all control widgets."""

    def __init__(self, parent, on_submit=None, on_model_select=None,
                 on_model_refresh=None, on_faux_click=None,
                 on_session_new=None, on_session_select=None,
                 on_session_rename=None, on_session_delete=None,
                 on_session_branch=None, on_sandbox_pick=None, **kw):
        kw.setdefault("bg", T.BG_DARK)
        super().__init__(parent, **kw)

        # Model picker
        self.model_picker = ModelPicker(
            self, on_select=on_model_select, on_refresh=on_model_refresh)
        self.model_picker.pack(fill="x", padx=4, pady=(4, 2))

        # Separator
        tk.Frame(self, bg=T.BORDER, height=1).pack(fill="x", padx=8, pady=4)

        # Session panel
        self.session_panel = SessionPanel(
            self,
            on_new=on_session_new,
            on_select=on_session_select,
            on_rename=on_session_rename,
            on_delete=on_session_delete,
            on_branch=on_session_branch,
        )
        self.session_panel.pack(fill="x", padx=4, pady=2)

        tk.Frame(self, bg=T.BORDER, height=1).pack(fill="x", padx=8, pady=4)

        # Resource status
        self.resources = ResourceBlock(self)
        self.resources.pack(fill="x", padx=4, pady=2)

        tk.Frame(self, bg=T.BORDER, height=1).pack(fill="x", padx=8, pady=4)

        # Prompt preview
        self.prompt_preview = PromptPreview(self)
        self.prompt_preview.pack(fill="x", padx=4, pady=2)

        tk.Frame(self, bg=T.BORDER, height=1).pack(fill="x", padx=8, pady=4)

        # Input pane
        self.input_pane = InputPane(self, on_submit=on_submit)
        self.input_pane.pack(fill="both", expand=True, padx=4, pady=2)

        tk.Frame(self, bg=T.BORDER, height=1).pack(fill="x", padx=8, pady=4)

        # Sandbox picker button + faux buttons
        action_row = tk.Frame(self, bg=T.BG_DARK)
        action_row.pack(fill="x", padx=4, pady=(2, 4))

        sandbox_btn = tk.Button(
            action_row, text="📁 SANDBOX", font=T.FONT_BUTTON,
            fg=T.AMBER, bg=T.BG_LIGHT, activebackground=T.BG_SURFACE,
            activeforeground=T.AMBER, relief="flat", bd=0,
            padx=10, pady=4, cursor="hand2",
            command=on_sandbox_pick if on_sandbox_pick else lambda: None,
        )
        sandbox_btn.pack(fill="x", pady=(0, 4))
        sandbox_btn.bind("<Enter>", lambda e: sandbox_btn.config(bg=T.BG_SURFACE))
        sandbox_btn.bind("<Leave>", lambda e: sandbox_btn.config(bg=T.BG_LIGHT))

        self.faux_buttons = FauxButtonPanel(self, on_click=on_faux_click)
        self.faux_buttons.pack(fill="x", padx=4, pady=(0, 4))
