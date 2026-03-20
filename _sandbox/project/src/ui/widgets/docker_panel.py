"""Docker sandbox control panel — user-only container lifecycle management.

Displays Docker status and provides buttons to enable/disable Docker mode,
build the image, and start/stop/destroy the container. The agent never sees
or interacts with this panel.
"""

import tkinter as tk
from src.ui import theme as T
from src.ui.widgets.status_light import StatusLight


class DockerPanel(tk.Frame):
    """Docker sandbox controls — user-only panel."""

    def __init__(self, parent, on_toggle=None, on_build=None,
                 on_start=None, on_stop=None, on_destroy=None, **kw):
        kw.setdefault("bg", T.BG_MID)
        super().__init__(parent, **kw)

        self._on_toggle = on_toggle
        self._on_build = on_build
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_destroy = on_destroy

        # Header row with label + status light
        header_row = tk.Frame(self, bg=T.BG_MID)
        header_row.pack(fill="x", padx=8, pady=(6, 2))

        tk.Label(header_row, text="DOCKER SANDBOX", font=T.FONT_SMALL,
                 fg=T.TEXT_DIM, bg=T.BG_MID).pack(side="left")

        self._light = StatusLight(header_row, size=8, color=T.TEXT_DIM)
        self._light.pack(side="right", padx=(4, 0))
        self._status_label = tk.Label(header_row, text="Unchecked",
                                       font=T.FONT_SMALL, fg=T.TEXT_DIM,
                                       bg=T.BG_MID)
        self._status_label.pack(side="right")

        # Enable/disable toggle
        self._enabled_var = tk.BooleanVar(value=False)
        toggle_row = tk.Frame(self, bg=T.BG_MID)
        toggle_row.pack(fill="x", padx=8, pady=(2, 2))

        self._toggle_cb = tk.Checkbutton(
            toggle_row, text="Enable Docker mode",
            variable=self._enabled_var,
            font=T.FONT_SMALL, fg=T.TEXT_PRIMARY, bg=T.BG_MID,
            activebackground=T.BG_MID, activeforeground=T.CYAN,
            selectcolor=T.BG_LIGHT, highlightthickness=0,
            command=self._handle_toggle,
        )
        self._toggle_cb.pack(side="left")

        # Button row
        btn_row = tk.Frame(self, bg=T.BG_MID)
        btn_row.pack(fill="x", padx=8, pady=(2, 6))

        self._build_btn = self._make_btn(btn_row, "Build", T.CYAN, self._handle_build)
        self._build_btn.pack(side="left", padx=(0, 3), expand=True, fill="x")

        self._start_btn = self._make_btn(btn_row, "Start", T.GREEN, self._handle_start)
        self._start_btn.pack(side="left", padx=3, expand=True, fill="x")

        self._stop_btn = self._make_btn(btn_row, "Stop", T.AMBER, self._handle_stop)
        self._stop_btn.pack(side="left", padx=3, expand=True, fill="x")

        self._destroy_btn = self._make_btn(btn_row, "Nuke", T.RED, self._handle_destroy)
        self._destroy_btn.pack(side="left", padx=(3, 0), expand=True, fill="x")

        # Info line
        self._info_label = tk.Label(self, text="Container not checked",
                                     font=T.FONT_SMALL, fg=T.TEXT_DIM,
                                     bg=T.BG_MID, anchor="w")
        self._info_label.pack(fill="x", padx=8, pady=(0, 6))

    def _make_btn(self, parent, text, color, command):
        btn = tk.Button(
            parent, text=text, font=(T.FONT_FAMILY, T.FONT_SIZE_SM, "bold"),
            fg=color, bg=T.BG_LIGHT, activebackground=T.BG_SURFACE,
            activeforeground=color, relief="flat", bd=0,
            padx=4, pady=2, cursor="hand2", command=command,
        )
        btn.bind("<Enter>", lambda e, b=btn: b.config(bg=T.BG_SURFACE))
        btn.bind("<Leave>", lambda e, b=btn: b.config(bg=T.BG_LIGHT))
        return btn

    # ── State update methods (called by app.py) ──────────

    def set_status(self, status: str, docker_available: bool = True,
                   image_exists: bool = False) -> None:
        """Update the status display. status is container_status() result."""
        if not docker_available:
            self._light.set_color(T.RED)
            self._status_label.config(text="Docker N/A", fg=T.RED)
            self._info_label.config(text="Docker Desktop not running")
            return

        if status == "running":
            self._light.set_color(T.GREEN)
            self._status_label.config(text="Running", fg=T.GREEN)
            self._info_label.config(text="Container active — agent uses Linux bash")
        elif status == "exited" or status == "stopped":
            self._light.set_color(T.AMBER)
            self._status_label.config(text="Stopped", fg=T.AMBER)
            self._info_label.config(text="Container stopped — press Start")
        elif status == "not_found":
            if image_exists:
                self._light.set_color(T.TEXT_DIM)
                self._status_label.config(text="No container", fg=T.TEXT_DIM)
                self._info_label.config(text="Image ready — press Start to create container")
            else:
                self._light.set_color(T.TEXT_DIM)
                self._status_label.config(text="No image", fg=T.TEXT_DIM)
                self._info_label.config(text="Press Build to create the sandbox image")
        else:
            self._light.set_color(T.RED)
            self._status_label.config(text=status, fg=T.RED)
            self._info_label.config(text=f"Unexpected state: {status}")

    def set_enabled(self, enabled: bool) -> None:
        """Set the checkbox state without triggering the callback."""
        self._enabled_var.set(enabled)

    # ── Internal handlers ────────────────────────────────

    def _handle_toggle(self):
        if self._on_toggle:
            self._on_toggle(self._enabled_var.get())

    def _handle_build(self):
        if self._on_build:
            self._info_label.config(text="Building image... (may take a minute)")
            self._on_build()

    def _handle_start(self):
        if self._on_start:
            self._info_label.config(text="Starting container...")
            self._on_start()

    def _handle_stop(self):
        if self._on_stop:
            self._on_stop()

    def _handle_destroy(self):
        if self._on_destroy:
            self._on_destroy()
