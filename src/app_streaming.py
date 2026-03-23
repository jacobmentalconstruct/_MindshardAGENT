"""Chat submission and streaming callbacks — extracted from app.py."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.registry.session_registry import register_message

if TYPE_CHECKING:
    from src.app_state import AppState

FLUSH_INTERVAL_MS = 150


def on_submit(s: AppState, text: str) -> None:
    from src.app_prompt import refresh_prompt_inspector, set_prompt_inspector
    from src.app_session import schedule_autosave

    s.activity.info("user", f"Prompt submitted ({len(text)} chars)")
    s.ui_state.last_user_input = text
    s.window.chat_pane.add_message("user", text)
    s.window.chat_pane.scroll_to_bottom()
    s.window.control_pane.set_last_prompt(text)
    refresh_prompt_inspector(s, text)
    s.window.set_save_dirty(True)
    s.window.set_status("Thinking...")
    s.window.control_pane.input_pane.set_enabled(False)
    s.ui_state.is_streaming = True
    s.streaming_content.clear()

    # Persist user message
    sid = s.active_session["sid"]
    if sid:
        s.session_store.add_message(sid, "user", text)
        if s.active_session["node_id"]:
            register_message(s.registry, s.active_session["node_id"], "user", text[:50])

    # Placeholder assistant card for streaming
    s.window.chat_pane.add_message("assistant", "Thinking...")
    s.window.chat_pane.scroll_to_bottom()
    stream_card = s.window.chat_pane._inner.winfo_children()[-1]
    s.stream_dirty["val"] = False

    # ── Chunked streaming ──────────────────────────
    def _on_token(token: str):
        s.streaming_content.append(token)
        s.stream_dirty["val"] = True

    def _flush_stream():
        """Called on main thread by a repeating timer."""
        if s.stream_dirty["val"]:
            s.stream_dirty["val"] = False
            try:
                content = "".join(s.streaming_content)
                stream_card.update_streaming_content(content)
                s.window.chat_pane._inner.update_idletasks()
                s.window.chat_pane._canvas.configure(
                    scrollregion=s.window.chat_pane._canvas.bbox("all"))
                s.window.chat_pane._canvas.yview_moveto(1.0)
            except Exception:
                pass
        if s.ui_state.is_streaming:
            s.stream_flush_id["id"] = s.root.after(FLUSH_INTERVAL_MS, _flush_stream)

    # Start the flush pump
    s.stream_flush_id["id"] = s.root.after(FLUSH_INTERVAL_MS, _flush_stream)

    def _on_complete(result: dict):
        s.ui_state.is_streaming = False
        if s.stream_flush_id["id"] is not None:
            s.root.after_cancel(s.stream_flush_id["id"])
            s.stream_flush_id["id"] = None
        meta = result.get("metadata", {})
        s.safe_ui(lambda: _finish_stream(meta, result))

    def _finish_stream(meta, result):
        try:
            content = result.get("content", "".join(s.streaming_content))
            stream_card.update_streaming_content(content)
            s.window.chat_pane._inner.update_idletasks()
            s.window.chat_pane._canvas.configure(
                scrollregion=s.window.chat_pane._canvas.bbox("all"))
            s.window.chat_pane._canvas.yview_moveto(1.0)

            s.window.set_status("Ready")
            s.window.control_pane.input_pane.set_enabled(True)
            s.activity.info("chat",
                f"Response: {meta.get('tokens_out', '?')} tokens, {meta.get('time', '?')}")

            s.window.control_pane.set_last_response(content)
            set_prompt_inspector(s, result.get("prompt_build"))

            sid = s.active_session["sid"]
            if sid:
                s.session_store.add_message(
                    sid, "assistant", content,
                    model_name=s.config.selected_model,
                    token_out=int(str(meta.get("tokens_out", "0")).replace("~", "") or 0),
                )
                if s.active_session["node_id"]:
                    register_message(s.registry, s.active_session["node_id"], "assistant", content[:50])

            schedule_autosave(s)
        except Exception:
            pass

    def _on_error(err: str):
        s.ui_state.is_streaming = False
        if s.stream_flush_id["id"] is not None:
            s.root.after_cancel(s.stream_flush_id["id"])
            s.stream_flush_id["id"] = None
        s.safe_ui(lambda: _handle_error(err))

    def _handle_error(err):
        s.window.chat_pane.add_message("system", f"Error: {err}")
        s.window.set_status("Error — check model connection")
        s.window.control_pane.input_pane.set_enabled(True)

    s.engine.submit_prompt(
        user_text=text,
        on_token=_on_token,
        on_complete=_on_complete,
        on_error=_on_error,
    )
