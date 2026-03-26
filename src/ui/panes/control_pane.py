"""Primary workstation shell.

This pane now owns the main horizontal work area:
  left rail      -> workspace/session/sandbox/git controls
  center area    -> chat + compose/CLI dock
  right workbench-> prompt context, sources, inspect, tools
"""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from src.core.agent.prompt_sources import default_global_prompt_dir
from src.ui import theme as T

def _noop(): ...  # Sentinel used in place of anonymous `lambda: None` for optional callbacks


from src.ui.panes.chat_pane import ChatPane
from src.ui.panes.cli_pane import CLIPane
from src.ui.panes.input_pane import InputPane
from src.ui.widgets.docker_panel import DockerPanel
from src.ui.widgets.faux_button_panel import FauxButtonPanel
from src.ui.widgets.model_picker import ModelPicker
from src.ui.widgets.session_panel import SessionPanel
from src.ui.widgets.status_light import StatusLight
from src.ui.widgets.vcs_panel import VCSPanel


SASH_OPTS = dict(
    sashwidth=6,
    sashrelief="raised",
    sashpad=1,
)


class ResourceBlock(tk.Frame):
    """CPU/RAM/GPU status display."""

    def __init__(self, parent, **kw):
        kw.setdefault("bg", T.BG_MID)
        super().__init__(parent, **kw)

        header = tk.Label(
            self,
            text="RESOURCES",
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_MID,
        )
        header.pack(anchor="w", padx=8, pady=(6, 2))

        self._status_frame = tk.Frame(self, bg=T.BG_MID)
        self._status_frame.pack(fill="x", padx=8, pady=(0, 6))

        light_row = tk.Frame(self._status_frame, bg=T.BG_MID)
        light_row.pack(fill="x", pady=2)
        self._light = StatusLight(light_row, size=10, color=T.TEXT_DIM)
        self._light.pack(side="left")
        self._status_label = tk.Label(
            light_row,
            text="Idle",
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_MID,
        )
        self._status_label.pack(side="left", padx=6)

        self._cpu_label = tk.Label(
            self._status_frame,
            text="CPU: --",
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_MID,
            anchor="w",
        )
        self._cpu_label.pack(fill="x")
        self._ram_label = tk.Label(
            self._status_frame,
            text="RAM: --",
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_MID,
            anchor="w",
        )
        self._ram_label.pack(fill="x")
        self._gpu_label = tk.Label(
            self._status_frame,
            text="GPU: --",
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_MID,
            anchor="w",
        )
        self._gpu_label.pack(fill="x")

    def update_stats(
        self,
        cpu: float,
        ram_used: float,
        ram_total: float,
        gpu_available: bool,
        vram_used: float,
        vram_total: float,
    ) -> None:
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

    def __init__(
        self,
        parent,
        label: str = "PREVIEW",
        height: int = 5,
        max_chars: int | None = 2000,
        **kw,
    ):
        kw.setdefault("bg", T.BG_MID)
        super().__init__(parent, **kw)
        self._max_chars = max_chars
        self._rendered_text = ""

        header = tk.Label(self, text=label, font=T.FONT_SMALL, fg=T.TEXT_DIM, bg=T.BG_MID)
        header.pack(anchor="w", padx=8, pady=(6, 2))

        text_frame = tk.Frame(self, bg=T.BG_LIGHT)
        text_frame.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        self._text = tk.Text(
            text_frame,
            wrap="word",
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_LIGHT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            height=height,
            padx=6,
            pady=4,
            state="disabled",
        )
        scrollbar = tk.Scrollbar(
            text_frame,
            orient="vertical",
            command=self._text.yview,
            bg=T.SCROLLBAR_BG,
            troughcolor=T.SCROLLBAR_BG,
        )
        self._text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._text.pack(side="left", fill="both", expand=True)

    def set_text(self, text: str) -> None:
        rendered = text if self._max_chars is None else text[: self._max_chars]
        if rendered == self._rendered_text:
            return
        self._rendered_text = rendered
        self._text.config(state="normal")
        self._text.delete("1.0", "end")
        self._text.insert("1.0", rendered)
        self._text.config(state="disabled")
        self._text.see("1.0")


class SummaryCard(tk.Frame):
    """Compact summary card for the right prompt workbench."""

    def __init__(self, parent, title: str, accent: str = T.CYAN, **kw):
        kw.setdefault("bg", T.BG_MID)
        super().__init__(parent, **kw)
        self.configure(highlightthickness=1, highlightbackground=T.BORDER, highlightcolor=T.BORDER)

        header = tk.Frame(self, bg=T.BG_MID)
        header.pack(fill="x", padx=8, pady=(6, 2))
        tk.Label(header, text=title, font=T.FONT_SMALL, fg=accent, bg=T.BG_MID).pack(side="left")

        self._body = tk.Label(
            self,
            text="",
            font=T.FONT_SMALL,
            fg=T.TEXT_PRIMARY,
            bg=T.BG_MID,
            anchor="w",
            justify="left",
            wraplength=260,
        )
        self._body.pack(fill="x", padx=8, pady=(0, 8))
        self.bind("<Configure>", self._sync_wraplength)
        self._body.bind("<Configure>", self._sync_wraplength)

    def set_body(self, text: str) -> None:
        self._body.config(text=text)

    def _sync_wraplength(self, _event=None) -> None:
        width = max(180, self.winfo_width() - 24)
        if int(self._body.cget("wraplength")) != width:
            self._body.config(wraplength=width)


