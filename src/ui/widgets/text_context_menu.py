"""Right-click context menu for text widgets — highlight→ask support.

Attaches a context menu to any tk.Text widget that lets the user:
  - Ask about the selected text (pre-fills the input with the selection)
  - Inject the selection as context into the chat
  - Copy to clipboard (standard)

Usage:
    from src.ui.widgets.text_context_menu import attach_context_menu

    attach_context_menu(
        widget=my_text_widget,
        on_ask=lambda text: ...,     # called with selected text, opens ask dialog
        on_inject=lambda text: ...,  # called with selected text, injects into input
    )

Domain: ui (single domain — valid component)
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable


def attach_context_menu(
    widget: tk.Text,
    on_ask: Callable[[str], None] | None = None,
    on_inject: Callable[[str], None] | None = None,
) -> None:
    """Attach a right-click context menu to a tk.Text widget.

    The menu shows "Ask about this", "Inject as context", and "Copy".
    "Ask about this" and "Inject as context" are only shown if the corresponding
    callbacks are provided. Empty selection disables both.

    Args:
        widget: The tk.Text widget to attach the menu to.
        on_ask: Called with the selected text when "Ask about this" is clicked.
        on_inject: Called with the selected text when "Inject as context" is clicked.
    """
    menu = tk.Menu(widget, tearoff=0, bg="#111827", fg="#e2e8f0",
                   activebackground="#1e293b", activeforeground="#00f0ff",
                   relief="flat", bd=0)

    def _get_selection() -> str:
        try:
            return widget.get(tk.SEL_FIRST, tk.SEL_LAST).strip()
        except tk.TclError:
            return ""

    def _ask_about() -> None:
        text = _get_selection()
        if text and on_ask:
            on_ask(text)

    def _inject_context() -> None:
        text = _get_selection()
        if text and on_inject:
            on_inject(text)

    def _copy() -> None:
        try:
            text = _get_selection() or widget.get("1.0", "end-1c")
            widget.clipboard_clear()
            widget.clipboard_append(text)
        except tk.TclError:
            pass

    def _show_menu(event: tk.Event) -> None:
        menu.delete(0, "end")
        has_selection = bool(_get_selection())

        if on_ask:
            menu.add_command(
                label="Ask about this" if has_selection else "Ask about this (select text first)",
                command=_ask_about,
                state="normal" if has_selection else "disabled",
            )
        if on_inject:
            menu.add_command(
                label="Inject as context" if has_selection else "Inject as context (select text first)",
                command=_inject_context,
                state="normal" if has_selection else "disabled",
            )
        if on_ask or on_inject:
            menu.add_separator()
        menu.add_command(label="Copy", command=_copy)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    widget.bind("<Button-3>", _show_menu)
