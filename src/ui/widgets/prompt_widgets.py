"""Shared prompt/workbench UI widgets.

These widgets stay UI-local and are reused across the right workbench and
workspace rail panes. They intentionally own presentation only.
"""

from __future__ import annotations

import tkinter as tk

from src.ui import theme as T


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
        from src.ui.widgets.status_light import StatusLight

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

    @property
    def text_widget(self) -> tk.Text:
        return self._text


class SummaryCard(tk.Frame):
    """Compact summary card for workbench and workspace cards."""

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
            layer = line[1: line.index("]")]
            name = line[line.index("]") + 1:].strip()
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
