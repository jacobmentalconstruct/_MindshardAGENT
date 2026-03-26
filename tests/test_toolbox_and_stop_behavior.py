import json
import socket
import threading
from pathlib import Path
from types import SimpleNamespace

from src.app_ui_bridge import UIControlBridgeServer
from src.core.agent.execution_planner import PlannerStageResult, run_execution_planner
from src.core.agent.loop_types import LoopRequest, REVIEW_JUDGE_LOOP, RECOVERY_AGENT_LOOP
from src.core.agent.planner_only_loop import PlannerOnlyLoop
from src.core.agent.recovery_agent_loop import RecoveryAgentLoop
from src.core.agent.review_judge_loop import ReviewJudgeLoop
from src.core.agent.thought_chain import ThoughtChain
from src.core.agent.thought_chain_command_handler import run_thought_chain
from src.core.agent.transcript_formatter import strip_tool_call_markup
from src.core.config.app_config import AppConfig
from src.core.engine import Engine
from src.core.ollama.ollama_client import chat_stream
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.event_bus import EventBus
from src.core.sandbox.tool_catalog import ToolCatalog
from src.core.sandbox.tool_discovery import discover_tools
from src.app_streaming import on_submit


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


def test_recovery_agent_loop_wraps_loop_mode_and_forwards_join():
    joined: list[float] = []
    holder: dict[str, object] = {}

    class DummyToolLoop:
        loop_id = "tool_agent"

        def run(self, request: LoopRequest) -> None:
            request.on_complete(
                {
                    "content": "Recovered answer",
                    "metadata": {"loop_mode": "tool_agent", "stopped": False, "rounds": 1},
                    "history_addition": [
                        {"role": "user", "content": request.user_text},
                        {"role": "assistant", "content": "Recovered answer"},
                    ],
                }
            )

        def request_stop(self) -> None:
            return None

        def join(self, timeout: float = 3.0) -> None:
            joined.append(timeout)

    loop = RecoveryAgentLoop(ActivityStream(), DummyToolLoop())
    loop.run(
        LoopRequest(
            user_text="Please try again differently",
            chat_history=[],
            on_complete=lambda result: holder.setdefault("result", result),
        )
    )
    loop.join(timeout=1.25)

    result = holder["result"]
    assert result["metadata"]["loop_mode"] == RECOVERY_AGENT_LOOP
    assert result["history_addition"][0]["content"] == "Please try again differently"
    assert joined == [1.25]


