"""Owned prompt workbench tabs."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from src.core.agent.prompt_sources import default_global_prompt_dir
from src.ui import theme as T
from src.ui.widgets.prompt_widgets import (
    SourceLayerList,
    SummaryCard,
    TextPreview,
    parse_prompt_sources_text,
)


def _noop():
    """Sentinel used in place of anonymous lambda no-ops."""


def _nearest_existing_dir(path: Path | None) -> Path | None:
    if path is None:
        return None
    candidate = path if path.is_dir() else path.parent
    while True:
        if candidate.exists():
            return candidate
        if candidate.parent == candidate:
            return None
        candidate = candidate.parent


def _make_toolbar_btn(parent, text: str, command, width: int | None = None) -> tk.Button:
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


class PromptTab(tk.Frame):
    """Prompt summary tab with current prompt/response previews."""

    def __init__(self, parent, *, on_reload_prompt_docs=None, on_open_prompt_lab=None, on_reload_prompt_lab_state=None, **kw):
        kw.setdefault("bg", T.BG_DARK)
        super().__init__(parent, **kw)
        self._on_reload_prompt_docs = on_reload_prompt_docs
        self._on_open_prompt_lab = on_open_prompt_lab
        self._on_reload_prompt_lab_state = on_reload_prompt_lab_state

        self._compiled_summary = SummaryCard(self, title="COMPILED PROMPT", accent=T.CYAN)
        self._compiled_summary.pack(fill="x", padx=4, pady=(4, 4))
        self._source_summary = SummaryCard(self, title="SOURCE LAYERS", accent=T.PURPLE)
        self._source_summary.pack(fill="x", padx=4, pady=4)
        self._prompt_lab_summary = SummaryCard(self, title="PROMPT LAB", accent=T.GREEN)
        self._prompt_lab_summary.pack(fill="x", padx=4, pady=4)

        self.prompt_preview = TextPreview(self, label="LAST PROMPT", height=5, max_chars=4000)
        self.prompt_preview.pack(fill="x", padx=4, pady=2)
        self.response_preview = TextPreview(self, label="LAST RESPONSE", height=6, max_chars=5000)
        self.response_preview.pack(fill="both", expand=True, padx=4, pady=2)

        action_row = tk.Frame(self, bg=T.BG_DARK)
        action_row.pack(fill="x", padx=4, pady=(0, 4))
        _make_toolbar_btn(action_row, "Reload Docs", self._refresh_prompt_docs).pack(side="left")
        _make_toolbar_btn(action_row, "Reload Lab", self._refresh_prompt_lab).pack(side="left", padx=(6, 0))
        _make_toolbar_btn(action_row, "Open Lab", self._open_prompt_lab).pack(side="left", padx=(6, 0))

    def _refresh_prompt_docs(self) -> None:
        if self._on_reload_prompt_docs:
            self._on_reload_prompt_docs()

    def _refresh_prompt_lab(self) -> None:
        if self._on_reload_prompt_lab_state:
            self._on_reload_prompt_lab_state()

    def _open_prompt_lab(self) -> None:
        if self._on_open_prompt_lab:
            self._on_open_prompt_lab()

    def update_summaries(
        self,
        *,
        prompt_text: str,
        sources_text: str,
        prompt_lab_summary: str,
        last_prompt_text: str,
        last_response_text: str,
    ) -> None:
        parsed_sources = parse_prompt_sources_text(sources_text)
        prompt_lines = len(prompt_text.splitlines()) if prompt_text else 0
        prompt_chars = len(prompt_text)
        source_layers = len(parsed_sources["layers"])
        last_prompt_chars = len(last_prompt_text.strip())
        last_response_chars = len(last_response_text.strip())

        if prompt_text:
            compiled_text = (
                f"Ready\n{prompt_lines} lines | {prompt_chars} chars"
                f"\nPrompt fp: {parsed_sources['prompt_fingerprint'] or 'n/a'}"
            )
        else:
            compiled_text = "No compiled prompt yet."
        if sources_text:
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
        self._prompt_lab_summary.set_body(prompt_lab_summary or "Prompt Lab state not loaded yet.")

    def set_last_prompt(self, text: str) -> None:
        self.prompt_preview.set_text(text)

    def set_last_response(self, text: str) -> None:
        self.response_preview.set_text(text)


class SourcesTab(tk.Frame):
    """Sources tab with layer list and file-backed editor workflow."""

    def __init__(self, parent, *, on_prompt_source_saved=None, **kw):
        kw.setdefault("bg", T.BG_DARK)
        super().__init__(parent, **kw)
        self._on_prompt_source_saved = on_prompt_source_saved
        self._sources_text = ""
        self._source_layers: list[dict] = []
        self._selected_source: dict | None = None
        self._source_editor_path: Path | None = None
        self._source_editor_dirty = False
        self._source_editor_runtime = False

        top_row = tk.Frame(self, bg=T.BG_DARK)
        top_row.pack(fill="x", padx=4, pady=(4, 2))

        self._sources_meta_summary = SummaryCard(top_row, title="SOURCE STACK", accent=T.CYAN)
        self._sources_meta_summary.pack(side="left", fill="both", expand=True, padx=(0, 4))

        self._source_editor_summary = SummaryCard(top_row, title="EDITOR", accent=T.GREEN)
        self._source_editor_summary.pack(side="left", fill="both", expand=True)

        self._source_layer_list = SourceLayerList(self, on_select=self._on_source_layer_selected)
        self._source_layer_list.pack(fill="both", expand=True, padx=4, pady=2)

        toolbar = tk.Frame(self, bg=T.BG_DARK)
        toolbar.pack(fill="x", padx=4, pady=(2, 2))

        self._new_source_btn = _make_toolbar_btn(toolbar, "New", self._new_source)
        self._new_source_btn.pack(side="left")
        self._load_source_btn = _make_toolbar_btn(toolbar, "Load", self._load_source)
        self._load_source_btn.pack(side="left", padx=(4, 0))
        self._save_source_btn = _make_toolbar_btn(toolbar, "Save", self._save_source)
        self._save_source_btn.pack(side="left", padx=(4, 0))
        self._save_as_source_btn = _make_toolbar_btn(toolbar, "Save As", self._save_source_as)
        self._save_as_source_btn.pack(side="left", padx=(4, 0))
        self._edit_source_btn = _make_toolbar_btn(toolbar, "Open External", self._edit_source_external)
        self._edit_source_btn.pack(side="left", padx=(12, 0))
        self._open_source_folder_btn = _make_toolbar_btn(toolbar, "Open Folder", self._open_source_folder)
        self._open_source_folder_btn.pack(side="left", padx=(4, 0))

        editor_frame = tk.Frame(
            self,
            bg=T.BG_LIGHT,
            highlightthickness=1,
            highlightbackground=T.BORDER,
            highlightcolor=T.BORDER_GLOW,
        )
        editor_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))

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

        self._set_source_editor_state(
            "Select a file-backed source layer to edit it here.\nRuntime layers remain read-only.",
            editable=False,
            path=None,
            runtime=True,
        )
        self.set_sources_text("")

    def _default_source_dir(self) -> Path:
        existing = _nearest_existing_dir(self._source_editor_path)
        if existing:
            return existing
        if self._selected_source and self._selected_source.get("path"):
            existing = _nearest_existing_dir(Path(self._selected_source["path"]).resolve())
            if existing:
                return existing
        for layer in self._source_layers:
            if layer.get("path"):
                existing = _nearest_existing_dir(Path(layer["path"]).resolve())
                if existing:
                    return existing
        return default_global_prompt_dir()

    def _set_source_editor_state(self, text: str, *, editable: bool, path: Path | None, runtime: bool) -> None:
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
            if not path.exists():
                err = (
                    "Source file is missing on disk.\n"
                    "Use Open Folder to inspect the nearest existing directory, "
                    "or Save As to recreate it.\n\n"
                    f"{err}"
                )
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
        self._set_source_editor_state(content, editable=True, path=path, runtime=False)
        if self._on_prompt_source_saved:
            self._on_prompt_source_saved(path)
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

        folder = self._default_source_dir()
        err = open_folder(folder)
        if err:
            messagebox.showerror("Open Folder Failed", err, parent=self.winfo_toplevel())

    def set_sources_text(self, sources_text: str) -> None:
        self._sources_text = sources_text or ""
        parsed_sources = parse_prompt_sources_text(self._sources_text)
        previous_key = self._source_layer_list.selected_key
        self._source_layers = list(parsed_sources["layers"])
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
        self._sync_source_action_states()


class InspectTab(tk.Frame):
    """Inspect tab with system/prompt/response/source previews."""

    def __init__(self, parent, **kw):
        kw.setdefault("bg", T.BG_DARK)
        super().__init__(parent, **kw)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=4, pady=4)

        inspect_system_tab = tk.Frame(notebook, bg=T.BG_DARK)
        inspect_prompt_tab = tk.Frame(notebook, bg=T.BG_DARK)
        inspect_response_tab = tk.Frame(notebook, bg=T.BG_DARK)
        inspect_sources_tab = tk.Frame(notebook, bg=T.BG_DARK)
        notebook.add(inspect_system_tab, text="System")
        notebook.add(inspect_prompt_tab, text="Last Prompt")
        notebook.add(inspect_response_tab, text="Last Response")
        notebook.add(inspect_sources_tab, text="Sources")

        self.system_prompt_preview = TextPreview(inspect_system_tab, label="SYSTEM PROMPT", height=20, max_chars=40000)
        self.system_prompt_preview.pack(fill="both", expand=True, padx=4, pady=2)
        self.inspect_prompt_preview = TextPreview(inspect_prompt_tab, label="LAST PROMPT", height=20, max_chars=20000)
        self.inspect_prompt_preview.pack(fill="both", expand=True, padx=4, pady=2)
        self.inspect_response_preview = TextPreview(inspect_response_tab, label="LAST RESPONSE", height=20, max_chars=30000)
        self.inspect_response_preview.pack(fill="both", expand=True, padx=4, pady=2)
        self.inspect_sources_preview = TextPreview(inspect_sources_tab, label="PROMPT SOURCES", height=20, max_chars=20000)
        self.inspect_sources_preview.pack(fill="both", expand=True, padx=4, pady=2)

    def set_prompt_inspector(self, prompt_text: str, sources_text: str) -> None:
        self.system_prompt_preview.set_text(prompt_text)
        self.inspect_sources_preview.set_text(sources_text)

    def set_last_prompt(self, text: str) -> None:
        self.inspect_prompt_preview.set_text(text)

    def set_last_response(self, text: str) -> None:
        self.inspect_response_preview.set_text(text)

    def context_menu_targets(self) -> list[tk.Text]:
        return [
            self.inspect_response_preview.text_widget,
            self.inspect_prompt_preview.text_widget,
        ]


class ToolsTab(tk.Frame):
    """Tools tab with discovered tools and round-limit controls."""

    def __init__(self, parent, *, on_reload_tools=None, on_set_tool_round_limit=None, initial_tool_round_limit: int = 12, **kw):
        kw.setdefault("bg", T.BG_DARK)
        super().__init__(parent, **kw)
        self._on_set_tool_round_limit = on_set_tool_round_limit
        self._tool_round_limit_var = tk.IntVar(value=max(1, int(initial_tool_round_limit)))

        header_row = tk.Frame(self, bg=T.BG_DARK)
        header_row.pack(fill="x", padx=8, pady=(6, 2))
        tk.Label(header_row, text="CUSTOM TOOLS", font=T.FONT_SMALL, fg=T.TEXT_DIM, bg=T.BG_DARK).pack(side="left")
        self._tool_count_badge = tk.Label(
            header_row,
            text="0",
            font=(T.FONT_FAMILY, T.FONT_SIZE_SM, "bold"),
            fg=T.BG_DARK,
            bg=T.TEXT_DIM,
            padx=5,
            pady=1,
        )
        self._tool_count_badge.pack(side="left", padx=6)

        reload_btn = tk.Button(
            header_row,
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
        reload_btn.bind("<Enter>", lambda _e: reload_btn.config(bg=T.BG_MID))
        reload_btn.bind("<Leave>", lambda _e: reload_btn.config(bg=T.BG_DARK))

        tool_settings = tk.Frame(
            self,
            bg=T.BG_MID,
            highlightthickness=1,
            highlightbackground=T.BORDER,
            highlightcolor=T.BORDER,
        )
        tool_settings.pack(fill="x", padx=8, pady=(0, 8))

        settings_header = tk.Frame(tool_settings, bg=T.BG_MID)
        settings_header.pack(fill="x", padx=8, pady=(6, 2))
        tk.Label(settings_header, text="TOOL LOOP", font=T.FONT_SMALL, fg=T.CYAN, bg=T.BG_MID).pack(side="left")
        tk.Label(tool_settings, text="Max Tool Rounds", font=T.FONT_SMALL, fg=T.TEXT_PRIMARY, bg=T.BG_MID, anchor="w").pack(fill="x", padx=8)

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
        _make_toolbar_btn(settings_row, "Apply", self._apply_tool_round_limit).pack(side="left", padx=(8, 0))

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

        self._tools_list_frame = tk.Frame(self, bg=T.BG_MID)
        self._tools_list_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

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

    def set_tool_round_limit(self, value: int) -> None:
        value = max(1, int(value))
        self._tool_round_limit_var.set(value)
        self._tool_round_status.config(
            text=f"Max tool rounds set to {value}. Use STOP or Escape to request a real stop.",
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
            tk.Label(row, text="⚙", font=T.FONT_SMALL, fg=T.CYAN, bg=T.BG_MID).pack(side="left", padx=(4, 6))
            tk.Label(row, text=tool_name, font=T.FONT_SMALL, fg=T.TEXT_PRIMARY, bg=T.BG_MID, anchor="w").pack(side="left")


class BagTab(tk.Frame):
    """Evidence bag tab."""

    def __init__(self, parent, *, on_bag_refresh=None, **kw):
        kw.setdefault("bg", T.BG_DARK)
        super().__init__(parent, **kw)

        header_row = tk.Frame(self, bg=T.BG_DARK)
        header_row.pack(fill="x", padx=8, pady=(6, 2))
        tk.Label(header_row, text="EVIDENCE BAG", font=T.FONT_SMALL, fg=T.TEXT_DIM, bg=T.BG_DARK).pack(side="left")
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
            command=on_bag_refresh if on_bag_refresh else _noop,
        )
        refresh_btn.pack(side="right")
        refresh_btn.bind("<Enter>", lambda _e: refresh_btn.config(bg=T.BG_MID))
        refresh_btn.bind("<Leave>", lambda _e: refresh_btn.config(bg=T.BG_DARK))

        tk.Label(
            self,
            text="Shows evidence that fell off the STM window (last ~128 tok summary). Click Refresh to fetch current bag contents.",
            font=T.FONT_SMALL,
            fg=T.TEXT_DIM,
            bg=T.BG_DARK,
            wraplength=320,
            justify="left",
        ).pack(fill="x", padx=8, pady=(0, 4))

        self._bag_preview = TextPreview(self, label="BAG CONTENTS", height=18, max_chars=8000)
        self._bag_preview.pack(fill="both", expand=True, padx=4, pady=(0, 4))

    def set_evidence_bag_display(self, content: str, *, enabled: bool = True) -> None:
        if enabled:
            self._bag_status_badge.config(text="active", bg=T.GREEN, fg=T.BG_DARK)
        else:
            self._bag_status_badge.config(text="disabled", bg=T.TEXT_DIM, fg=T.BG_DARK)
        self._bag_preview.set_text(content if content else "(bag is empty)")
