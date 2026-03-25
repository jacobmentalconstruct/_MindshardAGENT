import json
import threading
from pathlib import Path
from types import SimpleNamespace

from src.app_ui_bridge import UIControlBridgeServer
from src.core.agent.execution_planner import PlannerStageResult, run_execution_planner
from src.core.agent.loop_types import LoopRequest
from src.core.agent.planner_only_loop import PlannerOnlyLoop
from src.core.agent.thought_chain import ThoughtChain
from src.core.agent.thought_chain_command_handler import run_thought_chain
from src.core.config.app_config import AppConfig
from src.core.engine import Engine
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.event_bus import EventBus
from src.core.sandbox.tool_catalog import ToolCatalog
from src.core.sandbox.tool_discovery import discover_tools


def _write_tool(root: Path, filename: str, tool_name: str) -> Path:
    tool_dir = root / ".mindshard" / "tools"
    tool_dir.mkdir(parents=True, exist_ok=True)
    tool_file = tool_dir / filename
    tool_file.write_text(
        f'''"""
Tool: {tool_name}
Description: Echo tool for tests
Parameters: message:string:required
"""
import json
import sys

params = {{}}
if "--json" in sys.argv:
    params = json.loads(sys.argv[sys.argv.index("--json") + 1])
print(json.dumps({{"message": params.get("message", "")}}))
''',
        encoding="utf-8",
    )
    return tool_file


def test_discover_tools_preserves_source_and_script_path(tmp_path):
    tool_file = _write_tool(tmp_path, "toolbox_echo.py", "toolbox_echo")

    found = discover_tools(tmp_path, source="toolbox")

    assert len(found) == 1
    assert found[0].name == "toolbox_echo"
    assert found[0].source == "toolbox"
    assert Path(found[0].script_path) == tool_file


def test_engine_reload_discovers_and_executes_toolbox_tools(tmp_path):
    sandbox_root = tmp_path / "sandbox"
    toolbox_root = tmp_path / "toolbox"
    sandbox_root.mkdir()
    toolbox_root.mkdir()

    _write_tool(sandbox_root, "sandbox_echo.py", "sandbox_echo")
    _write_tool(toolbox_root, "toolbox_echo.py", "toolbox_echo")

    config = AppConfig(
        sandbox_root=str(sandbox_root),
        toolbox_root=str(toolbox_root),
        selected_model="test-model",
        planner_model="test-model",
    )
    engine = Engine(config=config, activity=ActivityStream(), bus=EventBus())
    try:
        engine.set_sandbox(str(sandbox_root))

        names = set(engine.tool_catalog.discovered_tool_names())
        assert {"sandbox_echo", "toolbox_echo"} <= names
        assert engine.tool_catalog.get("toolbox_echo").source == "toolbox"

        result = engine.tool_router.execute(
            {"tool": "toolbox_echo", "message": "hello from toolbox"}
        )
        assert result["success"] is True
        payload = json.loads(result["result"]["stdout"].strip())
        assert payload["message"] == "hello from toolbox"
    finally:
        engine.vault.close()


def test_run_execution_planner_reports_stopped(monkeypatch):
    def fake_chat_stream(**kwargs):
        assert kwargs["should_stop"]() is True
        return {
            "content": "GOAL:\n- Partial plan",
            "wall_ms": 12.0,
            "prompt_eval_count": 4,
            "eval_count": 5,
            "stopped": True,
        }

    monkeypatch.setattr("src.core.agent.execution_planner.chat_stream", fake_chat_stream)

    config = AppConfig(
        selected_model="test-model",
        planner_model="test-model",
        planning_enabled=True,
    )
    result = run_execution_planner(
        config=config,
        activity=ActivityStream(),
        tool_catalog=ToolCatalog(),
        user_text="Please plan this backend change",
        sandbox_root="C:/tmp/sandbox",
        should_stop=lambda: True,
    )

    assert result is not None
    assert result.stopped is True
    assert "GOAL:" in result.plan_text


def test_planner_only_loop_request_stop_marks_completion_stopped(monkeypatch):
    done = threading.Event()
    holder: dict[str, object] = {}

    def fake_run_execution_planner(**kwargs):
        should_stop = kwargs["should_stop"]
        while not should_stop():
            threading.Event().wait(0.01)
        return PlannerStageResult(
            model_name="planner-test",
            plan_text="GOAL:\n- Partial plan",
            wall_ms=10.0,
            tokens_in=1,
            tokens_out=2,
            stopped=True,
        )

    monkeypatch.setattr("src.core.agent.planner_only_loop.run_execution_planner", fake_run_execution_planner)

    loop = PlannerOnlyLoop(
        config=AppConfig(selected_model="test-model", planner_model="test-model", planning_enabled=True),
        activity=ActivityStream(),
        tool_catalog=ToolCatalog(),
        sandbox_root_getter=lambda: "C:/tmp/sandbox",
        active_project_getter=lambda: "",
    )

    loop.run(
        LoopRequest(
            user_text="Plan this feature",
            chat_history=[],
            on_complete=lambda result: (holder.setdefault("result", result), done.set()),
            on_error=lambda err: (holder.setdefault("error", err), done.set()),
        )
    )
    loop.request_stop()

    assert done.wait(timeout=2.0), "planner-only loop did not finish"
    assert "error" not in holder
    result = holder["result"]
    assert result["metadata"]["stopped"] is True
    assert "[Stopped by user request.]" in result["content"]