class SourceLayerList(tk.Frame):
    """Structured list of prompt source layers."""

    _LAYER_COLORS = {
        "runtime": T.CYAN,
        "global": T.PURPLE,
        "project_override": T.GREEN,
        "project_meta": T.AMBER,
    }

    def __init__(self, parent, on_select=None, **kw):
        kw.setdefault("bg", T.BG_DARK)
        super().__init__(parent, **kw)
        self._on_select = on_select
        self._selected_key = ""
        self._row_frames: dict[str, tk.Frame] = {}

        self._canvas = tk.Canvas(self, bg=T.BG_DARK, highlightthickness=0, bd=0)
        self._scrollbar = tk.Scrollbar(
            self,
            orient="vertical",
            command=self._canvas.yview,
            bg=T.SCROLLBAR_BG,
            troughcolor=T.SCROLLBAR_BG,
        )
        self._inner = tk.Frame(self._canvas, bg=T.BG_DARK)
        self._window_id = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_resize)

        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

    def _on_inner_configure(self, _event) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_resize(self, event) -> None:
        self._canvas.itemconfigure(self._window_id, width=event.width)

    def set_layers(
        self,
        layers: list[dict],
        warnings: list[str],
        selected_key: str = "",
        notify_selection: bool = True,
    ) -> None:
        for child in self._inner.winfo_children():
            child.destroy()
        self._row_frames.clear()
        self._selected_key = ""

        if warnings:
            warn_card = tk.Frame(
                self._inner,
                bg=T.BG_MID,
                highlightthickness=1,
                highlightbackground=T.AMBER,
                highlightcolor=T.AMBER,
            )
            warn_card.pack(fill="x", padx=4, pady=(4, 6))
            tk.Label(
                warn_card,
                text="WARNINGS",
                font=T.FONT_SMALL,
                fg=T.AMBER,
                bg=T.BG_MID,
            ).pack(anchor="w", padx=8, pady=(6, 2))
            for warning in warnings:
                tk.Label(
                    warn_card,
                    text=f"- {warning}",
                    font=T.FONT_SMALL,
                    fg=T.TEXT_PRIMARY,
                    bg=T.BG_MID,
                    anchor="w",
                    justify="left",
                    wraplength=280,
                ).pack(fill="x", padx=8, pady=(0, 4))

        if not layers:
            tk.Label(
                self._inner,
                text="No prompt source layers loaded yet.",
                font=T.FONT_SMALL,
                fg=T.TEXT_DIM,
                bg=T.BG_DARK,
                anchor="w",
            ).pack(fill="x", padx=8, pady=8)
            return

        for layer_info in layers:
            layer = layer_info.get("layer", "runtime")
            accent = self._LAYER_COLORS.get(layer, T.CYAN)
            row_key = layer_info.get("path") or f"{layer}:{layer_info.get('name', '')}"
            row = tk.Frame(
                self._inner,
                bg=T.BG_MID,
                highlightthickness=1,
                highlightbackground=T.BORDER,
                highlightcolor=T.BORDER,
            )
            row.pack(fill="x", padx=4, pady=4)
            self._row_frames[row_key] = row

            header = tk.Frame(row, bg=T.BG_MID)
            header.pack(fill="x", padx=8, pady=(6, 2))

            tk.Label(
                header,
                text=layer.upper(),
                font=T.FONT_SMALL,
                fg=accent,
                bg=T.BG_MID,
            ).pack(side="left")
            tk.Label(
                header,
                text=layer_info.get("name", "(unnamed)"),
                font=T.FONT_SMALL,
                fg=T.TEXT_BRIGHT,
                bg=T.BG_MID,
            ).pack(side="left", padx=(8, 0))

            tk.Label(
                row,
                text=layer_info.get("path") or "(runtime)",
                font=T.FONT_SMALL,
                fg=T.TEXT_DIM,
                bg=T.BG_MID,
                anchor="w",
                justify="left",
                wraplength=280,
            ).pack(fill="x", padx=8, pady=(0, 8))

            self._bind_row_click(row, layer_info, row_key)

        if layers:
            target_key = selected_key if selected_key in self._row_frames else (
                layers[0].get("path") or f"{layers[0].get('layer', 'runtime')}:{layers[0].get('name', '')}"
            )
            for layer_info in layers:
                candidate_key = layer_info.get("path") or f"{layer_info.get('layer', 'runtime')}:{layer_info.get('name', '')}"
                if candidate_key == target_key:
                    self.select_layer(layer_info, notify=notify_selection)
                    break

    def _bind_row_click(self, widget: tk.Widget, layer_info: dict, row_key: str) -> None:
        def _on_row_click(_e, info=layer_info, key=row_key):
            self.select_layer(info, key=key)
        widget.bind("<Button-1>", _on_row_click)
        for child in widget.winfo_children():
            self._bind_row_click(child, layer_info, row_key)

    def select_layer(self, layer_info: dict, key: str | None = None, notify: bool = True) -> None:
        row_key = key or layer_info.get("path") or f"{layer_info.get('layer', 'runtime')}:{layer_info.get('name', '')}"
        for existing_key, row in self._row_frames.items():
            row.config(
                highlightbackground=T.BORDER_GLOW if existing_key == row_key else T.BORDER,
                highlightcolor=T.BORDER_GLOW if existing_key == row_key else T.BORDER,
            )
        self._selected_key = row_key
        if notify and self._on_select:
            self._on_select(layer_info)

    @property
    def selected_key(self) -> str:
        return self._selected_key


def parse_prompt_sources_text(text: str) -> dict:
    """Parse the prompt source inspector text into structured metadata."""

    metadata = {
        "source_fingerprint": "",
        "prompt_fingerprint": "",
        "warnings": [],
        "layers": [],
    }
    lines = text.splitlines()
    idx = 0
    while idx < len(lines):
        raw = lines[idx]
        line = raw.strip()
        if not line:
            idx += 1
            continue
        if line.startswith("Source fingerprint:"):
            metadata["source_fingerprint"] = line.split(":", 1)[1].strip()
            idx += 1
            continue
        if line.startswith("Prompt fingerprint:"):
            metadata["prompt_fingerprint"] = line.split(":", 1)[1].strip()
            idx += 1
            continue
        if line == "Warnings:":
            idx += 1
            while idx < len(lines):
                warning_line = lines[idx].strip()
                if not warning_line.startswith("- "):
                    break
                metadata["warnings"].append(warning_line[2:].strip())
                idx += 1
            continue
        if line.startswith("[") and "]" in line:
            layer = line[1 : line.index("]")]
            name = line[line.index("]") + 1 :].strip()
            path = ""
            if idx + 1 < len(lines):
                next_line = lines[idx + 1].strip()
                if (
                    next_line
                    and not next_line.startswith("[")
                    and not next_line.startswith("Source fingerprint:")
                    and not next_line.startswith("Prompt fingerprint:")
                    and next_line != "Warnings:"
                    and not next_line.startswith("- ")
                ):
                    path = next_line
                    idx += 1
            metadata["layers"].append({"layer": layer, "name": name, "path": path})
        idx += 1
    return metadata


