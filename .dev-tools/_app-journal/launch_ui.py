"""
FILE: launch_ui.py
ROLE: Convenience launcher for the _app-journal Tkinter manager.
WHAT IT DOES: Starts the project journal UI against a project root and shared SQLite store.
HOW TO USE:
  - python _app-journal/launch_ui.py --project-root C:\\path\\to\\project
"""

from __future__ import annotations

from ui.app_journal_ui import main


if __name__ == "__main__":
    raise SystemExit(main())