def test_review_judge_loop_stop_path_keeps_wrapper_metadata():
    holder: dict[str, object] = {}
    loop_ref: dict[str, object] = {}

    class DummyToolLoop:
        loop_id = "tool_agent"

        def run(self, request: LoopRequest) -> None:
            loop_ref["loop"].request_stop()
            request.on_complete(
                {
                    "content": "Base answer",
                    "metadata": {"loop_mode": "tool_agent", "stopped": False, "rounds": 1},
                    "history_addition": [
                        {"role": "user", "content": request.user_text},
                        {"role": "assistant", "content": "Base answer"},
                    ],
                }
            )

        def request_stop(self) -> None:
            return None

        def join(self, timeout: float = 3.0) -> None:
            return None

    loop = ReviewJudgeLoop(
        config=AppConfig(selected_model="test-model", planner_model="test-model"),
        activity=ActivityStream(),
        tool_agent_loop=DummyToolLoop(),
    )
    loop_ref["loop"] = loop
    loop.run(
        LoopRequest(
            user_text="Review this",
            chat_history=[],
            on_complete=lambda result: holder.setdefault("result", result),
        )
    )

    result = holder["result"]
    assert result["metadata"]["loop_mode"] == REVIEW_JUDGE_LOOP
    assert result["metadata"]["review_generated"] is False
    assert result["metadata"]["stopped"] is True


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
    persisted_messages: list[tuple[str, str, str, int]] = []
    autosave_calls: list[str] = []

    monkeypatch = __import__("pytest").MonkeyPatch()
    monkeypatch.setattr("src.app_session.schedule_autosave", lambda s: autosave_calls.append("autosave"))

    class DummyState:
        def __init__(self):
            self.ui_state = SimpleNamespace(is_busy=False, busy_kind="", stop_requested=False, last_user_input="")
            self.ui_facade = SimpleNamespace(
                post_user_message=lambda text: messages.append(f"USER::{text}"),
                post_system_message=lambda text: messages.append(text),
                set_input_enabled=lambda enabled: input_enabled_calls.append(enabled),
                set_last_prompt=lambda text: messages.append(f"LAST_PROMPT::{text}"),
                set_last_response=lambda text: messages.append(f"LAST_RESPONSE::{text}"),
            )
            self.window = SimpleNamespace(
                set_status=lambda text: status_updates.append(text),
            )
            self.engine = SimpleNamespace(
                journal=SimpleNamespace(record=lambda *args: journal_rows.append(args)),
                project_meta=None,
            )
            self.config = SimpleNamespace(sandbox_root="")
            self.session_store = SimpleNamespace(
                add_message=lambda sid, role, content, model_name="", token_out=0, **kwargs: persisted_messages.append(
                    (sid, role, content, token_out)
                )
            )
            self.active_session = {"sid": "sess-test", "node_id": None}
            self.registry = SimpleNamespace()
            self._busy_token = 0

        @property
        def active_session_id(self):
            return self.active_session["sid"]

        @property
        def active_session_node_id(self):
            return self.active_session["node_id"]

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
                "model": "planner-test",
                "tokens_out_total": 42,
                "stopped": False,
            }
        )

    state.engine.run_thought_chain = fake_run_thought_chain

    run_thought_chain(state, "Ship the UI bridge", depth=3)

    assert state.ui_state.is_busy is False
    assert state.ui_state.busy_kind == ""
    assert input_enabled_calls == [False, True]
    assert status_updates == ["Planning...", "Ready"]
    assert messages[0] == "USER::Ship the UI bridge"
    assert messages[1] == "LAST_PROMPT::Ship the UI bridge"
    assert messages[2] == "Starting thought chain for: Ship the UI bridge"
    assert "[Plan round 1]\nFirst pass" in messages[3]
    assert "Task list (2 tasks):" in messages[4]
    assert messages[5].startswith("LAST_RESPONSE::Task list (2 tasks):")
    assert journal_rows, "expected thought-chain completion to be journaled"
    assert persisted_messages[0] == ("sess-test", "user", "Ship the UI bridge", 0)
    assert persisted_messages[1][0:2] == ("sess-test", "assistant")
    assert "Task list (2 tasks):" in persisted_messages[1][2]
    assert autosave_calls == ["autosave"]
    monkeypatch.undo()


def test_chat_stream_can_stop_while_waiting_for_next_chunk(monkeypatch):
    checks = {"count": 0}

    class FakeSock:
        def __init__(self):
            self.timeout = None

        def settimeout(self, value):
            self.timeout = value

    class FakeResponse:
        def __init__(self):
            self.fp = SimpleNamespace(raw=SimpleNamespace(_sock=FakeSock()))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def readline(self):
            raise socket.timeout()

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=0: FakeResponse())

    def should_stop():
        checks["count"] += 1
        return checks["count"] >= 2

    result = chat_stream(
        base_url="http://example.invalid",
        model="test-model",
        messages=[{"role": "user", "content": "Hello"}],
        should_stop=should_stop,
        timeout=30,
        read_idle_timeout=0.01,
        heartbeat_sec=0.01,
    )

    assert result["stopped"] is True
    assert result["done_reason"] == "stopped"


