"""
FILE: session_policy_dialog.py
ROLE: Session command policy edit dialog (UI domain).
WHAT IT OWNS:
  - ask_session_policy: present two askstring prompts to collect policy overrides,
    return parsed (adds, removes) lists or None if cancelled.

This module owns the UI interaction pattern for collecting session policy
overrides — what prompts to show, how to present current values, and how to
validate/parse the user's input. It does NOT apply the policy; the caller
(on_session_policy in app_session.py) applies the result to the session store
and engine.

Domain: ui (single domain — valid component)
"""

from __future__ import annotations

from typing import Optional


def ask_session_policy(
    root,
    current_allow_add: list[str],
    current_allow_remove: list[str],
) -> Optional[tuple[list[str], list[str]]]:
    """Show two askstring dialogs to collect session command policy overrides.

    Returns (adds, removes) tuple on confirmation.
    Returns None if the user cancels either dialog.

    args:
        root: tk parent widget for dialog placement.
        current_allow_add: existing extra-allowed commands for this session.
        current_allow_remove: existing restricted commands for this session.
    """
    from tkinter import simpledialog

    add_str = simpledialog.askstring(
        "Session Policy — Extra Allowed",
        "Commands to ADD to allowlist for this session\n"
        "(comma-separated, e.g. 'npm, yarn').\n"
        "Leave blank for defaults.\n"
        "Security-blocked commands (powershell, curl, etc.) cannot be added.",
        initialvalue=", ".join(current_allow_add),
        parent=root,
    )
    if add_str is None:
        return None

    remove_str = simpledialog.askstring(
        "Session Policy — Restricted",
        "Commands to REMOVE from allowlist for this session\n"
        "(comma-separated, e.g. 'git, rm').\n"
        "Leave blank for defaults.",
        initialvalue=", ".join(current_allow_remove),
        parent=root,
    )
    if remove_str is None:
        return None

    adds = [c.strip() for c in add_str.split(",") if c.strip()]
    removes = [c.strip() for c in remove_str.split(",") if c.strip()]
    return adds, removes
