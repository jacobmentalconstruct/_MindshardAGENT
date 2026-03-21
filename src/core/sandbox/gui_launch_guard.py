"""Heuristics for detecting likely local GUI launches from CLI commands or scripts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shlex


PYTHON_LAUNCHERS = {"python", "python.exe", "pythonw", "pythonw.exe", "py", "py.exe"}
TK_MARKERS = ("import tkinter", "from tkinter", "tk.Tk(", "ttk.", "Tk()")


@dataclass(frozen=True)
class GuiLaunchMatch:
    """Metadata describing a likely local GUI launch request."""

    reason: str
    target_path: str = ""
    module_name: str = ""


def detect_gui_script(path: str | Path) -> GuiLaunchMatch | None:
    """Return match details when a Python file looks like a Tkinter GUI script."""

    script_path = Path(path).resolve()
    if script_path.suffix.lower() not in {".py", ".pyw"}:
        return None
    if not script_path.exists():
        return None
    if _file_uses_tkinter(script_path):
        return GuiLaunchMatch(reason="python_script_tkinter", target_path=str(script_path))
    return None


def detect_gui_launch(command: str, root: str | Path, cwd: str | Path | None = None) -> GuiLaunchMatch | None:
    """Return match details when a CLI command is likely to open a GUI window."""

    try:
        tokens = shlex.split(command, posix=False)
    except ValueError:
        tokens = command.strip().split()

    if not tokens:
        return None

    launcher = Path(tokens[0]).name.lower()
    work_dir = Path(cwd).resolve() if cwd else Path(root).resolve()
    root_path = Path(root).resolve()

    if launcher in PYTHON_LAUNCHERS:
        candidate = _python_target(tokens)
        if candidate is None:
            return None
        if candidate[0] == "module":
            module_name = candidate[1]
            if module_name.lower() == "tkinter":
                return GuiLaunchMatch(reason="python_tkinter_module", module_name=module_name)
            return None

        script_path = _resolve_script(candidate[1], work_dir, root_path)
        if not script_path:
            return None
        return detect_gui_script(script_path)

    direct_path = _resolve_script(tokens[0], work_dir, root_path)
    if direct_path and direct_path.exists() and direct_path.suffix.lower() in {".py", ".pyw"}:
        match = detect_gui_script(direct_path)
        if match:
            return GuiLaunchMatch(reason="direct_python_script_tkinter", target_path=match.target_path)

    return None


def _python_target(tokens: list[str]) -> tuple[str, str] | None:
    idx = 1
    while idx < len(tokens):
        token = tokens[idx]
        if token == "-m" and idx + 1 < len(tokens):
            return ("module", tokens[idx + 1])
        if token.startswith("-"):
            idx += 1
            continue
        return ("script", token)
    return None


def _resolve_script(token: str, cwd: Path, root: Path) -> Path | None:
    candidate = Path(token.strip('"'))
    if candidate.suffix.lower() not in {".py", ".pyw"}:
        return None
    if candidate.is_absolute():
        return candidate.resolve()
    direct = (cwd / candidate).resolve()
    if direct.exists():
        return direct
    return (root / candidate).resolve()


def _file_uses_tkinter(path: Path) -> bool:
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")[:20000]
    except Exception:
        return False
    lowered = content.lower()
    return any(marker.lower() in lowered for marker in TK_MARKERS)
