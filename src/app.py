"""Application entry point and composition root.

This file intentionally stays thin. Runtime assembly belongs in
`app_bootstrap.py`; runtime-control and shutdown choreography belong in
`app_lifecycle.py`.
"""

import sys
from pathlib import Path

# Project root is the _MindshardAGENT directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Ensure project root is on sys.path for package imports
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.app_bootstrap import bootstrap_app, ensure_project_root_on_path


def main() -> None:
    bootstrap = bootstrap_app(PROJECT_ROOT)
    bootstrap.log.info("Entering main loop")
    bootstrap.root.mainloop()
    bootstrap.log.info("=== MindshardAGENT shutdown complete ===")


if __name__ == "__main__":
    ensure_project_root_on_path(PROJECT_ROOT)
    main()
