from __future__ import annotations

import sys
from pathlib import Path
import tkinter as tk


UTILITY_SRC = Path(__file__).resolve().parent
UTILITY_ROOT = UTILITY_SRC.parent
TOOLBOX_ROOT = UTILITY_ROOT.parent.parent

if str(UTILITY_SRC) not in sys.path:
    sys.path.insert(0, str(UTILITY_SRC))
if str(TOOLBOX_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLBOX_ROOT))

from src.core.runtime.runtime_logger import init_logging
from src.ui import theme

from diaglab.controller import DiagnosticController
from diaglab.services import DiagnosticService
from diaglab.view import DiagnosticView


def main() -> None:
    log_dir = UTILITY_ROOT / "_logs"
    output_dir = UTILITY_ROOT / "outputs"
    log_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    init_logging(log_dir=log_dir)

    root = tk.Tk()
    theme.enable_dpi_awareness(root)
    service = DiagnosticService(
        toolbox_root=TOOLBOX_ROOT,
        utility_root=UTILITY_ROOT,
        output_root=output_dir,
    )
    view = DiagnosticView(root, toolbox_root=TOOLBOX_ROOT)
    controller = DiagnosticController(root=root, view=view, service=service)
    controller.start()
    root.mainloop()


if __name__ == "__main__":
    main()
