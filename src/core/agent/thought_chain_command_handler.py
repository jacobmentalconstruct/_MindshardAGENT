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
    if s.ui_facade:
        s.ui_facade.post_system_message(f"Starting thought chain for: {goal}")
    busy_token = s.begin_busy("thought_chain", status_text="Planning...", disable_input=True)

    def _on_round(round_num: int, text: str) -> None:
        if s.ui_facade:
            s.safe_ui(
                lambda rn=round_num, t=text:
                    s.ui_facade.post_system_message(f"[Plan round {rn}]\n{t}")
            )

    def _on_complete(result: dict) -> None:
        def _finish() -> None:
            tasks = result.get("tasks", [])
            if result.get("stopped"):
                completed = int(result.get("completed_rounds", 0) or 0)
                preview = result.get("final_text", "").strip()
                message = f"Plan stopped after {completed} round(s)."
                if preview:
                    message += f"\n\nLast completed round:\n{preview}"
                if s.ui_facade:
                    s.ui_facade.post_system_message(message)
            elif tasks:
                task_lines = "\n".join(
                    f"  {t['number']}. "
                    f"{'[' + t['complexity'] + '] ' if t['complexity'] else ''}"
                    f"{t['text']}"
                    for t in tasks
                )
                if s.ui_facade:
                    s.ui_facade.post_system_message(
                        f"Task list ({len(tasks)} tasks):\n{task_lines}"
                    )
            else:
                if s.ui_facade:
                    s.ui_facade.post_system_message(
                        f"Plan complete (no structured tasks extracted):\n"
                        f"{result.get('final_text', '')}"
                    )
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

    s.engine.run_thought_chain(
        goal=goal,
        depth=depth,
        on_round=_on_round,
        on_complete=_on_complete,
        on_error=_on_error,
    )
