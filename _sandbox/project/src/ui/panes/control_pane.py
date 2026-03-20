"""Right control pane — tabbed layout with pinned input.

Layout:
  ┌─────────────────────────────┐
  │ [Session] [Sandbox] [Watch] │  ← tab bar
  ├─────────────────────────────┤
  │                             │
  │  Tab content (scrollable)   │
  │                             │
  ├─────────────────────────────┤
  │  Input pane (pinned)        │
  ├─────────────────────────────┤
  │  Action buttons             │
  └─────────────────────────────┘

Tabs:
  Session  — Model picker, session list
  Sandbox  — Docker panel, sandbox picker, resources
  Watch    — Last response, last prompt, faux buttons
"""

import tkinter as tk
from src.ui import theme as T
from src.ui.widgets.model_picker import ModelPicker
from src.ui.widgets.status_light import StatusLight
from src.ui.widgets.faux_button_panel import FauxButtonPanel
from src.ui.widgets.session_panel import SessionPanel
from src.ui.widgets.docker_panel import DockerPanel
from src.ui.panes.input_pane import InputPane


# ── Reusable blocks ─────────────────────────────────────

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

        if cpu > 85:
            self._light.set_color(T.RED)
            self._status_label.config(text="Heavy load", fg=T.RED)
        elif cpu > 60:
            self._light.set_color(T.AMBER)
            self._status_label.config(text="Moderate", fg=T.AMBER)
        else:
            self._light.set_color(T.GREEN)
            self._status_label.config(text="OK", fg=T.GREEN)


class TextPreview(tk.Frame):
    """Scrollable read-only text preview block."""

    def __init__(self, parent, label: str = "PREVIEW", height: int = 5, **kw):
        kw.setdefault("bg", T.BG_MID)
        super().__init__(parent, **kw)

        header = tk.Label(self, text=label, font=T.FONT_SMALL,
                          fg=T.TEXT_DIM, bg=T.BG_MID)
        header.pack(anchor="w", padx=8, pady=(6, 2))

        text_frame = tk.Frame(self, bg=T.BG_LIGHT)
        text_frame.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        self._text = tk.Text(
            text_frame, wrap="word", font=T.FONT_SMALL,
            fg=T.TEXT_DIM, bg=T.BG_LIGHT,
            relief="flat", bd=0, highlightthickness=0,
            height=height, padx=6, pady=4, state="disabled",
        )
        scrollbar = tk.Scrollbar(text_frame, orient="vertical",
                                  command=self._text.yview,
                                  bg=T.SCROLLBAR_BG, troughcolor=T.SCROLLBAR_BG)
        self._text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._text.pack(side="left", fill="both", expand=True)

    def set_text(self, text: str) -> None:
        self._text.config(state="normal")
        self._text.delete("1.0", "end")
        self._text.insert("1.0", text[:2000])
        self._text.config(state="disabled")
        self._text.see("end")


# ── Tab bar ──────────────────────────────────────────────

class TabBar(tk.Frame):
    """Custom tab bar matching the cyberpunk theme."""

    def __init__(self, parent, tabs: list[str], on_select=None, **kw):
        kw.setdefault("bg", T.BG_DARK)
        super().__init__(parent, **kw)
        self._on_select = on_select
        self._buttons: dict[str, tk.Button] = {}
        self._active: str = ""

        for name in tabs:
            btn = tk.Button(
                self, text=name,
                font=(T.FONT_FAMILY, T.FONT_SIZE_SM, "bold"),
                fg=T.TEXT_DIM, bg=T.BG_DARK,
                activebackground=T.BG_MID, activeforeground=T.CYAN,
                relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
                command=lambda n=name: self._select(n),
            )
            btn.pack(side="left", padx=1)
            btn.bind("<Enter>", lambda e, b=btn, n=name: (
                b.config(bg=T.BG_MID) if n != self._active else None))
            btn.bind("<Leave>", lambda e, b=btn, n=name: (
                b.config(bg=T.BG_DARK) if n != self._active else None))
            self._buttons[name] = btn

        # Style first tab as active (but don't fire callback yet —
        # parent may not have built tab frames yet)
        if tabs:
            self._active = tabs[0]
            self._buttons[tabs[0]].config(fg=T.CYAN, bg=T.BG_MID)

    def _select(self, name: str) -> None:
        # Deactivate old
        if self._active and self._active in self._buttons:
            self._buttons[self._active].config(fg=T.TEXT_DIM, bg=T.BG_DARK)
        # Activate new
        self._active = name
        self._buttons[name].config(fg=T.CYAN, bg=T.BG_MID)
        if self._on_select:
            self._on_select(name)

    @property
    def active(self) -> str:
        return self._active


# ── Main control pane ────────────────────────────────────