def test_thought_chain_stop_halts_after_current_round(monkeypatch):
    done = threading.Event()
    holder: dict[str, object] = {}

    def fake_chat_stream(**kwargs):
        assert callable(kwargs["should_stop"])
        return {
            "content": "Brainstormed first round",
            "wall_ms": 10.0,
            "prompt_eval_count": 1,
            "eval_count": 1,
            "stopped": False,
        }

    monkeypatch.setattr("src.core.agent.thought_chain.chat_stream", fake_chat_stream)

    chain = ThoughtChain(
        AppConfig(selected_model="test-model", planner_model="test-model"),
        ActivityStream(),
    )

    def on_round(round_num: int, text: str) -> None:
        assert round_num == 1
        assert text == "Brainstormed first round"
        chain.request_stop()

    chain.run(
        "Decompose this goal",
        depth=3,
        on_round=on_round,
        on_complete=lambda result: (holder.setdefault("result", result), done.set()),
        on_error=lambda err: (holder.setdefault("error", err), done.set()),
    )

    assert done.wait(timeout=2.0), "thought chain did not finish"
    assert "error" not in holder
    result = holder["result"]
    assert result["stopped"] is True
    assert result["completed_rounds"] == 1
    assert result["final_text"] == "Brainstormed first round"


def test_ui_bridge_wait_until_idle_uses_busy_state():
    server = object.__new__(UIControlBridgeServer)
    states = iter(
        [
            {"is_busy": True, "busy_kind": "thought_chain"},
            {"is_busy": True, "busy_kind": "thought_chain"},
            {"is_busy": False, "busy_kind": ""},
        ]
    )
    server.snapshot_state = lambda max_messages=20: next(states)

    result = UIControlBridgeServer.wait_until_idle(server, timeout_ms=500, poll_ms=1)

    assert result["idle"] is True
    assert result["state"]["is_busy"] is False


def test_run_thought_chain_tracks_busy_state_until_completion():
    messages: list[str] = []
    input_enabled_calls: list[bool] = []
    status_updates: list[str] = []
    journal_rows: list[tuple] = []

    class DummyState:
        def __init__(self):
            self.ui_state = SimpleNamespace(is_busy=False, busy_kind="", stop_requested=False)
            self.ui_facade = SimpleNamespace(
                post_system_message=lambda text: messages.append(text),
                set_input_enabled=lambda enabled: input_enabled_calls.append(enabled),
            )
            self.window = SimpleNamespace(
                set_status=lambda text: status_updates.append(text),
            )
            self.engine = SimpleNamespace(
                journal=SimpleNamespace(record=lambda *args: journal_rows.append(args)),
            )
            self._busy_token = 0

        def begin_busy(self, kind: str, *, status_text: str | None = None, disable_input: bool = True) -> int:
            self._busy_token += 1
            self.ui_state.is_busy = True
            self.ui_state.busy_kind = kind
            self.ui_state.stop_requested = False
            if status_text:
                self.window.set_status(status_text)
            if disable_input:
                self.ui_facade.set_input_enabled(False)
            return self._busy_token

        def end_busy(self, token: int | None = None, *, status_text: str | None = "Ready", enable_input: bool = True) -> bool:
            self.ui_state.is_busy = False
            self.ui_state.busy_kind = ""
            self.ui_state.stop_requested = False
            if status_text:
                self.window.set_status(status_text)
            if enable_input:
                self.ui_facade.set_input_enabled(True)
            return True

        def safe_ui(self, callback):
            callback()

    state = DummyState()

    def fake_run_thought_chain(**kwargs):
        assert state.ui_state.is_busy is True
        assert state.ui_state.busy_kind == "thought_chain"
        kwargs["on_round"](1, "First pass")
        kwargs["on_complete"](
            {
                "tasks": [
                    {"number": "1", "text": "Create tests", "complexity": "small"},
                    {"number": "2", "text": "Wire handlers", "complexity": "medium"},
                ],
                "final_text": "1. [small] Create tests\n2. [medium] Wire handlers",
                "completed_rounds": 3,
                "stopped": False,
            }
        )

    state.engine.run_thought_chain = fake_run_thought_chain

    run_thought_chain(state, "Ship the UI bridge", depth=3)

    assert state.ui_state.is_busy is False
    assert state.ui_state.busy_kind == ""
    assert input_enabled_calls == [False, True]
    assert status_updates == ["Planning...", "Ready"]
    assert messages[0] == "Starting thought chain for: Ship the UI bridge"
    assert "[Plan round 1]\nFirst pass" in messages[1]
    assert "Task list (2 tasks):" in messages[2]
    assert journal_rows, "expected thought-chain completion to be journaled"
