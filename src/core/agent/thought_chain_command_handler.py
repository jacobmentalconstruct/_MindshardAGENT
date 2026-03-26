"""
FILE: thought_chain_command_handler.py
ROLE: Thought-chain (CTC) command orchestrator.
WHAT IT OWNS:
  - run_thought_chain: wire CTC round/complete/error callbacks, post results to
    the UI activity stream, and record the journal entry on completion.

The goal input dialog stays in app_commands.py (UI I/O in the shim).
This handler owns "what happens after the user submits a goal."

Domains: agent + runtime (2 — valid manager)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import src.core.runtime.action_journal as aj

if TYPE_CHECKING:
    from src.app_state import AppState


def run_thought_chain(s: "AppState", goal: str, depth: int = 3) -> None:
    """Start a CTC spiral for *goal* and wire all UI feedback callbacks.

    Owns:
      - status bar updates throughout
      - per-round system message posting
      - final task-list formatting and posting
      - journal entry on completion
      - error display on failure

    Called after the goal string is validated in the 'Plan' shim.
    """
    from src.app_session import schedule_autosave
    from src.core.registry.session_registry import register_message

    def _persist_message(role: str, content: str, *, model_name: str = "", token_out: int = 0) -> None:
        sid = s.active_session["sid"]
        if not sid or not content.strip():
            return
        s.session_store.add_message(
            sid,
            role,
            content,
            model_name=model_name,
            token_out=token_out,
        )
        if s.active_session["node_id"]:
            register_message(s.registry, s.active_session["node_id"], role, content[:50])

    if s.ui_facade:
        s.ui_facade.post_user_message(goal)
        s.ui_facade.set_last_prompt(goal)
    s.ui_state.last_user_input = goal
    _persist_message("user", goal)
    starting_message = f"Starting thought chain for: {goal}"
    if s.ui_facade:
        s.ui_facade.post_system_message(starting_message)
    busy_token = s.begin_busy("thought_chain", status_text="Planning...", disable_input=True)
    goal_context = _build_goal_context(s)

    def _on_round(round_num: int, text: str) -> None:
        if s.ui_facade:
            s.safe_ui(
                lambda rn=round_num, t=text:
                    s.ui_facade.post_system_message(f"[Plan round {rn}]\n{t}")
            )

    def _on_complete(result: dict) -> None:
        def _finish() -> None:
            tasks = result.get("tasks", [])
            assistant_message = ""
            if result.get("stopped"):
                completed = int(result.get("completed_rounds", 0) or 0)
                preview = result.get("final_text", "").strip()
                reason = str(result.get("stopped_reason", "") or "stopped")
                message = f"Plan stopped after {completed} round(s)."
                if reason and reason != "stopped":
                    message += f"\nReason: {reason}"
                if preview:
                    message += f"\n\nLast completed round:\n{preview}"
                assistant_message = message
                if s.ui_facade:
                    s.ui_facade.post_system_message(message)
            elif tasks:
                task_lines = "\n".join(
                    f"  {t['number']}. "
                    f"{'[' + t['complexity'] + '] ' if t['complexity'] else ''}"
                    f"{t['text']}"
                    for t in tasks
                )
                assistant_message = f"Task list ({len(tasks)} tasks):\n{task_lines}"
                if s.ui_facade:
                    s.ui_facade.post_system_message(assistant_message)
            else:
                assistant_message = (
                    f"Plan complete (no structured tasks extracted):\n"
                    f"{result.get('final_text', '')}"
                )
                if s.ui_facade:
                    s.ui_facade.post_system_message(assistant_message)
            if s.ui_facade:
                s.ui_facade.set_last_response(assistant_message)
            _persist_message(
                "assistant",
                assistant_message,
                model_name=str(result.get("model", "") or ""),
                token_out=int(result.get("tokens_out_total", 0) or 0),
            )
            schedule_autosave(s)
            if s.engine.journal:
                stopped = bool(result.get("stopped"))
                s.engine.journal.record(
                    aj.AGENT_TURN,
                    (
                        f"CTC stopped after {result.get('completed_rounds', 0)} round(s) for '{goal[:50]}'"
                        if stopped else
                        f"CTC plan: {len(tasks)} tasks for '{goal[:50]}'"
                    ),
                    {
                            "goal": goal,
                            "task_count": len(tasks),
                            "stopped": stopped,
                            "stopped_reason": result.get("stopped_reason", ""),
                            "round_stats": result.get("round_stats", []),
                            "tasks": [t["text"] for t in tasks[:10]],
                    },
                )
            s.end_busy(busy_token, status_text="Ready", enable_input=True)

        s.safe_ui(_finish)

    def _on_error(err: str) -> None:
        def _show_error() -> None:
            if s.ui_facade:
                s.ui_facade.post_system_message(f"Plan failed: {err}")
            s.end_busy(busy_token, status_text="Ready", enable_input=True)

        s.safe_ui(_show_error)

    try:
        s.engine.run_thought_chain(
            goal=goal,
            goal_context=goal_context,
            depth=depth,
            on_round=_on_round,
            on_complete=_on_complete,
            on_error=_on_error,
        )
    except Exception as exc:
        _on_error(str(exc))


def _build_goal_context(s: "AppState") -> str:
    """Build a compact software-project anchor for thought-chain planning."""
    lines = [
        "Treat this as a software/codebase planning task unless the user explicitly says it is about a physical system.",
    ]

    project_meta = getattr(s.engine, "project_meta", None)
    if project_meta is not None:
        display_name = project_meta.display_name
        if display_name:
            lines.append(f"Project: {display_name}")
        project_type = project_meta.get("project_type", "")
        if project_type:
            lines.append(f"Project type: {project_type}")
        current_goal = project_meta.get("current_goal", "")
        if current_goal:
            lines.append(f"Current project goal: {current_goal}")
        constraints = project_meta.get("constraints", "")
        if constraints:
            lines.append(f"Constraints: {constraints}")

    sandbox_root = Path(str(s.config.sandbox_root or "")).resolve()
    if sandbox_root.is_dir():
        entries = []
        for child in sorted(sandbox_root.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
            name = child.name
            if name.startswith(".") or name in {"__pycache__", ".venv"}:
                continue
            entries.append(f"{name}/" if child.is_dir() else name)
            if len(entries) >= 10:
                break
        if entries:
            lines.append(f"Top-level workspace entries: {', '.join(entries)}")

    return "\n".join(lines)