class ControlPane(tk.Frame):
    """Right-side tabbed control column with pinned input."""

    def __init__(self, parent, on_submit=None, on_model_select=None,
                 on_model_refresh=None, on_faux_click=None,
                 on_session_new=None, on_session_select=None,
                 on_session_rename=None, on_session_delete=None,
                 on_session_branch=None, on_sandbox_pick=None,
                 on_docker_toggle=None, on_docker_build=None,
                 on_docker_start=None, on_docker_stop=None,
                 on_docker_destroy=None, **kw):
        kw.setdefault("bg", T.BG_DARK)
        super().__init__(parent, **kw)

        # ── Tab bar ──────────────────────────────────
        self._tab_bar = TabBar(
            self, tabs=["Session", "Sandbox", "Watch"],
            on_select=self._switch_tab,
        )
        self._tab_bar.pack(fill="x", padx=4, pady=(4, 0))

        # Glow line under tabs
        tk.Frame(self, bg=T.CYAN, height=1).pack(fill="x", padx=8, pady=(0, 4))

        # ── Tab content container ────────────────────
        self._tab_container = tk.Frame(self, bg=T.BG_DARK)
        self._tab_container.pack(fill="both", expand=True)

        # ── Build each tab's content ─────────────────
        self._tab_frames: dict[str, tk.Frame] = {}

        # --- SESSION tab ---
        session_tab = tk.Frame(self._tab_container, bg=T.BG_DARK)
        self._tab_frames["Session"] = session_tab

        self.model_picker = ModelPicker(
            session_tab, on_select=on_model_select, on_refresh=on_model_refresh)
        self.model_picker.pack(fill="x", padx=4, pady=(4, 2))

        tk.Frame(session_tab, bg=T.BORDER, height=1).pack(fill="x", padx=8, pady=4)

        self.session_panel = SessionPanel(
            session_tab,
            on_new=on_session_new,
            on_select=on_session_select,
            on_rename=on_session_rename,
            on_delete=on_session_delete,
            on_branch=on_session_branch,
        )
        self.session_panel.pack(fill="both", expand=True, padx=4, pady=2)

        # --- SANDBOX tab ---
        sandbox_tab = tk.Frame(self._tab_container, bg=T.BG_DARK)
        self._tab_frames["Sandbox"] = sandbox_tab

        self.docker_panel = DockerPanel(
            sandbox_tab,
            on_toggle=on_docker_toggle,
            on_build=on_docker_build,
            on_start=on_docker_start,
            on_stop=on_docker_stop,
            on_destroy=on_docker_destroy,
        )
        self.docker_panel.pack(fill="x", padx=4, pady=(4, 2))

        tk.Frame(sandbox_tab, bg=T.BORDER, height=1).pack(fill="x", padx=8, pady=4)

        self.resources = ResourceBlock(sandbox_tab)
        self.resources.pack(fill="x", padx=4, pady=2)

        tk.Frame(sandbox_tab, bg=T.BORDER, height=1).pack(fill="x", padx=8, pady=4)

        sandbox_btn = tk.Button(
            sandbox_tab, text="SANDBOX FOLDER", font=T.FONT_BUTTON,
            fg=T.AMBER, bg=T.BG_LIGHT, activebackground=T.BG_SURFACE,
            activeforeground=T.AMBER, relief="flat", bd=0,
            padx=10, pady=4, cursor="hand2",
            command=on_sandbox_pick if on_sandbox_pick else lambda: None,
        )
        sandbox_btn.pack(fill="x", padx=12, pady=4)
        sandbox_btn.bind("<Enter>", lambda e: sandbox_btn.config(bg=T.BG_SURFACE))
        sandbox_btn.bind("<Leave>", lambda e: sandbox_btn.config(bg=T.BG_LIGHT))

        # --- WATCH tab ---
        watch_tab = tk.Frame(self._tab_container, bg=T.BG_DARK)
        self._tab_frames["Watch"] = watch_tab

        self.response_preview = TextPreview(watch_tab, label="LAST RESPONSE", height=6)
        self.response_preview.pack(fill="both", expand=True, padx=4, pady=(4, 2))

        tk.Frame(watch_tab, bg=T.BORDER, height=1).pack(fill="x", padx=8, pady=4)

        self.prompt_preview = TextPreview(watch_tab, label="LAST PROMPT", height=4)
        self.prompt_preview.pack(fill="both", expand=True, padx=4, pady=2)

        tk.Frame(watch_tab, bg=T.BORDER, height=1).pack(fill="x", padx=8, pady=4)

        self.faux_buttons = FauxButtonPanel(watch_tab, on_click=on_faux_click)
        self.faux_buttons.pack(fill="x", padx=4, pady=(0, 4))

        # ── Pinned bottom section ────────────────────
        tk.Frame(self, bg=T.BORDER, height=1).pack(fill="x", padx=8, pady=4)

        self.input_pane = InputPane(self, on_submit=on_submit)
        self.input_pane.pack(fill="x", padx=4, pady=(2, 4))

        # ── Show first tab ───────────────────────────
        self._switch_tab("Session")

    def _switch_tab(self, name: str) -> None:
        """Show the selected tab, hide others."""
        for tab_name, frame in self._tab_frames.items():
            if tab_name == name:
                frame.place(in_=self._tab_container, x=0, y=0,
                            relwidth=1.0, relheight=1.0)
                frame.lift()
            else:
                frame.place_forget()
