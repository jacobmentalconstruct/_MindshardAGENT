"""Intent-level UI facade for app-layer → UI widget bridge.

ROLE: Exposes intent-level operations to callers outside the UI domain.
      Callers say what they want to happen; the facade owns how to make
      the widget hierarchy reflect that intent.

WHAT IT OWNS:
  - set_tool_count: update the sandbox tool count display
  - set_models: update the model picker list
  - set_tool_round_limit: update the tool round limit display
  - refresh_vcs: trigger a VCS panel status refresh
  - wire_vcs: bind a VCS controller to the VCS panel (one-time setup)
  - set_input_enabled: enable/disable the user input field
  - set_input_text: replace the content of the user input field
  - get_input_text: return the current content of the user input field
  - focus_input: move keyboard focus to the user input field
  - attach_context_menus: wire right-click menus to read-only preview widgets
  - clear_prompt_inspector: clear the prompt inspector view
  - cycle_workspace_tabs: cycle workspace tab focus
  - refresh_session_list: update the session panel list
  - post_system_message: append a system-role message to the chat display
  - post_user_message: append a user-role message to the chat display and scroll
  - clear_chat: clear all messages from the chat display
  - load_chat_history: bulk-load a message list into the chat display
  - scroll_chat_to_bottom: scroll the chat display to the most recent message
  - begin_chat_stream: start a new streaming assistant card
  - update_chat_stream: update the active streaming card with accumulated content
  - end_chat_stream: finalize the streaming card with the complete response
  - set_last_prompt: record the most recently submitted prompt text
  - set_last_response: record the most recently completed response text
  - set_docker_status: update docker panel status indicators
  - set_docker_enabled: enable/disable the docker panel controls
  - get_loop_mode: read the user's selected loop mode override (None = auto)
  - set_evidence_bag_display: update the evidence bag explorer tab content

OWNERSHIP CONTRACT:
  - Method names describe caller intent, not widget paths.
  - If a method name contains a widget class name, it is in violation.
  - If control_pane is refactored, only this file changes — not all callers.

Domain: ui only (single domain — valid component)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.ui.gui_main import MainWindow


class UIFacade:
    """Thin intent bridge between application layer and control pane widgets."""

    def __init__(self, window: "MainWindow") -> None:
        self._win = window

    # ── Tool display ──────────────────────────────────────────────────────────

    def set_tool_count(self, count: int, names: list) -> None:
        """Update the sandbox tool count display."""
        self._win.control_pane.set_tool_count(count, names)

    def set_tool_round_limit(self, limit: int) -> None:
        """Update the tool round limit control."""
        self._win.control_pane.set_tool_round_limit(limit)

    # ── Model picker ──────────────────────────────────────────────────────────

    def set_models(self, models: list, primary_model: str) -> None:
        """Update the available model list and select the primary model."""
        self._win.control_pane.model_picker.set_models(models, primary_model)

    # ── VCS panel ─────────────────────────────────────────────────────────────

    def wire_vcs(self, vcs: object) -> None:
        """Bind a VCS controller to the VCS panel (called once at startup)."""
        self._win.control_pane.vcs_panel.set_vcs(vcs)

    def refresh_vcs(self) -> None:
        """Trigger a VCS panel status refresh."""
        self._win.control_pane.vcs_panel.refresh()

    # ── Input field ───────────────────────────────────────────────────────────

    def set_input_enabled(self, enabled: bool) -> None:
        """Enable or disable the user input field."""
        self._win.control_pane.input_pane.set_enabled(enabled)

    def set_input_text(self, text: str) -> None:
        """Replace the content of the user input field."""
        self._win.control_pane.input_pane.set_text(text)

    def get_input_text(self) -> str:
        """Return the current content of the user input field."""
        return self._win.control_pane.input_pane.get_text()

    def focus_input(self) -> None:
        """Move keyboard focus to the user input field."""
        self._win.control_pane.input_pane.focus_input()

    def is_input_enabled(self) -> bool:
        """Return True when the compose input is currently editable."""
        return self._win.control_pane.input_pane.is_enabled()

    def submit_input(self) -> bool:
        """Submit the current compose input if it is non-empty and enabled."""
        return self._win.control_pane.input_pane.submit()

    # ── Context menus ──────────────────────────────────────────────────────────

    def attach_context_menus(
        self,
        on_ask: "Callable[[str], None]",
        on_inject: "Callable[[str], None]",
    ) -> None:
        """Attach right-click context menus to read-only text preview widgets.

        Owns the knowledge of which internal preview widgets exist — callers
        never need to reach into the widget tree.
        """
        from src.ui.widgets.text_context_menu import attach_context_menu

        try:
            preview_widgets = [
                self._win.control_pane.response_preview._text,
                self._win.control_pane.inspect_response_preview._text,
                self._win.control_pane.inspect_prompt_preview._text,
            ]
            for tw in preview_widgets:
                if tw is not None:
                    attach_context_menu(tw, on_ask=on_ask, on_inject=on_inject)
        except Exception:
            pass  # context menus are best-effort; don't block startup

    # ── Prompt inspector ──────────────────────────────────────────────────────

    def clear_prompt_inspector(self) -> None:
        """Clear the prompt inspector view (used after project detach)."""
        self._win.control_pane.set_prompt_inspector("", "")

    # ── Workspace navigation ──────────────────────────────────────────────────

    def cycle_workspace_tabs(self) -> None:
        """Cycle keyboard focus through workspace tabs."""
        self._win.control_pane.cycle_workspace_tabs()

    # ── Session list ──────────────────────────────────────────────────────────

    def refresh_session_list(self, sessions: list, active_sid: str | None) -> None:
        """Update the session panel list to reflect the current session set."""
        self._win.control_pane.session_panel.set_sessions(sessions, active_sid)

    # ── Chat display ──────────────────────────────────────────────────────────

    def post_system_message(self, text: str) -> None:
        """Append a system-role notification to the chat display."""
        self._win.chat_pane.add_message("system", text)

    def post_user_message(self, text: str) -> None:
        """Append a user-role message to the chat display and scroll to bottom."""
        self._win.chat_pane.add_message("user", text)
        self._win.chat_pane.scroll_to_bottom()

    def clear_chat(self) -> None:
        """Clear all messages from the chat display."""
        self._win.chat_pane.clear()

    def load_chat_history(self, messages: list) -> None:
        """Bulk-load a list of {role, content} messages into the chat display."""
        self._win.chat_pane.clear()
        for m in messages:
            self._win.chat_pane.add_message(m["role"], m["content"])
        self._win.chat_pane.scroll_to_bottom()

    def scroll_chat_to_bottom(self) -> None:
        """Scroll the chat display to the most recent message."""
        self._win.chat_pane.scroll_to_bottom()

    def begin_chat_stream(self) -> None:
        """Add a placeholder assistant card and prepare for token-by-token updates."""
        self._win.chat_pane.begin_stream()

    def update_chat_stream(self, content: str) -> None:
        """Update the active streaming card with the accumulated response text."""
        self._win.chat_pane.update_stream(content)

    def end_chat_stream(self, content: str) -> None:
        """Finalize the streaming card with the complete response text."""
        self._win.chat_pane.end_stream(content)

    # ── Prompt / response tracking ────────────────────────────────────────────

    def set_last_prompt(self, text: str) -> None:
        """Record the most recently submitted prompt in the control pane."""
        self._win.control_pane.set_last_prompt(text)

    def set_last_response(self, content: str) -> None:
        """Record the most recently completed response in the control pane."""
        self._win.control_pane.set_last_response(content)

    # ── Docker panel ──────────────────────────────────────────────────────────

    def set_docker_status(
        self, status: str, *, docker_available: bool, image_exists: bool
    ) -> None:
        """Update docker panel status indicators."""
        self._win.control_pane.docker_panel.set_status(
            status, docker_available=docker_available, image_exists=image_exists
        )

    def set_docker_enabled(self, enabled: bool) -> None:
        """Enable or disable the docker panel controls."""
        self._win.control_pane.docker_panel.set_enabled(enabled)

    # ── Loop mode ─────────────────────────────────────────────────────────────

    def get_loop_mode(self) -> str | None:
        """Return the user's loop mode override, or None to use auto-selection.

        When the compose-area loop selector is set to 'auto', returns None so
        the loop selector applies its intent-driven heuristic as normal.
        """
        return self._win.control_pane.get_loop_mode()

    def set_loop_mode(self, mode: str | None) -> str:
        """Set the user's loop mode override and return the applied value."""
        return self._win.control_pane.set_loop_mode(mode)

    # ── Evidence bag explorer ─────────────────────────────────────────────────

    def set_evidence_bag_display(self, content: str, *, enabled: bool = True) -> None:
        """Update the evidence bag explorer tab with current bag contents."""
        self._win.control_pane.set_evidence_bag_display(content, enabled=enabled)

    def snapshot_state(self, *, max_messages: int = 20) -> dict[str, Any]:
        """Return a compact snapshot of visible UI state for automation/testing."""
        cp = self._win.control_pane
        chat_messages = self._win.chat_pane.export_messages(limit=max_messages)
        return {
            "status_text": str(self._win._status_text.cget("text")),
            "model_label": str(self._win._model_label.cget("text")),
            "session_label": str(self._win._session_label.cget("text")),
            "working_label": str(self._win._working_label.cget("text")),
            "source_label": str(self._win._source_label.cget("text")),
            "input_enabled": self.is_input_enabled(),
            "input_text": self.get_input_text(),
            "loop_mode": cp._loop_mode_var.get() if hasattr(cp, "_loop_mode_var") else "auto",
            "project_name": getattr(cp, "_current_project_name", ""),
            "current_model_name": getattr(cp, "_current_model_name", "(none)"),
            "current_session_title": getattr(cp, "_current_session_title", "New Session"),
            "last_prompt": getattr(cp, "_last_prompt_text", ""),
            "last_response": getattr(cp, "_last_response_text", ""),
            "chat_messages": chat_messages,
        }
