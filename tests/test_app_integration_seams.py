from __future__ import annotations

from types import SimpleNamespace

import src.app_commands as app_commands
from src.core.project import project_command_handler


def test_on_cli_command_runs_via_background_thread_and_updates_cli_pane(monkeypatch) -> None:
    activity_events: list[tuple[str, str]] = []
    results: list[dict] = []
    started: list[tuple[str, bool]] = []

    class _FakeThread:
        def __init__(self, *, target, daemon: bool, name: str) -> None:
            self._target = target
            started.append((name, daemon))

        def start(self) -> None:
            self._target()

    class _FakeEngine:
        def run_cli(self, command: str) -> dict:
            return {"command": command, "exit_code": 0, "stdout": "ok", "stderr": ""}

    class _FakeActivity:
        def tool(self, source: str, message: str) -> None:
            activity_events.append((source, message))

    class _FakeCliPane:
        def show_result(self, result: dict) -> None:
            results.append(result)

    class _FakeWindow:
        cli_pane = _FakeCliPane()

    class _FakeState:
        engine = _FakeEngine()
        activity = _FakeActivity()
        window = _FakeWindow()

        @staticmethod
        def safe_ui(fn) -> None:
            fn()

    monkeypatch.setattr(app_commands.threading, "Thread", _FakeThread)

    app_commands.on_cli_command(_FakeState(), "echo seam")

    assert started == [("cli-panel", True)]
    assert activity_events == [("cli_panel", "User CLI: echo seam")]
    assert results == [{"command": "echo seam", "exit_code": 0, "stdout": "ok", "stderr": ""}]


def test_attach_sandbox_refreshes_prompt_lab_summary(monkeypatch, tmp_path) -> None:
    prompt_refreshes: list[tuple[str, bool]] = []
    prompt_inspector_refreshes: list[str] = []
    new_sessions: list[str] = []

    monkeypatch.setattr(project_command_handler, "_reinit_stores", lambda s, root: None)
    monkeypatch.setattr(
        "src.app_session.on_session_new",
        lambda s: new_sessions.append(str(s.config.sandbox_root)),
    )
    monkeypatch.setattr(
        "src.app_prompt.refresh_prompt_inspector",
        lambda s: prompt_inspector_refreshes.append(str(s.config.sandbox_root)),
    )
    monkeypatch.setattr(
        "src.app_prompt_lab.refresh_prompt_lab_summary",
        lambda s, announce=False: prompt_refreshes.append((str(s.config.sandbox_root), announce)) or "ok",
    )

    class _FakeProjectMeta:
        display_name = "Attached Project"
        source_path = ""

        @staticmethod
        def get(key: str, default=None):
            return {"profile": "standard"}.get(key, default)

        @staticmethod
        def update(data: dict) -> None:
            return None

    class _FakeEngine:
        def __init__(self) -> None:
            self.project_meta = _FakeProjectMeta()
            self.tool_catalog = SimpleNamespace(discovered_tool_names=lambda: ["a", "b"])
            self.tokenizer = SimpleNamespace(set_model=lambda model: None)

        def set_sandbox(self, root: str) -> None:
            self.project_meta = _FakeProjectMeta()

    class _FakeUIFacade:
        def set_models(self, models, selected) -> None:
            return None

        def set_tool_count(self, count: int, names: list[str]) -> None:
            return None

        def refresh_vcs(self) -> None:
            return None

    class _FakeWindow:
        def set_project_paths(self, source_path: str, new_root: str) -> None:
            return None

        def set_project_name(self, display: str) -> None:
            return None

        def set_model(self, model: str) -> None:
            return None

    class _FakeActivity:
        def info(self, source: str, message: str) -> None:
            return None

    state = SimpleNamespace(
        config=SimpleNamespace(
            sandbox_root="",
            primary_chat_model="model-a",
            selected_model="model-a",
        ),
        engine=_FakeEngine(),
        window=_FakeWindow(),
        ui_state=SimpleNamespace(sandbox_root="", selected_model="", available_models=["model-a"]),
        activity=_FakeActivity(),
        ui_facade=_FakeUIFacade(),
    )

    project_command_handler.attach_sandbox(state, str(tmp_path))

    assert new_sessions == [str(tmp_path)]
    assert prompt_inspector_refreshes == [str(tmp_path)]
    assert prompt_refreshes == [(str(tmp_path), False)]


def test_detach_success_refreshes_prompt_lab_summary(monkeypatch) -> None:
    prompt_refreshes: list[tuple[str, bool]] = []

    monkeypatch.setattr(
        "src.app_prompt_lab.refresh_prompt_lab_summary",
        lambda s, announce=False: prompt_refreshes.append((str(s.config.sandbox_root), announce)) or "ok",
    )

    class _FakeEngine:
        project_meta = SimpleNamespace(display_name="Attached Project")

        @staticmethod
        def detach_project(on_progress=None, keep_sidecar: bool = False) -> dict:
            return {
                "success": True,
                "archive_path": "C:/archive.zip",
                "sidecar_retained": keep_sidecar,
            }

    class _FakeUIFacade:
        def __init__(self) -> None:
            self.input_enabled: list[bool] = []
            self.messages: list[str] = []
            self.cleared = 0
            self.vcs_refreshes = 0

        def post_system_message(self, message: str) -> None:
            self.messages.append(message)

        def set_input_enabled(self, enabled: bool) -> None:
            self.input_enabled.append(enabled)

        def clear_prompt_inspector(self) -> None:
            self.cleared += 1

        def refresh_vcs(self) -> None:
            self.vcs_refreshes += 1

    class _FakeWindow:
        def __init__(self) -> None:
            self.statuses: list[str] = []

        def set_status(self, status: str) -> None:
            self.statuses.append(status)

        def set_project_name(self, name: str) -> None:
            return None

        def set_project_paths(self, source: str, root: str) -> None:
            return None

    ui_facade = _FakeUIFacade()
    window = _FakeWindow()
    state = SimpleNamespace(
        config=SimpleNamespace(sandbox_root=""),
        engine=_FakeEngine(),
        ui_facade=ui_facade,
        window=window,
        safe_ui=lambda fn: fn(),
    )

    class _FakeThread:
        def __init__(self, *, target, daemon: bool, name: str) -> None:
            self._target = target

        def start(self) -> None:
            self._target()

    monkeypatch.setattr(project_command_handler.threading, "Thread", _FakeThread)

    project_command_handler.detach(state, keep_sidecar=False)

    assert prompt_refreshes == [("", False)]
    assert ui_facade.input_enabled == [False, True]
    assert ui_facade.cleared == 1
    assert ui_facade.vcs_refreshes == 1
    assert "Detached" in window.statuses