def test_on_submit_discards_stream_placeholder_on_immediate_error():
    events: list[str] = []
    persisted_messages: list[tuple[str, str, str]] = []

    class DummyFacade:
        def post_user_message(self, text: str) -> None:
            events.append(f"user::{text}")

        def set_last_prompt(self, text: str) -> None:
            events.append(f"last_prompt::{text}")

        def begin_chat_stream(self) -> None:
            events.append("begin_stream")

        def cancel_chat_stream(self) -> None:
            events.append("cancel_stream")

        def post_system_message(self, text: str) -> None:
            events.append(f"system::{text}")

        def get_loop_mode(self):
            return "direct_chat"

    class DummyState:
        def __init__(self):
            self.activity = SimpleNamespace(info=lambda *args, **kwargs: None)
            self.ui_state = SimpleNamespace(
                last_user_input="",
                is_streaming=False,
                is_busy=False,
                busy_kind="",
                stop_requested=False,
            )
            self.ui_facade = DummyFacade()
            self.window = SimpleNamespace(
                set_save_dirty=lambda val: events.append(f"save_dirty::{val}"),
                set_status=lambda text: events.append(f"status::{text}"),
            )
            self.registry = SimpleNamespace()
            self.root = SimpleNamespace(
                after=lambda delay, fn: "after-id",
                after_cancel=lambda after_id: events.append(f"after_cancel::{after_id}"),
            )
            self.active_session = {"sid": "sess-1", "node_id": None}
            self.session_store = SimpleNamespace(
                add_message=lambda sid, role, content, **kwargs: persisted_messages.append((sid, role, content))
            )
            self.config = SimpleNamespace(selected_model="test-model")
            self.engine = SimpleNamespace(
                submit_prompt=lambda **kwargs: kwargs["on_error"]("No model selected")
            )
            self.streaming_content = []
            self.stream_dirty = {"val": False}
            self.stream_flush_id = {"id": None}
            self._busy_token = 0

        @property
        def active_session_id(self):
            return self.active_session["sid"]

        @property
        def active_session_node_id(self):
            return self.active_session["node_id"]

        def reset_stream_buffer(self):
            self.streaming_content.clear()
            self.stream_dirty["val"] = False

        def append_stream_token(self, token: str):
            self.streaming_content.append(token)
            self.stream_dirty["val"] = True

        def current_stream_text(self):
            return "".join(self.streaming_content)

        def consume_stream_dirty(self):
            dirty = bool(self.stream_dirty["val"])
            self.stream_dirty["val"] = False
            return dirty

        @property
        def stream_flush_after_id(self):
            return self.stream_flush_id["id"]

        def set_stream_flush_after_id(self, after_id):
            self.stream_flush_id["id"] = after_id

        def clear_stream_flush_after_id(self):
            self.stream_flush_id["id"] = None

        def begin_busy(self, kind: str, *, status_text: str | None = None, disable_input: bool = True) -> int:
            self._busy_token += 1
            self.ui_state.is_busy = True
            self.ui_state.busy_kind = kind
            if status_text:
                self.window.set_status(status_text)
            return self._busy_token

        def end_busy(self, token: int | None = None, *, status_text: str | None = "Ready", enable_input: bool = True) -> bool:
            self.ui_state.is_busy = False
            self.ui_state.busy_kind = ""
            self.ui_state.stop_requested = False
            if status_text:
                self.window.set_status(status_text)
            return True

        def safe_ui(self, callback):
            callback()

    import src.app_prompt as app_prompt

    monkeypatch = __import__("pytest").MonkeyPatch()
    monkeypatch.setattr(app_prompt, "refresh_prompt_inspector", lambda s, text: events.append(f"refresh::{text}"))
    monkeypatch.setattr(app_prompt, "set_prompt_inspector", lambda s, prompt_build: events.append("set_prompt"))

    state = DummyState()
    on_submit(state, "Hello")

    assert state.ui_state.is_busy is False
    assert state.ui_state.is_streaming is False
    assert "begin_stream" in events
    assert "cancel_stream" in events
    assert "system::Error: No model selected" in events
    assert ("sess-1", "user", "Hello") in persisted_messages
    monkeypatch.undo()


def test_strip_tool_call_markup_removes_executable_syntax_but_keeps_prose():
    raw = (
        "I will inspect the project structure first.\n\n"
        "```tool_call\n"
        '{"tool": "list_files", "path": "", "depth": 2}\n'
        "```\n\n"
        "Then I will draft the blueprint."
    )

    cleaned = strip_tool_call_markup(raw)

    assert "tool_call" not in cleaned
    assert "list_files" not in cleaned
    assert "I will inspect the project structure first." in cleaned
    assert "Then I will draft the blueprint." in cleaned


def test_strip_tool_call_markup_removes_tool_calls_summary_lines():
    raw = "Done.\n\nTOOL_CALLS: list_files(path:\"\", depth:2)\n\nNext step."

    cleaned = strip_tool_call_markup(raw)

    assert "TOOL_CALLS:" not in cleaned
    assert cleaned == "Done.\n\nNext step."
