"""Right-side prompt workbench and evidence/source tooling."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from src.ui import theme as T
from src.ui.panes.prompt_workbench_tabs import (
    BagTab,
    InspectTab,
    PromptTab,
    SourcesTab,
    ToolsTab,
)


class PromptWorkbench(tk.Frame):
    """Owns the right prompt/sources/inspect/tools/bag workbench."""

    def __init__(
        self,
        parent,
        *,
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

        self._prompt_text = ""
        self._sources_text = ""
        self._last_prompt_text = ""
        self._last_response_text = ""

        tk.Label(
            self,
            text="PROMPT WORKBENCH",
            font=T.FONT_HEADING,
            fg=T.CYAN,
            bg=T.BG_DARK,
        ).pack(anchor="w", padx=10, pady=(8, 4))

        self._right_notebook = ttk.Notebook(self)
        self._right_notebook.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        self._prompt_tab = PromptTab(self._right_notebook, on_reload_prompt_docs=on_reload_prompt_docs)
        self._sources_tab = SourcesTab(self._right_notebook, on_prompt_source_saved=on_prompt_source_saved)
        self._inspect_tab = InspectTab(self._right_notebook)
        self._tools_tab = ToolsTab(
            self._right_notebook,
            on_reload_tools=on_reload_tools,
            on_set_tool_round_limit=on_set_tool_round_limit,
            initial_tool_round_limit=initial_tool_round_limit,
        )
        self._bag_tab = BagTab(self._right_notebook, on_bag_refresh=on_bag_refresh)

        self._right_notebook.add(self._prompt_tab, text="Prompt")
        self._right_notebook.add(self._sources_tab, text="Sources")
        self._right_notebook.add(self._inspect_tab, text="Inspect")
        self._right_notebook.add(self._tools_tab, text="Tools")
        self._right_notebook.add(self._bag_tab, text="Bag")

        self.prompt_preview = self._prompt_tab.prompt_preview
        self.response_preview = self._prompt_tab.response_preview
        self.system_prompt_preview = self._inspect_tab.system_prompt_preview
        self.inspect_prompt_preview = self._inspect_tab.inspect_prompt_preview
        self.inspect_response_preview = self._inspect_tab.inspect_response_preview
        self.inspect_sources_preview = self._inspect_tab.inspect_sources_preview

        self._update_prompt_summaries()
        self.set_tool_count(0, None)
        self.set_tool_round_limit(initial_tool_round_limit)

    def _update_prompt_summaries(self) -> None:
        self._prompt_tab.update_summaries(
            prompt_text=self._prompt_text,
            sources_text=self._sources_text,
            last_prompt_text=self._last_prompt_text,
            last_response_text=self._last_response_text,
        )

    def set_tool_round_limit(self, value: int) -> None:
        self._tools_tab.set_tool_round_limit(value)

    def set_tool_count(self, count: int, tool_names: list[str] | None = None) -> None:
        self._tools_tab.set_tool_count(count, tool_names)

    def set_prompt_inspector(self, prompt_text: str, sources_text: str) -> None:
        self._prompt_text = prompt_text or ""
        self._sources_text = sources_text or ""
        self._inspect_tab.set_prompt_inspector(self._prompt_text, self._sources_text)
        self._sources_tab.set_sources_text(self._sources_text)
        self._update_prompt_summaries()

    def set_last_prompt(self, text: str) -> None:
        self._last_prompt_text = text or ""
        self._prompt_tab.set_last_prompt(text)
        self._inspect_tab.set_last_prompt(text)
        self._update_prompt_summaries()

    def set_last_response(self, text: str) -> None:
        self._last_response_text = text or ""
        self._prompt_tab.set_last_response(text)
        self._inspect_tab.set_last_response(text)
        self._update_prompt_summaries()

    def set_evidence_bag_display(self, content: str, *, enabled: bool = True) -> None:
        self._bag_tab.set_evidence_bag_display(content, enabled=enabled)

    def context_menu_targets(self) -> list[tk.Text]:
        return [
            self.response_preview.text_widget,
            *self._inspect_tab.context_menu_targets(),
        ]

    @property
    def last_prompt_text(self) -> str:
        return self._last_prompt_text

    @property
    def last_response_text(self) -> str:
        return self._last_response_text