class ControlPane(tk.Frame):
    """Main workstation shell with left rail, center interaction area, and right workbench."""

    def __init__(
        self,
        parent,
        on_submit=None,
        on_stop=None,
        on_model_select=None,
        on_model_refresh=None,
        on_faux_click=None,
        on_session_new=None,
        on_session_select=None,
        on_session_rename=None,
        on_session_delete=None,
        on_session_branch=None,
        on_session_policy=None,
        on_sandbox_pick=None,
        on_import=None,
        on_edit_project_brief=None,
        on_edit_prompt_overrides=None,
        on_cli_command=None,
        on_docker_toggle=None,
        on_docker_build=None,
        on_docker_start=None,
        on_docker_stop=None,
        on_docker_destroy=None,
        on_vcs_snapshot=None,
        on_reload_tools=None,
        on_reload_prompt_docs=None,
        on_prompt_source_saved=None,
        on_set_tool_round_limit=None,
        on_bag_refresh=None,
        initial_tool_round_limit: int = 12,
        **kw,
    ):
        kw.setdefault("bg", T.BG_DARK)
        super().__init__(parent, **kw)

        self._on_reload_prompt_docs = on_reload_prompt_docs
        self._on_prompt_source_saved = on_prompt_source_saved
        self._on_bag_refresh = on_bag_refresh
        self._prompt_text = ""
        self._sources_text = ""
        self._last_prompt_text = ""
        self._last_response_text = ""
        self._current_model_name = "(none)"
        self._current_session_title = "New Session"
        self._current_project_name = ""
        self._source_layers: list[dict] = []
        self._selected_source: dict | None = None
        self._source_editor_path: Path | None = None
        self._source_editor_dirty = False
        self._source_editor_runtime = False
        self._on_set_tool_round_limit = on_set_tool_round_limit
        self._tool_round_limit_var = tk.IntVar(value=max(1, int(initial_tool_round_limit)))
        self._layout_initialized = False
        self._center_layout_initialized = False
        self._layout_apply_pending = False

        self._main_work_area = tk.PanedWindow(
            self,
            orient="horizontal",
            bg=T.BORDER,
            bd=0,
            **SASH_OPTS,
        )
        self._main_work_area.pack(fill="both", expand=True)

        self._left_workspace_rail = tk.Frame(self._main_work_area, bg=T.BG_DARK)
        self._center_interaction_area = tk.Frame(self._main_work_area, bg=T.BG_DARK)
        self._right_prompt_workbench = tk.Frame(self._main_work_area, bg=T.BG_DARK)

        self._main_work_area.add(self._left_workspace_rail, stretch="never", width=300)
        self._main_work_area.add(self._center_interaction_area, stretch="always", width=780)
        self._main_work_area.add(self._right_prompt_workbench, stretch="never", width=360)
        self._main_work_area.paneconfigure(self._left_workspace_rail, minsize=260)
        self._main_work_area.paneconfigure(self._center_interaction_area, minsize=520)
        self._main_work_area.paneconfigure(self._right_prompt_workbench, minsize=300)

        self._build_left_rail(
            on_model_select=on_model_select,
            on_model_refresh=on_model_refresh,
            on_session_new=on_session_new,
            on_session_select=on_session_select,
            on_session_rename=on_session_rename,
            on_session_delete=on_session_delete,
            on_session_branch=on_session_branch,
            on_session_policy=on_session_policy,
            on_sandbox_pick=on_sandbox_pick,
            on_import=on_import,
            on_edit_project_brief=on_edit_project_brief,
            on_edit_prompt_overrides=on_edit_prompt_overrides,
            on_docker_toggle=on_docker_toggle,
            on_docker_build=on_docker_build,
            on_docker_start=on_docker_start,
            on_docker_stop=on_docker_stop,
            on_docker_destroy=on_docker_destroy,
            on_vcs_snapshot=on_vcs_snapshot,
        )
        self._build_center_area(
            on_submit=on_submit,
            on_stop=on_stop,
            on_faux_click=on_faux_click,
            on_cli_command=on_cli_command,
        )
        self._build_right_workbench(
            on_reload_tools=on_reload_tools,
            on_reload_prompt_docs=on_reload_prompt_docs,
        )

        self.bind("<Configure>", self._on_shell_configure)
        self._schedule_default_layout()
        self.after(120, self._apply_default_layout)
        self.after(320, self._apply_default_layout)

    def _build_left_rail(
        self,
        on_model_select,
        on_model_refresh,
        on_session_new,
        on_session_select,
        on_session_rename,
        on_session_delete,
        on_session_branch,
        on_session_policy,
        on_sandbox_pick,
        on_import,
        on_edit_project_brief,
        on_edit_prompt_overrides,
        on_docker_toggle,
        on_docker_build,
        on_docker_start,
        on_docker_stop,
        on_docker_destroy,
        on_vcs_snapshot,
    ) -> None:
        tk.Label(
            self._left_workspace_rail,
            text="WORKSPACE",
            font=T.FONT_HEADING,
            fg=T.CYAN,
            bg=T.BG_DARK,
        ).pack(anchor="w", padx=10, pady=(8, 4))

        self._left_notebook = ttk.Notebook(self._left_workspace_rail)
        self._left_notebook.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        session_tab = tk.Frame(self._left_notebook, bg=T.BG_DARK)
        sandbox_tab = tk.Frame(self._left_notebook, bg=T.BG_DARK)
        git_tab = tk.Frame(self._left_notebook, bg=T.BG_DARK)
        self._left_notebook.add(session_tab, text="Session")
        self._left_notebook.add(sandbox_tab, text="Sandbox")
        self._left_notebook.add(git_tab, text="Git")

        self._session_summary_card = SummaryCard(
            session_tab,
            title="CURRENT SESSION",
            accent=T.GREEN,
        )
        self._session_summary_card.pack(fill="x", padx=4, pady=(4, 2))

        self.model_picker = ModelPicker(
            session_tab,
            on_select=on_model_select,
            on_refresh=on_model_refresh,
        )
        self.model_picker.pack(fill="x", padx=4, pady=(4, 2))

        tk.Frame(session_tab, bg=T.BORDER, height=1).pack(fill="x", padx=8, pady=4)

        self.session_panel = SessionPanel(
            session_tab,
            on_new=on_session_new,
            on_select=on_session_select,
            on_rename=on_session_rename,
            on_delete=on_session_delete,
            on_branch=on_session_branch,
            on_policy=on_session_policy,
        )
        self.session_panel.pack(fill="both", expand=True, padx=4, pady=2)

        self.docker_panel = DockerPanel(
            sandbox_tab,
            on_toggle=on_docker_toggle,
            on_build=on_docker_build,
            on_start=on_docker_start,
            on_stop=on_docker_stop,
            on_destroy=on_docker_destroy,
        )
        self.docker_panel.pack(fill="x", padx=4, pady=(4, 2))

        self._sandbox_summary_card = SummaryCard(
            sandbox_tab,
            title="PROJECT STATUS",
            accent=T.AMBER,
        )
        self._sandbox_summary_card.pack(fill="x", padx=4, pady=(0, 2))

        tk.Frame(sandbox_tab, bg=T.BORDER, height=1).pack(fill="x", padx=8, pady=4)

        self.resources = ResourceBlock(sandbox_tab)
        self.resources.pack(fill="x", padx=4, pady=2)

        tk.Frame(sandbox_tab, bg=T.BORDER, height=1).pack(fill="x", padx=8, pady=4)

        proj_header = tk.Label(
            sandbox_tab,
            text="PROJECT",
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_DARK,
        )
        proj_header.pack(anchor="w", padx=12, pady=(4, 2))

        proj_name_frame = tk.Frame(sandbox_tab, bg=T.BG_MID, bd=0)
        proj_name_frame.pack(fill="x", padx=8, pady=(0, 4))

        tk.Label(proj_name_frame, text="◆", font=T.FONT_SMALL, fg=T.CYAN, bg=T.BG_MID).pack(
            side="left",
            padx=(8, 4),
            pady=4,
        )
        self._project_name_label = tk.Label(
            proj_name_frame,
            text="No project set",
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_MID,
            anchor="w",
        )
        self._project_name_label.pack(side="left", fill="x", expand=True, pady=4)

        btn_row = tk.Frame(sandbox_tab, bg=T.BG_DARK)
        btn_row.pack(fill="x", padx=8, pady=(0, 4))

        open_btn = tk.Button(
            btn_row,
            text="OPEN PROJECT",
            font=T.FONT_BUTTON,
            fg=T.AMBER,
            bg=T.BG_LIGHT,
            activebackground=T.BG_SURFACE,
            activeforeground=T.AMBER,
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=on_sandbox_pick if on_sandbox_pick else _noop,
        )
        open_btn.pack(side="left", fill="x", expand=True, padx=(0, 2))
        open_btn.bind("<Enter>", lambda e: open_btn.config(bg=T.BG_SURFACE))
        open_btn.bind("<Leave>", lambda e: open_btn.config(bg=T.BG_LIGHT))

        import_btn = tk.Button(
            btn_row,
            text="ADD REF",
            font=T.FONT_BUTTON,
            fg=T.PURPLE,
            bg=T.BG_LIGHT,
            activebackground=T.BG_SURFACE,
            activeforeground=T.PURPLE,
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=on_import if on_import else _noop,
        )
        import_btn.pack(side="left", fill="x", expand=True, padx=(2, 0))
        import_btn.bind("<Enter>", lambda e: import_btn.config(bg=T.BG_SURFACE))
        import_btn.bind("<Leave>", lambda e: import_btn.config(bg=T.BG_LIGHT))

        edit_btn_row = tk.Frame(sandbox_tab, bg=T.BG_DARK)
        edit_btn_row.pack(fill="x", padx=8, pady=(0, 4))

        edit_brief_btn = tk.Button(
            edit_btn_row,
            text="EDIT BRIEF",
            font=T.FONT_BUTTON,
            fg=T.CYAN,
            bg=T.BG_LIGHT,
            activebackground=T.BG_SURFACE,
            activeforeground=T.GREEN,
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=on_edit_project_brief if on_edit_project_brief else _noop,
        )
        edit_brief_btn.pack(side="left", fill="x", expand=True, padx=(0, 2))
        edit_brief_btn.bind("<Enter>", lambda e: edit_brief_btn.config(bg=T.BG_SURFACE))
        edit_brief_btn.bind("<Leave>", lambda e: edit_brief_btn.config(bg=T.BG_LIGHT))

        edit_prompts_btn = tk.Button(
            edit_btn_row,
            text="EDIT PROMPTS",
            font=T.FONT_BUTTON,
            fg=T.AMBER,
            bg=T.BG_LIGHT,
            activebackground=T.BG_SURFACE,
            activeforeground=T.AMBER,
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=on_edit_prompt_overrides if on_edit_prompt_overrides else _noop,
        )
        edit_prompts_btn.pack(side="left", fill="x", expand=True, padx=(2, 0))
        edit_prompts_btn.bind("<Enter>", lambda e: edit_prompts_btn.config(bg=T.BG_SURFACE))
        edit_prompts_btn.bind("<Leave>", lambda e: edit_prompts_btn.config(bg=T.BG_LIGHT))

        self.vcs_panel = VCSPanel(git_tab, on_snapshot=on_vcs_snapshot)
        self.vcs_panel.pack(fill="both", expand=True)

    def _build_center_area(self, on_submit, on_stop, on_faux_click, on_cli_command) -> None:
        tk.Label(
            self._center_interaction_area,
            text="INTERACTION",
            font=T.FONT_HEADING,
            fg=T.CYAN,
            bg=T.BG_DARK,
        ).pack(anchor="w", padx=10, pady=(8, 4))

        self._center_split = tk.PanedWindow(
            self._center_interaction_area,
            orient="vertical",
            bg=T.BORDER,
            bd=0,
            **SASH_OPTS,
        )
        self._center_split.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        self.chat_pane = ChatPane(self._center_split)
        self._center_split.add(self.chat_pane, stretch="always")
        self._center_split.paneconfigure(self.chat_pane, minsize=260)

        bottom_dock_frame = tk.Frame(self._center_split, bg=T.BG_DARK)
        self._center_split.add(bottom_dock_frame, stretch="never", height=250)
        self._center_split.paneconfigure(bottom_dock_frame, minsize=210)

        self._bottom_dock = ttk.Notebook(bottom_dock_frame)
        self._bottom_dock.pack(fill="both", expand=True)

        compose_tab = tk.Frame(self._bottom_dock, bg=T.BG_DARK)
        cli_tab = tk.Frame(self._bottom_dock, bg=T.BG_DARK)
        self._bottom_dock.add(compose_tab, text="Compose")
        self._bottom_dock.add(cli_tab, text="Sandbox CLI")

        compose_status_row = tk.Frame(compose_tab, bg=T.BG_DARK)
        compose_status_row.pack(fill="x", padx=8, pady=(6, 0))
        self._compose_status = tk.Label(
            compose_status_row,
            text="Compose prompt and submit from here.",
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_DARK,
        )
        self._compose_status.pack(side="left")

        # Loop mode override selector — lets user force a specific execution loop
        tk.Label(
            compose_status_row, text="Mode:",
            font=T.FONT_SMALL, fg=T.TEXT_DIM, bg=T.BG_DARK,
        ).pack(side="right", padx=(0, 2))
        self._loop_mode_var = tk.StringVar(value="auto")
        _loop_combo = ttk.Combobox(
            compose_status_row,
            textvariable=self._loop_mode_var,
            values=["auto", "tool_agent", "direct_chat", "planner_only", "thought_chain", "recovery_agent", "review_judge"],
            width=14,
            state="readonly",
        )
        _loop_combo.pack(side="right", padx=(0, 4))

        self.input_pane = InputPane(compose_tab, on_submit=on_submit, on_stop=on_stop)
        self.input_pane.pack(fill="both", expand=True, padx=4, pady=(2, 0))

        self.faux_buttons = FauxButtonPanel(compose_tab, on_click=on_faux_click)
        self.faux_buttons.pack(fill="x", padx=4, pady=(0, 4))

        self.cli_pane = CLIPane(cli_tab, on_command=on_cli_command)
        self.cli_pane.pack(fill="both", expand=True, padx=4, pady=4)

    def _build_right_workbench(self, on_reload_tools, on_reload_prompt_docs) -> None:
        tk.Label(
            self._right_prompt_workbench,
            text="PROMPT WORKBENCH",
            font=T.FONT_HEADING,
            fg=T.CYAN,
            bg=T.BG_DARK,
        ).pack(anchor="w", padx=10, pady=(8, 4))

        self._right_notebook = ttk.Notebook(self._right_prompt_workbench)
        self._right_notebook.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        prompt_tab = tk.Frame(self._right_notebook, bg=T.BG_DARK)
        sources_tab = tk.Frame(self._right_notebook, bg=T.BG_DARK)
        inspect_tab = tk.Frame(self._right_notebook, bg=T.BG_DARK)
        tools_tab = tk.Frame(self._right_notebook, bg=T.BG_DARK)
        bag_tab = tk.Frame(self._right_notebook, bg=T.BG_DARK)
        self._right_notebook.add(prompt_tab, text="Prompt")
        self._right_notebook.add(sources_tab, text="Sources")
        self._right_notebook.add(inspect_tab, text="Inspect")
        self._right_notebook.add(tools_tab, text="Tools")
        self._right_notebook.add(bag_tab, text="Bag")
        self._build_bag_tab(bag_tab)

        self._compiled_summary = SummaryCard(prompt_tab, title="COMPILED PROMPT", accent=T.CYAN)
        self._compiled_summary.pack(fill="x", padx=4, pady=(4, 4))
        self._source_summary = SummaryCard(prompt_tab, title="SOURCE LAYERS", accent=T.PURPLE)
        self._source_summary.pack(fill="x", padx=4, pady=4)

        self.prompt_preview = TextPreview(prompt_tab, label="LAST PROMPT", height=5, max_chars=4000)
        self.prompt_preview.pack(fill="x", padx=4, pady=2)
        self.response_preview = TextPreview(
            prompt_tab,
            label="LAST RESPONSE",
            height=6,
            max_chars=5000,
        )
        self.response_preview.pack(fill="both", expand=True, padx=4, pady=2)

        prompt_action_row = tk.Frame(prompt_tab, bg=T.BG_DARK)
        prompt_action_row.pack(fill="x", padx=8, pady=(0, 8))

        reload_prompt_btn = tk.Button(
            prompt_action_row,
            text="Reload Docs",
            font=T.FONT_BUTTON,
            fg=T.CYAN,
            bg=T.BG_LIGHT,
            activebackground=T.BG_SURFACE,
            activeforeground=T.CYAN,
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=on_reload_prompt_docs if on_reload_prompt_docs else _noop,
        )
        reload_prompt_btn.pack(side="left")
        reload_prompt_btn.bind("<Enter>", lambda e: reload_prompt_btn.config(bg=T.BG_SURFACE))
        reload_prompt_btn.bind("<Leave>", lambda e: reload_prompt_btn.config(bg=T.BG_LIGHT))

        self._inspect_hint = tk.Label(
            prompt_action_row,
            text="Inspect raw prompt text in the Inspect tab.",
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_DARK,
        )
        self._inspect_hint.pack(side="right")

        sources_header = tk.Frame(sources_tab, bg=T.BG_DARK)
        sources_header.pack(fill="x", padx=8, pady=(6, 0))
        tk.Label(
            sources_header,
            text="ACTIVE SOURCE LAYERS",
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_DARK,
        ).pack(side="left")
        tk.Button(
            sources_header,
            text="Reload Docs",
            font=T.FONT_SMALL,
            fg=T.CYAN,
            bg=T.BG_DARK,
            activebackground=T.BG_MID,
            activeforeground=T.CYAN,
            relief="flat",
            bd=0,
            cursor="hand2",
            command=on_reload_prompt_docs if on_reload_prompt_docs else _noop,
        ).pack(side="right")

        self._sources_meta_summary = SummaryCard(sources_tab, title="SOURCE SUMMARY", accent=T.CYAN)
        self._sources_meta_summary.pack(fill="x", padx=4, pady=(2, 4))

        sources_split = tk.PanedWindow(
            sources_tab,
            orient="vertical",
            bg=T.BORDER,
            bd=0,
            **SASH_OPTS,
        )
        sources_split.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        self._source_layer_list = SourceLayerList(sources_split, on_select=self._on_source_layer_selected)
        sources_split.add(self._source_layer_list, stretch="always", minsize=180)

        source_editor_frame = tk.Frame(sources_split, bg=T.BG_DARK)
        sources_split.add(source_editor_frame, stretch="always", minsize=210)

        self._source_editor_summary = SummaryCard(
            source_editor_frame,
            title="SOURCE EDITOR",
            accent=T.GREEN,
        )
        self._source_editor_summary.pack(fill="x", padx=0, pady=(0, 4))

        editor_toolbar = tk.Frame(source_editor_frame, bg=T.BG_DARK)
        editor_toolbar.pack(fill="x", pady=(0, 4))

        self._new_source_btn = self._make_toolbar_btn(editor_toolbar, "New", self._new_source)
        self._new_source_btn.pack(side="left", padx=(0, 4))
        self._load_source_btn = self._make_toolbar_btn(editor_toolbar, "Load", self._load_source)
        self._load_source_btn.pack(side="left", padx=4)
        self._save_source_btn = self._make_toolbar_btn(editor_toolbar, "Save", self._save_source)
        self._save_source_btn.pack(side="left", padx=4)
        self._save_as_source_btn = self._make_toolbar_btn(editor_toolbar, "Save As", self._save_source_as)
        self._save_as_source_btn.pack(side="left", padx=4)
        self._edit_source_btn = self._make_toolbar_btn(editor_toolbar, "Edit", self._edit_source_external)
        self._edit_source_btn.pack(side="left", padx=4)
        self._open_source_folder_btn = self._make_toolbar_btn(
            editor_toolbar,
            "🗁",
            self._open_source_folder,
            width=3,
        )
        self._open_source_folder_btn.pack(side="right", padx=(4, 0))

        editor_frame = tk.Frame(source_editor_frame, bg=T.BG_LIGHT)
        editor_frame.pack(fill="both", expand=True)

        self._source_editor = tk.Text(
            editor_frame,
            wrap="word",
            font=T.FONT_SMALL,
            fg=T.TEXT_INPUT,
            bg=T.BG_LIGHT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=T.BORDER,
            highlightcolor=T.BORDER_GLOW,
            padx=8,
            pady=6,
            insertbackground=T.CYAN,
        )
        source_editor_scroll = tk.Scrollbar(
            editor_frame,
            orient="vertical",
            command=self._source_editor.yview,
            bg=T.SCROLLBAR_BG,
            troughcolor=T.SCROLLBAR_BG,
        )
        self._source_editor.configure(yscrollcommand=source_editor_scroll.set)
        source_editor_scroll.pack(side="right", fill="y")
        self._source_editor.pack(side="left", fill="both", expand=True)
        self._source_editor.bind("<<Modified>>", self._on_source_editor_modified)

        self._inspect_notebook = ttk.Notebook(inspect_tab)
        self._inspect_notebook.pack(fill="both", expand=True, padx=4, pady=4)

        inspect_system_tab = tk.Frame(self._inspect_notebook, bg=T.BG_DARK)
        inspect_prompt_tab = tk.Frame(self._inspect_notebook, bg=T.BG_DARK)
        inspect_response_tab = tk.Frame(self._inspect_notebook, bg=T.BG_DARK)
        inspect_sources_tab = tk.Frame(self._inspect_notebook, bg=T.BG_DARK)
        self._inspect_notebook.add(inspect_system_tab, text="System")
        self._inspect_notebook.add(inspect_prompt_tab, text="Last Prompt")
        self._inspect_notebook.add(inspect_response_tab, text="Last Response")
        self._inspect_notebook.add(inspect_sources_tab, text="Sources")

        self.system_prompt_preview = TextPreview(
            inspect_system_tab,
            label="SYSTEM PROMPT",
            height=20,
            max_chars=40000,
        )
        self.system_prompt_preview.pack(fill="both", expand=True, padx=4, pady=2)

        self.inspect_prompt_preview = TextPreview(
            inspect_prompt_tab,
            label="LAST PROMPT",
            height=20,
            max_chars=20000,
        )
        self.inspect_prompt_preview.pack(fill="both", expand=True, padx=4, pady=2)

        self.inspect_response_preview = TextPreview(
            inspect_response_tab,
            label="LAST RESPONSE",
            height=20,
            max_chars=30000,
        )
        self.inspect_response_preview.pack(fill="both", expand=True, padx=4, pady=2)

        self.inspect_sources_preview = TextPreview(
            inspect_sources_tab,
            label="PROMPT SOURCES",
            height=20,
            max_chars=20000,
        )
        self.inspect_sources_preview.pack(fill="both", expand=True, padx=4, pady=2)

        tools_header_row = tk.Frame(tools_tab, bg=T.BG_DARK)
        tools_header_row.pack(fill="x", padx=8, pady=(6, 2))
        tk.Label(
            tools_header_row,
            text="CUSTOM TOOLS",
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_DARK,
        ).pack(side="left")
        self._tool_count_badge = tk.Label(
            tools_header_row,
            text="0",
            font=(T.FONT_FAMILY, T.FONT_SIZE_SM, "bold"),
            fg=T.BG_DARK,
            bg=T.TEXT_DIM,
            padx=5,
            pady=1,
        )
        self._tool_count_badge.pack(side="left", padx=6)

        reload_btn = tk.Button(
            tools_header_row,
            text="Reload",
            font=T.FONT_SMALL,
            fg=T.CYAN,
            bg=T.BG_DARK,
            activebackground=T.BG_MID,
            activeforeground=T.CYAN,
            relief="flat",
            bd=0,
            cursor="hand2",
            command=on_reload_tools if on_reload_tools else _noop,
        )
        reload_btn.pack(side="right")
        reload_btn.bind("<Enter>", lambda e: reload_btn.config(bg=T.BG_MID))
        reload_btn.bind("<Leave>", lambda e: reload_btn.config(bg=T.BG_DARK))

        tool_settings = tk.Frame(
            tools_tab,
            bg=T.BG_MID,
            highlightthickness=1,
            highlightbackground=T.BORDER,
            highlightcolor=T.BORDER,
        )
        tool_settings.pack(fill="x", padx=8, pady=(0, 8))

        settings_header = tk.Frame(tool_settings, bg=T.BG_MID)
        settings_header.pack(fill="x", padx=8, pady=(6, 2))
        tk.Label(
            settings_header,
            text="TOOL LOOP",
            font=T.FONT_SMALL,
            fg=T.CYAN,
            bg=T.BG_MID,
        ).pack(side="left")

        tk.Label(
            tool_settings,
            text="Max Tool Rounds",
            font=T.FONT_SMALL,
            fg=T.TEXT_PRIMARY,
            bg=T.BG_MID,
            anchor="w",
        ).pack(fill="x", padx=8)

        settings_row = tk.Frame(tool_settings, bg=T.BG_MID)
        settings_row.pack(fill="x", padx=8, pady=(4, 4))

        self._tool_round_spinbox = tk.Spinbox(
            settings_row,
            from_=1,
            to=50,
            width=5,
            textvariable=self._tool_round_limit_var,
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
        self._tool_round_spinbox.pack(side="left")

        apply_limit_btn = self._make_toolbar_btn(
            settings_row,
            "Apply",
            self._apply_tool_round_limit,
        )
        apply_limit_btn.pack(side="left", padx=(8, 0))

        self._tool_round_status = tk.Label(
            tool_settings,
            text="Use STOP or Escape to request a real stop for the active turn.",
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_MID,
            anchor="w",
            justify="left",
            wraplength=300,
        )
        self._tool_round_status.pack(fill="x", padx=8, pady=(0, 8))

        self._tools_list_frame = tk.Frame(tools_tab, bg=T.BG_MID)
        self._tools_list_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._update_workspace_summaries()
        self._update_prompt_summaries()
        self.set_tool_count(0, None)
        self.set_tool_round_limit(self._tool_round_limit_var.get())
        self._set_source_editor_state(
            "Select a file-backed source layer to edit it here.\nRuntime layers remain read-only.",
            editable=False,
            path=None,
            runtime=True,
        )

    def _make_toolbar_btn(self, parent, text: str, command, width: int | None = None) -> tk.Button:
        btn_kwargs = {
            "master": parent,
            "text": text,
            "font": T.FONT_SMALL,
            "fg": T.CYAN,
            "bg": T.BG_LIGHT,
            "activebackground": T.BG_SURFACE,
            "activeforeground": T.GREEN,
            "relief": "flat",
            "bd": 0,
            "padx": 8,
            "pady": 3,
            "cursor": "hand2",
            "command": command,
        }
        if width is not None:
            btn_kwargs["width"] = width
        btn = tk.Button(**btn_kwargs)
        btn.bind("<Enter>", lambda _e, b=btn: b.config(bg=T.BG_SURFACE))
        btn.bind("<Leave>", lambda _e, b=btn: b.config(bg=T.BG_LIGHT))
        return btn

    def _default_source_dir(self) -> Path:
        if self._source_editor_path:
            return self._source_editor_path.parent
        if self._selected_source and self._selected_source.get("path"):
            return Path(self._selected_source["path"]).resolve().parent
        for layer in self._source_layers:
            if layer.get("path"):
                return Path(layer["path"]).resolve().parent
        return default_global_prompt_dir()

    def _set_source_editor_state(
        self,
        text: str,
        *,
        editable: bool,
        path: Path | None,
        runtime: bool,
    ) -> None:
        self._source_editor_runtime = runtime
        self._source_editor_path = path
        self._source_editor.config(state="normal")
        self._source_editor.delete("1.0", "end")
        self._source_editor.insert("1.0", text)
        self._source_editor.edit_modified(False)
        self._source_editor.config(state="normal" if editable else "disabled")
        self._source_editor_dirty = False

        location = str(path) if path else "Unsaved buffer"
        mode = "Read-only" if runtime or not editable else "Editable"
        self._source_editor_summary.set_body(f"{mode}\n{location}")
        self._sync_source_action_states()

    def _sync_source_action_states(self) -> None:
        save_state = "normal" if not self._source_editor_runtime else "disabled"
        self._save_source_btn.config(state=save_state)
        self._save_as_source_btn.config(state=save_state)
        edit_state = "normal" if self._source_editor_path and self._source_editor_path.exists() else "disabled"
        self._edit_source_btn.config(state=edit_state)
        folder_state = "normal" if self._default_source_dir().exists() else "disabled"
        self._open_source_folder_btn.config(state=folder_state)

    def _refresh_prompt_docs(self) -> None:
        if self._on_reload_prompt_docs:
            self._on_reload_prompt_docs()

    def _apply_tool_round_limit(self) -> None:
        try:
            value = max(1, int(self._tool_round_limit_var.get()))
        except (tk.TclError, ValueError):
            self._tool_round_status.config(text="Enter a valid whole number between 1 and 50.", fg=T.RED)
            return
        self._tool_round_limit_var.set(value)
        if self._on_set_tool_round_limit:
            self._on_set_tool_round_limit(value)
        self._tool_round_status.config(
            text=f"Max tool rounds set to {value}. Use STOP or Escape to request a real stop.",
            fg=T.TEXT_DIM,
        )

    def _confirm_discard_unsaved(self) -> bool:
        if not self._source_editor_dirty:
            return True
        return messagebox.askyesno(
            "Discard Unsaved Changes",
            "The source editor has unsaved changes.\n\nDiscard them?",
            parent=self.winfo_toplevel(),
        )

    def _on_source_editor_modified(self, _event=None) -> None:
        if not self._source_editor.edit_modified():
            return
        self._source_editor.edit_modified(False)
        if self._source_editor_runtime:
            return
        self._source_editor_dirty = True
        location = str(self._source_editor_path) if self._source_editor_path else "Unsaved buffer"
        self._source_editor_summary.set_body(f"Modified\n{location}")

    def _on_source_layer_selected(self, layer_info: dict) -> None:
        if not self._confirm_discard_unsaved():
            # Restore previous selection highlight if user cancels.
            if self._selected_source:
                self._source_layer_list.select_layer(self._selected_source, notify=False)
            return

        self._selected_source = dict(layer_info)
        source_path = layer_info.get("path", "")
        if not source_path or source_path == "(runtime)":
            self._set_source_editor_state(
                "This layer is generated at runtime and is not editable from the Sources tab.",
                editable=False,
                path=None,
                runtime=True,
            )
            return

        path = Path(source_path)
        from src.core.project.source_file_service import read_prompt_source
        content, err = read_prompt_source(path)
        if err:
            self._set_source_editor_state(
                f"Could not read source file:\n{err}",
                editable=False,
                path=path,
                runtime=True,
            )
            return

        self._set_source_editor_state(content, editable=True, path=path, runtime=False)

    def _new_source(self) -> None:
        if not self._confirm_discard_unsaved():
            return
        self._selected_source = None
        self._set_source_editor_state("", editable=True, path=None, runtime=False)
        self._source_editor_summary.set_body(f"New source draft\n{self._default_source_dir()}")

    def _load_source(self) -> None:
        if not self._confirm_discard_unsaved():
            return
        path = filedialog.askopenfilename(
            title="Load Prompt Source",
            initialdir=str(self._default_source_dir()),
            filetypes=[("Markdown", "*.md"), ("Text", "*.txt"), ("All Files", "*.*")],
            parent=self.winfo_toplevel(),
        )
        if not path:
            return
        source_path = Path(path)
        from src.core.project.source_file_service import read_prompt_source
        content, err = read_prompt_source(source_path)
        if err:
            messagebox.showerror("Load Failed", err, parent=self.winfo_toplevel())
            return
        self._selected_source = {"layer": "external", "name": source_path.name, "path": str(source_path)}
        self._set_source_editor_state(content, editable=True, path=source_path, runtime=False)

    def _write_source_to_path(self, path: Path) -> bool:
        from src.core.project.source_file_service import write_prompt_source
        content = self._source_editor.get("1.0", "end-1c")
        err = write_prompt_source(path, content)
        if err:
            messagebox.showerror("Save Failed", err, parent=self.winfo_toplevel())
            return False
        self._set_source_editor_state(
            self._source_editor.get("1.0", "end-1c"),
            editable=True,
            path=path,
            runtime=False,
        )
        if self._on_prompt_source_saved:
            self._on_prompt_source_saved(path)
        else:
            self._refresh_prompt_docs()
        return True

    def _save_source(self) -> None:
        if self._source_editor_runtime:
            return
        if self._source_editor_path is None:
            self._save_source_as()
            return
        self._write_source_to_path(self._source_editor_path)

    def _save_source_as(self) -> None:
        if self._source_editor_runtime:
            return
        selected_name = self._source_editor_path.name if self._source_editor_path else "90_local_notes.md"
        path = filedialog.asksaveasfilename(
            title="Save Prompt Source As",
            initialdir=str(self._default_source_dir()),
            initialfile=selected_name,
            defaultextension=".md",
            filetypes=[("Markdown", "*.md"), ("Text", "*.txt"), ("All Files", "*.*")],
            parent=self.winfo_toplevel(),
        )
        if not path:
            return
        target = Path(path)
        if self._write_source_to_path(target):
            self._selected_source = {"layer": "external", "name": target.name, "path": str(target)}

    def _edit_source_external(self) -> None:
        if not self._source_editor_path or not self._source_editor_path.exists():
            return
        from src.core.project.source_file_service import open_in_editor
        open_in_editor(self._source_editor_path)

    def _open_source_folder(self) -> None:
        from src.core.project.source_file_service import open_folder
        open_folder(self._default_source_dir())

    def _apply_default_layout(self) -> None:
        self._layout_apply_pending = False
        total_width = self._main_work_area.winfo_width()
        if total_width >= 1080:
            left_width = max(260, int(total_width * 0.20))
            right_width = max(300, int(total_width * 0.25))
            sash_0 = left_width
            sash_1 = max(sash_0 + 520, total_width - right_width)
            sash_1 = min(sash_1, total_width - 300)
            self._main_work_area.sash_place(0, sash_0, 0)
            self._main_work_area.sash_place(1, sash_1, 0)
            self._layout_initialized = True

        center_height = self._center_split.winfo_height()
        if center_height >= 420:
            self._center_split.sash_place(0, 0, int(center_height * 0.72))
            self._center_layout_initialized = True

    def _on_shell_configure(self, _event=None) -> None:
        if not self._layout_initialized or not self._center_layout_initialized:
            self._schedule_default_layout()

    def _schedule_default_layout(self) -> None:
        if self._layout_apply_pending:
            return
        self._layout_apply_pending = True
        self.after_idle(self._apply_default_layout)

    def _count_source_layers(self) -> int:
        return len([line for line in self._sources_text.splitlines() if line.strip()])

    def _update_workspace_summaries(self) -> None:
        self._session_summary_card.set_body(
            f"Session: {self._current_session_title}\nModel: {self._current_model_name}"
        )
        project_text = self._current_project_name or "No project attached"
        self._sandbox_summary_card.set_body(
            f"{project_text}\nUse Sandbox for project state and prompt overrides."
        )

    def _update_prompt_summaries(self) -> None:
        parsed_sources = parse_prompt_sources_text(self._sources_text)
        prompt_lines = len(self._prompt_text.splitlines()) if self._prompt_text else 0
        prompt_chars = len(self._prompt_text)
        source_layers = len(parsed_sources["layers"])
        last_prompt_chars = len(self._last_prompt_text.strip())
        last_response_chars = len(self._last_response_text.strip())

        if self._prompt_text:
            compiled_text = (
                f"Ready\n{prompt_lines} lines | {prompt_chars} chars"
                f"\nPrompt fp: {parsed_sources['prompt_fingerprint'] or 'n/a'}"
            )
        else:
            compiled_text = "No compiled prompt yet."
        if self._sources_text:
            warning_count = len(parsed_sources["warnings"])
            source_text = (
                f"{source_layers} active layers"
                f"\nWarnings: {warning_count}"
                f"\nSource fp: {parsed_sources['source_fingerprint'] or 'n/a'}"
            )
        else:
            source_text = "No prompt sources loaded."

        self._compiled_summary.set_body(compiled_text)
        self._source_summary.set_body(
            source_text + f"\nLast prompt {last_prompt_chars} chars | response {last_response_chars} chars"
        )

    def set_project_name(self, name: str) -> None:
        self._current_project_name = name or ""
        self._project_name_label.config(
            text=name or "No project set",
            fg=T.TEXT_PRIMARY if name else T.TEXT_DIM,
        )
        self._update_workspace_summaries()

    def set_model_name(self, name: str) -> None:
        self._current_model_name = name or "(none)"
        self._update_workspace_summaries()

    def set_session_title(self, title: str) -> None:
        self._current_session_title = title or "New Session"
        self._update_workspace_summaries()

    def set_tool_round_limit(self, value: int) -> None:
        self._tool_round_limit_var.set(max(1, int(value)))
        self._tool_round_status.config(
            text=f"Max tool rounds set to {max(1, int(value))}. Use STOP or Escape to request a real stop.",
            fg=T.TEXT_DIM,
        )

    def set_tool_count(self, count: int, tool_names: list[str] | None = None) -> None:
        if count > 0:
            self._tool_count_badge.config(text=str(count), bg=T.GREEN, fg=T.BG_DARK)
        else:
            self._tool_count_badge.config(text="0", bg=T.TEXT_DIM, fg=T.BG_DARK)

        for widget in self._tools_list_frame.winfo_children():
            widget.destroy()

        if not tool_names:
            tk.Label(
                self._tools_list_frame,
                text="  No custom tools yet. Agent can create them in .mindshard/tools/",
                font=T.FONT_SMALL,
                fg=T.TEXT_DIM,
                bg=T.BG_MID,
                anchor="w",
                wraplength=280,
                justify="left",
            ).pack(fill="x", padx=4, pady=4)
            return

        for tool_name in tool_names:
            row = tk.Frame(self._tools_list_frame, bg=T.BG_MID)
            row.pack(fill="x", padx=4, pady=1)
            tk.Label(row, text="⚙", font=T.FONT_SMALL, fg=T.CYAN, bg=T.BG_MID).pack(
                side="left",
                padx=(4, 6),
            )
            tk.Label(
                row,
                text=tool_name,
                font=T.FONT_SMALL,
                fg=T.TEXT_PRIMARY,
                bg=T.BG_MID,
                anchor="w",
            ).pack(side="left")

    def set_prompt_inspector(self, prompt_text: str, sources_text: str) -> None:
        self._prompt_text = prompt_text or ""
        self._sources_text = sources_text or ""
        parsed_sources = parse_prompt_sources_text(self._sources_text)
        previous_key = self._source_layer_list.selected_key
        self._source_layers = list(parsed_sources["layers"])
        self.system_prompt_preview.set_text(self._prompt_text)
        self.inspect_sources_preview.set_text(self._sources_text)
        self._sources_meta_summary.set_body(
            (
                f"Layers: {len(parsed_sources['layers'])}"
                f"\nWarnings: {len(parsed_sources['warnings'])}"
                f"\nSource fp: {parsed_sources['source_fingerprint'] or 'n/a'}"
                f"\nPrompt fp: {parsed_sources['prompt_fingerprint'] or 'n/a'}"
            )
            if self._sources_text
            else "No prompt sources loaded."
        )
        self._source_layer_list.set_layers(
            parsed_sources["layers"],
            parsed_sources["warnings"],
            selected_key=previous_key,
            notify_selection=not self._source_editor_dirty,
        )
        self._update_prompt_summaries()

    def set_last_prompt(self, text: str) -> None:
        self._last_prompt_text = text or ""
        self.prompt_preview.set_text(text)
        self.inspect_prompt_preview.set_text(text)
        self._update_prompt_summaries()

    def set_last_response(self, text: str) -> None:
        self._last_response_text = text or ""
        self.response_preview.set_text(text)
        self.inspect_response_preview.set_text(text)
        self._update_prompt_summaries()

    def get_loop_mode(self) -> str | None:
        """Return the user-selected loop mode override, or None for auto-select."""
        val = self._loop_mode_var.get() if hasattr(self, "_loop_mode_var") else "auto"
        return val if val and val != "auto" else None

    def set_loop_mode(self, mode: str | None) -> str:
        """Set the compose-area loop mode override and return the applied value."""
        allowed = {
            "auto",
            "tool_agent",
            "direct_chat",
            "planner_only",
            "thought_chain",
            "recovery_agent",
            "review_judge",
        }
        value = (mode or "auto").strip() or "auto"
        if value not in allowed:
            raise ValueError(f"Unsupported loop mode: {value}")
        self._loop_mode_var.set(value)
        return value

    def set_stop_enabled(self, enabled: bool) -> None:
        self.input_pane.set_stop_enabled(enabled)

    def set_stop_requested(self, requested: bool) -> None:
        self.input_pane.set_stop_requested(requested)

    # ── Evidence Bag Tab ──────────────────────────────────────────────────────

    def _build_bag_tab(self, bag_tab: tk.Frame) -> None:
        """Build the Evidence Bag explorer tab in the right workbench."""
        header_row = tk.Frame(bag_tab, bg=T.BG_DARK)
        header_row.pack(fill="x", padx=8, pady=(6, 2))

        tk.Label(
            header_row,
            text="EVIDENCE BAG",
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_DARK,
        ).pack(side="left")

        self._bag_status_badge = tk.Label(
            header_row,
            text="disabled",
            font=(T.FONT_FAMILY, T.FONT_SIZE_SM, "bold"),
            fg=T.BG_DARK,
            bg=T.TEXT_DIM,
            padx=5,
            pady=1,
        )
        self._bag_status_badge.pack(side="left", padx=6)

        refresh_btn = tk.Button(
            header_row,
            text="Refresh",
            font=T.FONT_SMALL,
            fg=T.CYAN,
            bg=T.BG_DARK,
            activebackground=T.BG_MID,
            activeforeground=T.CYAN,
            relief="flat",
            bd=0,
            padx=8,
            pady=2,
            cursor="hand2",
            command=self._on_bag_refresh if self._on_bag_refresh else _noop,
        )
        refresh_btn.pack(side="right")
        refresh_btn.bind("<Enter>", lambda e: refresh_btn.config(bg=T.BG_MID))
        refresh_btn.bind("<Leave>", lambda e: refresh_btn.config(bg=T.BG_DARK))

        hint = tk.Label(
            bag_tab,
            text="Shows evidence that fell off the STM window (last ~128 tok summary). "
                 "Click Refresh to fetch current bag contents.",
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_DARK,
            wraplength=320,
            justify="left",
        )
        hint.pack(fill="x", padx=8, pady=(0, 4))

        self._bag_preview = TextPreview(
            bag_tab,
            label="BAG CONTENTS",
            height=18,
            max_chars=8000,
        )
        self._bag_preview.pack(fill="both", expand=True, padx=4, pady=(0, 4))

    def set_evidence_bag_display(self, content: str, *, enabled: bool = True) -> None:
        """Update the evidence bag explorer tab with current bag contents.

        Args:
            content: Formatted bag summary text to display.
            enabled: Whether the evidence bag feature is active.
        """
        if not hasattr(self, "_bag_preview"):
            return
        if enabled:
            self._bag_status_badge.config(
                text="active", bg=T.GREEN, fg=T.BG_DARK
            )
        else:
            self._bag_status_badge.config(
                text="disabled", bg=T.TEXT_DIM, fg=T.BG_DARK
            )
        display = content if content else "(bag is empty)"
        self._bag_preview.set_text(display)

    def cycle_workspace_tabs(self) -> None:
        tabs = self._left_notebook.tabs()
        if not tabs:
            return
        current = self._left_notebook.select()
        try:
            index = tabs.index(current)
        except ValueError:
            index = -1
        self._left_notebook.select(tabs[(index + 1) % len(tabs)])
