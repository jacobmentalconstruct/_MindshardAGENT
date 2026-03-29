from pathlib import Path

from src.core.agent.filesystem_claim_guardrail import (
    FilesystemEvidence,
    classify_filesystem_intent,
    evaluate_filesystem_guardrail,
)
from src.core.agent.tool_agent_turn_runner import run_tool_agent_turn
from src.core.config.app_config import AppConfig
from src.core.runtime.activity_stream import ActivityStream


class _FakeToolRouter:
    def __init__(self, result_by_tool_call_text):
        self._result_by_tool_call_text = result_by_tool_call_text

    def has_tool_calls(self, text: str) -> bool:
        return "```tool_call" in text

    def execute_all(self, text: str):
        for marker, results in self._result_by_tool_call_text.items():
            if marker in text:
                return results
        return []


def test_classify_filesystem_intent_create_edit_and_verify():
    create = classify_filesystem_intent("Create src/app.py and scaffold the file.")
    assert create.create_file is True
    assert create.modify_file is False

    modify = classify_filesystem_intent("Update src/app.py and replace the placeholder section.")
    assert modify.modify_file is True

    verify = classify_filesystem_intent("Create src/app.py and read it back to verify the file.")
    assert verify.create_file is True
    assert verify.verify_content is True
    assert verify.verify_path is True


def test_classify_filesystem_intent_ignores_non_filesystem_request():
    intent = classify_filesystem_intent("Please explain why this architecture works so well.")
    assert intent.any is False


def test_evaluate_filesystem_guardrail_flags_wrong_named_path(tmp_path):
    sandbox_root = str(tmp_path)
    evidence = FilesystemEvidence()
    evidence.record_tool_result(
        {
            "tool_name": "write_file",
            "success": True,
            "result": {"path": str(tmp_path / "todo_cli" / "src" / "main.py")},
        },
        sandbox_root,
    )

    evaluation = evaluate_filesystem_guardrail(
        user_text="Create todo_cli/src/main.py",
        assistant_text="I created `todo_cli/src/app.py`.",
        evidence=evidence,
        sandbox_root=sandbox_root,
    )

    assert evaluation.triggered is True
    assert any("assistant_named_file_without_matching_tool_evidence" in item for item in evaluation.violations)


def test_evaluate_filesystem_guardrail_ignores_inserted_content_paths(tmp_path):
    sandbox_root = str(tmp_path)
    target = tmp_path / "BUILD_PLAN.md"
    target.write_text("# Build Plan\n\n## Files\n- src/app.py\n- tests/test_app.py\n", encoding="utf-8")

    evidence = FilesystemEvidence()
    evidence.record_tool_result(
        {
            "tool_name": "replace_in_file",
            "success": True,
            "result": {"path": str(target)},
        },
        sandbox_root,
    )
    evidence.record_tool_result(
        {
            "tool_name": "read_file",
            "success": True,
            "result": {"path": str(target), "content": target.read_text(encoding="utf-8")},
        },
        sandbox_root,
    )

    evaluation = evaluate_filesystem_guardrail(
        user_text="Update BUILD_PLAN.md so it lists src/app.py and tests/test_app.py, then read it back.",
        assistant_text=(
            "Updated `BUILD_PLAN.md` so the Files section now lists `src/app.py` "
            "and `tests/test_app.py`, then read it back to confirm."
        ),
        evidence=evidence,
        sandbox_root=sandbox_root,
    )

    assert evaluation.triggered is False
    assert evaluation.violations == []
    assert "BUILD_PLAN.md" in evaluation.claimed_paths


def test_run_tool_agent_turn_repairs_missing_requested_readback(monkeypatch, tmp_path):
    sandbox_root = str(tmp_path)
    target = tmp_path / "todo_cli" / "src" / "main.py"
    responses = iter(
        [
            {"content": '```tool_call\n{"tool": "write_file", "path": "todo_cli/src/main.py", "content": "print(1)"}\n```'},
            {"content": "Created `todo_cli/src/main.py`."},
            {"content": '```tool_call\n{"tool": "read_file", "path": "todo_cli/src/main.py", "start_line": 1, "end_line": 20}\n```'},
            {"content": "Created and read back `todo_cli/src/main.py`."},
        ]
    )

    def fake_chat_stream(**kwargs):
        return next(responses)

    monkeypatch.setattr("src.core.agent.tool_agent_turn_runner.chat_stream", fake_chat_stream)

    router = _FakeToolRouter(
        {
            '"tool": "write_file"': [
                {
                    "tool_name": "write_file",
                    "success": True,
                    "result": {"path": str(target)},
                }
            ],
            '"tool": "read_file"': [
                {
                    "tool_name": "read_file",
                    "success": True,
                    "result": {"path": str(target), "content": "print(1)"},
                }
            ],
        }
    )

    outcome = run_tool_agent_turn(
        config=AppConfig(selected_model="test-model", planner_model="test-model", sandbox_root=sandbox_root),
        tool_router=router,
        activity=ActivityStream(),
        user_text="Create todo_cli/src/main.py and read it back to verify the file.",
        messages=[{"role": "system", "content": "Test"}],
        should_stop=lambda: False,
    )

    assert outcome.filesystem_guardrail_triggered is True
    assert outcome.filesystem_guardrail_repaired is True
    assert outcome.filesystem_guardrail_failed is False
    assert outcome.filesystem_evidence_summary["read_count"] == 1
    assert outcome.total_content[-1] == "Created and read back `todo_cli/src/main.py`."


def test_run_tool_agent_turn_blocks_false_success_without_tool_evidence(monkeypatch, tmp_path):
    responses = iter(
        [
            {"content": "I created `todo_cli/src/app.py`."},
            {"content": "I already did it."},
        ]
    )

    def fake_chat_stream(**kwargs):
        return next(responses)

    monkeypatch.setattr("src.core.agent.tool_agent_turn_runner.chat_stream", fake_chat_stream)

    router = _FakeToolRouter({})

    outcome = run_tool_agent_turn(
        config=AppConfig(selected_model="test-model", planner_model="test-model", sandbox_root=str(tmp_path)),
        tool_router=router,
        activity=ActivityStream(),
        user_text="Create todo_cli/src/app.py.",
        messages=[{"role": "system", "content": "Test"}],
        should_stop=lambda: False,
    )

    assert outcome.filesystem_guardrail_triggered is True
    assert outcome.filesystem_guardrail_repaired is False
    assert outcome.filesystem_guardrail_failed is True
    assert "can't confirm the requested file change" in outcome.total_content[-1].lower()
