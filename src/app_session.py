"""Session management callbacks — extracted from app.py."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.agent.model_roles import current_model_roles
import src.core.runtime.action_journal as aj

if TYPE_CHECKING:
    from src.app_state import AppState


def log_model_roles(s: AppState) -> None:
    roles = current_model_roles(s.config)
    recovery_label = roles.get("recovery_planner") if s.config.recovery_planning_enabled else "(disabled)"
    s.activity.info(
        "models",
        "Roles: "
        f"primary={roles.get('primary_chat') or '(none)'}, "
        f"planner={roles.get('planner') or '(none)'}, "
        f"recovery={recovery_label}, "
        f"coding={roles.get('coding') or '(none)'}, "
        f"review={roles.get('review') or '(none)'}, "
        f"probe={roles.get('fast_probe') or '(none)'}, "
        f"embedding={roles.get('embedding') or '(none)'}",
    )


def refresh_session_list(s: AppState) -> None:
    sessions = s.session_store.list_sessions()
    s.window.control_pane.session_panel.set_sessions(sessions, s.active_session["sid"])


def load_session(s: AppState, sid: str) -> None:
    """Switch to a session — load its messages into chat and engine."""
    from src.core.registry.session_registry import register_session

    session = s.session_store.get_session(sid)
    if not session:
        s.activity.error("session", f"Session not found: {sid}")
        return

    s.active_session["sid"] = sid
    s.active_session["node_id"] = register_session(
        s.registry, sid, session["title"], session.get("active_model", ""))

    messages = s.session_store.get_messages(sid)
    history = [{"role": m["role"], "content": m["content"]} for m in messages]
    s.engine.set_history(history)

    s.window.chat_pane.clear()
    for m in messages:
        s.window.chat_pane.add_message(m["role"], m["content"])
    s.window.chat_pane.scroll_to_bottom()

    s.window.set_session_title(session["title"])
    s.window.set_save_dirty(False)
    s.ui_state.session_title = session["title"]

    policy = s.session_store.get_command_policy(sid)
    if policy and s.engine.command_policy:
        s.engine.command_policy.apply_session_overrides(policy)
    elif s.engine.command_policy:
        s.engine.command_policy.clear_session_overrides()

    s.activity.info("session", f"Loaded session: {session['title']}")
    refresh_session_list(s)


def save_current_session(s: AppState) -> None:
    """Persist current chat history to the active session."""
    sid = s.active_session["sid"]
    if not sid:
        return
    s.session_store.save_session(sid, model=s.config.selected_model)
    s.window.set_save_dirty(False)
    s.activity.info("session", "Session saved")


def schedule_autosave(s: AppState) -> None:
    """Debounced autosave — saves 3 seconds after last turn completion."""
    if s.autosave_timer["id"] is not None:
        s.root.after_cancel(s.autosave_timer["id"])
    s.autosave_timer["id"] = s.root.after(3000, lambda: save_current_session(s))


def on_session_new(s: AppState) -> None:
    sid = s.session_store.new_session(
        model=s.config.selected_model,
        sandbox_root=s.config.sandbox_root,
    )
    load_session(s, sid)
    session = s.session_store.get_session(sid)
    title = session["title"] if session else sid
    s.activity.info("session", f"New session: {title}")
    if s.engine.journal:
        s.engine.journal.record(aj.SESSION_START, f"New session: {title}",
                                {"session_id": sid, "title": title})


def on_session_select(s: AppState, sid: str) -> None:
    if sid == s.active_session["sid"]:
        return
    save_current_session(s)
    load_session(s, sid)
    session = s.session_store.get_session(sid)
    if s.engine.journal:
        s.engine.journal.record(aj.SESSION_SWITCH,
            f"Switched to: {session['title'] if session else sid}",
            {"session_id": sid})


def on_session_rename(s: AppState, sid: str, new_title: str) -> None:
    s.session_store.save_session(sid, title=new_title)
    if sid == s.active_session["sid"]:
        s.window.set_session_title(new_title)
        s.ui_state.session_title = new_title
    refresh_session_list(s)
    s.activity.info("session", f"Renamed to: {new_title}")


def on_session_delete(s: AppState, sid: str) -> None:
    s.session_store.delete_session(sid)
    if sid == s.active_session["sid"]:
        remaining = s.session_store.list_sessions()
        if remaining:
            load_session(s, remaining[0]["session_id"])
        else:
            on_session_new(s)
    else:
        refresh_session_list(s)
    s.activity.info("session", "Session deleted")


def on_session_branch(s: AppState, sid: str) -> None:
    new_sid = s.session_store.branch_session(sid)
    load_session(s, new_sid)
    s.activity.info("session", "Session branched")


def on_session_policy(s: AppState, sid: str) -> None:
    """Open a dialog to edit per-session command policy overrides."""
    from tkinter import simpledialog

    current = s.session_store.get_command_policy(sid)
    allow_add = ", ".join(current.get("allow_add", []))
    allow_remove = ", ".join(current.get("allow_remove", []))

    add_str = simpledialog.askstring(
        "Session Policy — Extra Allowed",
        "Commands to ADD to allowlist for this session\n"
        "(comma-separated, e.g. 'npm, yarn').\n"
        "Leave blank for defaults.\n"
        "Security-blocked commands (powershell, curl, etc.) cannot be added.",
        initialvalue=allow_add,
        parent=s.root,
    )
    if add_str is None:
        return

    remove_str = simpledialog.askstring(
        "Session Policy — Restricted",
        "Commands to REMOVE from allowlist for this session\n"
        "(comma-separated, e.g. 'git, rm').\n"
        "Leave blank for defaults.",
        initialvalue=allow_remove,
        parent=s.root,
    )
    if remove_str is None:
        return

    policy = {}
    adds = [c.strip() for c in add_str.split(",") if c.strip()]
    removes = [c.strip() for c in remove_str.split(",") if c.strip()]
    if adds:
        policy["allow_add"] = adds
    if removes:
        policy["allow_remove"] = removes

    s.session_store.set_command_policy(sid, policy)

    if sid == s.active_session["sid"] and s.engine.command_policy:
        if policy:
            s.engine.command_policy.apply_session_overrides(policy)
        else:
            s.engine.command_policy.clear_session_overrides()

    desc = []
    if adds:
        desc.append(f"+{', '.join(adds)}")
    if removes:
        desc.append(f"-{', '.join(removes)}")
    msg = " | ".join(desc) if desc else "defaults"
    s.activity.info("policy", f"Session policy updated: {msg}")
