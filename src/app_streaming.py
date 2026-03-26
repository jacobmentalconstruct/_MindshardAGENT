"""Chat submission and streaming callbacks — extracted from app.py."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.registry.session_registry import register_message
from src.core.runtime.runtime_logger import get_logger

if TYPE_CHECKING:
    from src.app_state import AppState

log = get_logger("app_streaming")

FLUSH_INTERVAL_MS = 150


def _busy_status_for_mode(mode_hint: str | None) -> tuple[str, str]:
    normalized = (mode_hint or "").strip().lower()
    if normalized in {"planner_only", "thought_chain"}:
        return normalized, "Planning..."
    if normalized in {"tool_agent", "direct_chat"}:
        return normalized, "Thinking..."
    return "chat", "Thinking..."


def on_submit(s: AppState, text: str) -> None:
    from src.app_prompt import refresh_prompt_inspector, set_prompt_inspector
    from src.app_session import schedule_autosave

    s.activity.info("user", f"Prompt submitted ({len(text)} chars)")
    s.ui_state.last_user_input = text
    s.ui_facade.post_user_message(text)
    s.ui_facade.set_last_prompt(text)
    refresh_prompt_inspector(s, text)
    s.window.set_save_dirty(True)
    mode_hint = s.ui_facade.get_loop_mode() if s.ui_facade else None
    busy_kind, status_text = _busy_status_for_mode(mode_hint)
    busy_token = s.begin_busy(busy_kind, status_text=status_text, disable_input=True)
    s.ui_state.is_streaming = True
    s.streaming_content.clear()

    # Persist user message
    sid = s.active_session["sid"]
    if sid:
        s.session_store.add_message(sid, "user", text)
        if s.active_session["node_id"]:
            register_message(s.registry, s.active_session["node_id"], "user", text[:50])

    # Placeholder assistant card for streaming
    s.ui_facade.begin_chat_stream()
    s.stream_dirty["val"] = False

    # ── Chunked streaming ──────────────────────────
    def _on_token(token: str):
        s.streaming_content.append(token)
        s.stream_dirty["val"] = True

    def _flush_stream():
        """Called on main thread by a repeating timer."""
        if s.stream_dirty["val"]:
            s.stream_dirty["val"] = False
            content = "".join(s.streaming_content)
            s.ui_facade.update_chat_stream(content)
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
        content = result.get("content", "".join(s.streaming_content))

        # ── UI finalization (best-effort — window may be closing) ──
        try:
            s.ui_facade.end_chat_stream(content)
            s.activity.info("chat",
                f"Response: {meta.get('tokens_out', '?')} tokens, {meta.get('time', '?')}")
            s.ui_facade.set_last_response(content)
            set_prompt_inspector(s, result.get("prompt_build"))
        except Exception:
            log.exception("Stream finalization UI error (non-fatal)")

        # ── Persistence — errors here are real failures, not UI noise ──
        try:
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
            log.exception("Stream finalization persistence error — assistant message may not have saved")

        s.end_busy(busy_token, status_text="Ready", enable_input=True)

    def _on_error(err: str):
        s.ui_state.is_streaming = False
        if s.stream_flush_id["id"] is not None:
            s.root.after_cancel(s.stream_flush_id["id"])
            s.stream_flush_id["id"] = None
        s.safe_ui(lambda: _handle_error(err))

    def _handle_error(err):
        s.ui_facade.cancel_chat_stream()
        s.ui_facade.post_system_message(f"Error: {err}")
        s.end_busy(busy_token, status_text="Error — check model connection", enable_input=True)

    s.engine.submit_prompt(
        user_text=text,
        on_token=_on_token,
        on_complete=_on_complete,
        on_error=_on_error,
        mode_hint=mode_hint,
    )
