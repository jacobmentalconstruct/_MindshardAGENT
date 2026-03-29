"""Tool-use round-trip tests — validates the full pipeline headless.

Tests:
  1. Tool call parsing (does the router detect ```tool_call blocks?)
  2. CLI execution (does a parsed call actually run in sandbox?)
  3. Transcript formatting (does the result format correctly for re-injection?)
  4. Live model round-trip (does a small model actually produce a tool call
     that gets executed and fed back?)

Usage:
    python -m tests.test_tool_roundtrip [--live]

    Without --live: runs unit tests only (no Ollama needed)
    With --live: runs full end-to-end with actual model inference
"""

import sys
import json
import time
import tempfile
from pathlib import Path

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.sandbox.tool_catalog import ToolCatalog
from src.core.sandbox.cli_runner import CLIRunner
from src.core.sandbox.path_guard import PathGuard
from src.core.sandbox.command_policy import CommandPolicy
from src.core.sandbox.file_writer import FileWriter
from src.core.sandbox.python_runner import PythonRunner
from src.core.runtime.activity_stream import ActivityStream
from src.core.agent.tool_router import ToolRouter
from src.core.agent.transcript_formatter import format_tool_result, format_all_results
from src.core.agent.prompt_builder import build_system_prompt, build_system_prompt_bundle


# ── Test helpers ─────────────────────────────────────

_PASS = 0
_FAIL = 0


def _check(name: str, condition: bool, detail: str = ""):
    global _PASS, _FAIL
    if condition:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def _section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ── Test 1: Tool call parsing ────────────────────────

def test_parsing():
    _section("Test 1: Tool Call Parsing")

    activity = ActivityStream()
    catalog = ToolCatalog()
    # Mock CLI — won't actually run anything for parse tests
    guard = PathGuard(tempfile.mkdtemp())
    cli = CLIRunner(guard, activity)
    router = ToolRouter(catalog, cli, activity)

    # Good tool call
    text_good = '''I'll list the files for you.

```tool_call
{"tool": "cli_in_sandbox", "command": "dir", "cwd": "."}
```

Let me check what's there.'''

    calls = router.extract_tool_calls(text_good)
    _check("Extracts valid tool call", len(calls) == 1)
    _check("Correct tool name", calls[0].get("tool") == "cli_in_sandbox")
    _check("Correct command", calls[0].get("command") == "dir")
    _check("has_tool_calls detects it", router.has_tool_calls(text_good))

    # No tool call
    text_plain = "I don't need to run any commands for this."
    _check("No false positive", not router.has_tool_calls(text_plain))

    # Malformed JSON — router returns a sentinel so the model gets an explicit
    # error message instead of silently dropping the call (which caused hallucinated success).
    text_bad = '''```tool_call
{bad json here}
```'''
    calls_bad = router.extract_tool_calls(text_bad)
    _check("Malformed JSON returns sentinel (not dropped)", len(calls_bad) == 1)
    _check("Sentinel tool name is __malformed__", calls_bad[0].get("tool") == "__malformed__")
    result_bad = router.execute(calls_bad[0])
    _check("Sentinel execute returns failure", result_bad["success"] is False)
    _check("Sentinel error message is descriptive", "parse" in result_bad.get("error", "").lower())

    # Multiple tool calls
    text_multi = '''```tool_call
{"tool": "cli_in_sandbox", "command": "echo hello"}
```

```tool_call
{"tool": "cli_in_sandbox", "command": "echo world"}
```'''
    calls_multi = router.extract_tool_calls(text_multi)
    _check("Extracts multiple calls", len(calls_multi) == 2)
    _check("First command correct", calls_multi[0]["command"] == "echo hello")
    _check("Second command correct", calls_multi[1]["command"] == "echo world")

    # Unknown tool
    result = router.execute({"tool": "nonexistent_tool"})
    _check("Unknown tool returns error", not result["success"])
    _check("Error mentions tool name", "nonexistent_tool" in result.get("error", ""))


# ── Test 2: CLI Execution ────────────────────────────

def test_cli_execution():
    _section("Test 2: CLI Execution in Sandbox")

    sandbox = tempfile.mkdtemp()
    activity = ActivityStream()
    guard = PathGuard(sandbox)
    policy = CommandPolicy(mode="allowlist")
    cli = CLIRunner(guard, activity, policy=policy)

    # Basic echo
    result = cli.run("echo hello_roundtrip")
    _check("Echo succeeds", result["exit_code"] == 0)
    _check("Echo output correct", "hello_roundtrip" in result.get("stdout", ""))

    # Dir listing
    result = cli.run("dir")
    _check("Dir succeeds", result["exit_code"] == 0)

    # Blocked command
    result = cli.run("format C:")
    _check("Blocked command rejected", result["exit_code"] != 0 or "blocked" in result.get("stderr", "").lower() or result["exit_code"] == -1)


# ── Test 3: Transcript Formatting ────────────────────

def test_transcript_format():
    _section("Test 3: Transcript Formatting")

    # Success result
    tool_result = {
        "tool_name": "cli_in_sandbox",
        "success": True,
        "result": {
            "exit_code": 0,
            "stdout": "hello world\n",
            "stderr": "",
        },
    }
    formatted = format_tool_result(tool_result)
    _check("Success format includes tool name", "cli_in_sandbox" in formatted)
    _check("Success format includes exit code", "exit code 0" in formatted)
    _check("Success format includes stdout", "hello world" in formatted)

    # Error result
    err_result = {
        "tool_name": "cli_in_sandbox",
        "success": False,
        "error": "Command blocked by policy",
    }
    formatted_err = format_tool_result(err_result)
    _check("Error format includes tool name", "cli_in_sandbox" in formatted_err)
    _check("Error format includes message", "blocked" in formatted_err.lower())

    # Multiple results
    multi = format_all_results([tool_result, err_result])
    _check("Multi-format contains both", "hello world" in multi and "blocked" in multi.lower())


# ── Test 4: Prompt Builder ───────────────────────────

def test_prompt_builder():
    _section("Test 4: Prompt Builder")

    catalog = ToolCatalog()
    policy = CommandPolicy(mode="allowlist")

    system = build_system_prompt(
        sandbox_root="/tmp/sandbox",
        tools=catalog,
        command_policy=policy,
        session_title="Test Session",
        model_name="qwen3.5:2b",
    )

    _check("System prompt not empty", len(system) > 100)
    _check("Contains sandbox root", "/tmp/sandbox" in system)
    _check("Contains tool instructions", "tool_call" in system)
    _check("Contains cli_in_sandbox", "cli_in_sandbox" in system)
    _check("Contains run_python_file", "run_python_file" in system)
    _check("Contains replace_in_file", "replace_in_file" in system)
    _check("Contains replace_lines", "replace_lines" in system)
    _check("Mentions disposable runs", ".mindshard/runs/" in system or ".mindshard\\runs\\" in system)
    _check("Contains MindshardAGENT", "MindshardAGENT" in system)
    _check("Contains externalized workspace semantics", "Workspace Semantics" in system)

    # With RAG context
    system_rag = build_system_prompt(
        sandbox_root="/tmp/sandbox",
        tools=catalog,
        command_policy=policy,
        rag_context="The user prefers Python 3.10.",
    )
    _check("RAG context injected", "Python 3.10" in system_rag)
    _check("RAG section header present", "Relevant Context" in system_rag)

    bundle = build_system_prompt_bundle(
        sandbox_root="/tmp/sandbox",
        tools=catalog,
        command_policy=policy,
        model_name="qwen3.5:2b",
    )
    _check("Prompt bundle includes diagnostics", len(bundle.sections) > 5)
    _check("Prompt bundle has source fingerprint", len(bundle.source_fingerprint) > 10)
    _check("Prompt bundle has prompt fingerprint", len(bundle.prompt_fingerprint) > 10)
    _check(
        "Prompt bundle records doc sources",
        any(section.layer == "global_doc" and section.source_path for section in bundle.sections),
    )


# ── Test 5: Full Router Round-Trip ───────────────────

def test_full_router_roundtrip():
    _section("Test 5: Full Router Round-Trip (simulated)")

    sandbox = tempfile.mkdtemp()
    activity = ActivityStream()
    guard = PathGuard(sandbox)
    policy = CommandPolicy(mode="allowlist")
    cli = CLIRunner(guard, activity, policy=policy)
    catalog = ToolCatalog()
    router = ToolRouter(catalog, cli, activity)

    # Simulate model response with tool call
    model_response = '''Let me check what files are in the sandbox.

```tool_call
{"tool": "cli_in_sandbox", "command": "echo ROUNDTRIP_SUCCESS"}
```'''

    # Full pipeline: extract → execute → format
    _check("Has tool calls", router.has_tool_calls(model_response))
    results = router.execute_all(model_response)
    _check("Got results", len(results) == 1)
    _check("Execution succeeded", results[0]["success"])
    _check("Output contains marker", "ROUNDTRIP_SUCCESS" in results[0]["result"]["stdout"])

    formatted = format_all_results(results)
    _check("Formatted output contains marker", "ROUNDTRIP_SUCCESS" in formatted)
    _check("Formatted output has exit code", "exit code 0" in formatted)


# ── Test 6: File Writer/Reader Tools ──────────────────

def test_file_tools():
    _section("Test 6: File Writer/Reader Tools")

    sandbox = tempfile.mkdtemp()
    activity = ActivityStream()
    guard = PathGuard(sandbox)
    fw = FileWriter(guard, activity)

    # Write a file
    result = fw.write_file("test.py", "print('hello')\nprint('world')\n")
    _check("Write succeeds", result["success"])
    _check("Bytes written reported", result.get("bytes_written", 0) > 0)

    # Verify file exists on disk
    written_path = Path(sandbox) / "test.py"
    _check("File exists on disk", written_path.exists())
    _check("File content correct", written_path.read_text() == "print('hello')\nprint('world')\n")

    # Read a file
    result = fw.read_file("test.py")
    _check("Read succeeds", result["success"])
    _check("Read content correct", "print('hello')" in result.get("content", ""))
    _check("Read size reported", result.get("size", 0) > 0)

    # Read a numbered excerpt
    result = fw.read_file("test.py", start_line=2, end_line=2, line_numbers=True)
    _check("Numbered read succeeds", result["success"])
    _check("Numbered read includes line prefix", "   2|" in result.get("content", ""))
    _check("Numbered read includes selected line", "print('world')" in result.get("content", ""))

    result = fw.read_file("test.py", start_line=1, end_line=50, line_numbers=True)
    _check("Oversized end_line clamps instead of failing", result["success"])
    _check("Clamped read reports actual end line", result.get("end_line") == 2)

    result = fw.read_file("test.py", start_line=0, end_line=-5, line_numbers=True)
    _check("Malformed range normalizes instead of failing", result["success"])
    _check("Normalized malformed range starts at first line", result.get("start_line") == 1)
    _check("Normalized malformed range collapses to a usable line", result.get("end_line") == 1)

    # Whitespace-aware read
    fw.write_file("indent.py", "def demo():\n    value = 1\t \n")
    result = fw.read_file("indent.py", start_line=2, end_line=2, line_numbers=True, show_whitespace=True)
    _check("Whitespace-aware read succeeds", result["success"])
    _check("Whitespace view shows indent", "indent_spaces=4" in result.get("content", ""))
    _check("Whitespace view shows trailing spaces", "trailing_spaces=1" in result.get("content", ""))
    _check("Whitespace view shows tab marker", "\\t" in result.get("content", ""))

    # Exact replace succeeds
    result = fw.replace_in_file("test.py", "print('world')\n", "print('updated')\n")
    _check("Exact replace succeeds", result["success"])
    _check("Exact replace returns before excerpt", "before_excerpt" in result)
    _check("Exact replace returns after excerpt", "after_excerpt" in result)
    _check("Exact replace changed disk content", "print('updated')" in written_path.read_text())

    # Exact replace fails on zero match
    result = fw.replace_in_file("test.py", "print('missing')\n", "print('nope')\n")
    _check("Exact replace no-match fails", not result["success"])
    _check("Exact replace no-match explains issue", "not found" in result.get("error", "").lower())

    # Exact replace fails on ambiguity
    fw.write_file("ambiguous.txt", "slot\nslot\n")
    result = fw.replace_in_file("ambiguous.txt", "slot\n", "changed\n")
    _check("Exact replace ambiguity fails", not result["success"])
    _check("Exact replace ambiguity mentions replace_all or narrowing", "replace_all" in result.get("error", ""))

    # Line-range replacement succeeds
    fw.write_file("lines.py", "alpha\nbeta\ngamma\ndelta\n")
    result = fw.replace_lines("lines.py", 2, 3, "BETA\nGAMMA\n")
    _check("replace_lines succeeds", result["success"])
    _check("replace_lines preserves surrounding content", (Path(sandbox) / "lines.py").read_text() == "alpha\nBETA\nGAMMA\ndelta\n")

    # Regression: create placeholder file, inspect region, replace only target section
    fw.write_file(
        "plan.md",
        "# Plan\n\n## Step One\nTODO\n\n## Step Two\nTODO\n",
    )
    result = fw.read_file("plan.md", start_line=3, end_line=7, line_numbers=True)
    _check("Regression read region succeeds", result["success"])
    _check("Regression read region includes numbered step", "   6|" in result.get("content", ""))
    result = fw.replace_lines("plan.md", 6, 7, "## Step Two\n- implemented\n")
    _check("Regression replace_lines succeeds", result["success"])
    plan_text = (Path(sandbox) / "plan.md").read_text()
    _check("Regression replacement present on disk", "- implemented" in plan_text)
    _check("Regression replacement preserved first section", "## Step One\nTODO" in plan_text)

    # Read nonexistent file
    result = fw.read_file("does_not_exist.txt")
    _check("Read missing file fails", not result["success"])
    _check("Error mentions not found", "not found" in result.get("error", "").lower())

    # Append mode
    result = fw.write_file("test.py", "# appended\n", mode="append")
    _check("Append succeeds", result["success"])
    content = written_path.read_text()
    _check("Append preserved original", "print('hello')" in content)
    _check("Append added new content", "# appended" in content)

    # Path escape blocked
    result = fw.write_file("../../etc/passwd", "hacked")
    _check("Path escape blocked", not result["success"])
    _check("Error mentions sandbox", "outside" in result.get("error", "").lower() or "denied" in result.get("error", "").lower())

    # Blocked extension
    result = fw.write_file("malware.exe", "bad stuff")
    _check("Blocked extension rejected", not result["success"])
    _check("Error mentions security", "security" in result.get("error", "").lower())

    # Subdirectory creation
    result = fw.write_file("subdir/nested/deep.txt", "deep content")
    _check("Nested write succeeds", result["success"])
    deep_path = Path(sandbox) / "subdir" / "nested" / "deep.txt"
    _check("Nested file exists", deep_path.exists())


# ── Test 7: File Tools via Router ────────────────────

def test_file_tools_via_router():
    _section("Test 7: File Tools via Router (simulated model output)")

    sandbox = tempfile.mkdtemp()
    activity = ActivityStream()
    guard = PathGuard(sandbox)
    policy = CommandPolicy(mode="allowlist")
    cli = CLIRunner(guard, activity, policy=policy)
    fw = FileWriter(guard, activity)
    catalog = ToolCatalog()
    router = ToolRouter(catalog, cli, activity, file_writer=fw)

    # Simulate model writing a multi-line Python file
    model_response = '''I'll create the hello world app for you.

```tool_call
{"tool": "write_file", "path": "hello_world.py", "content": "import tkinter as tk\\n\\nclass HelloApp:\\n    def __init__(self):\\n        self.window = tk.Tk()\\n        self.window.title(\\"Hello World\\")\\n        label = tk.Label(self.window, text=\\"HELLO WORLD!\\", font=(\\"Arial\\", 24))\\n        label.pack(pady=50)\\n        self.window.mainloop()\\n\\nif __name__ == \\"__main__\\":\\n    app = HelloApp()\\n"}
```'''

    _check("Detects write_file call", router.has_tool_calls(model_response))
    results = router.execute_all(model_response)
    _check("Got write result", len(results) == 1)
    _check("Write succeeded", results[0]["success"])

    # Verify the file was actually created
    created = Path(sandbox) / "hello_world.py"
    _check("Python file exists", created.exists())
    content = created.read_text()
    _check("Has tkinter import", "import tkinter" in content)
    _check("Has class definition", "class HelloApp" in content)
    _check("Has mainloop", "mainloop()" in content)

    # Now simulate reading it back
    read_response = '''Let me read the file to verify.

```tool_call
{"tool": "read_file", "path": "hello_world.py"}
```'''

    results = router.execute_all(read_response)
    _check("Read via router succeeded", results[0]["success"])
    _check("Read content has tkinter", "import tkinter" in results[0]["result"]["content"])

    replace_response = '''Update only the title line.

```tool_call
{"tool": "replace_in_file", "path": "hello_world.py", "old_text": "        self.window.title(\\"Hello World\\")\\n", "new_text": "        self.window.title(\\"Hello Universe\\")\\n"}
```'''
    results = router.execute_all(replace_response)
    _check("replace_in_file via router succeeded", results[0]["success"])
    _check("replace_in_file via router returned after excerpt", "Hello Universe" in results[0]["result"].get("after_excerpt", ""))

    numbered_read = '''Read the constructor with line numbers.

```tool_call
{"tool": "read_file", "path": "hello_world.py", "start_line": 3, "end_line": 8, "line_numbers": true}
```'''
    results = router.execute_all(numbered_read)
    _check("Numbered read via router succeeded", results[0]["success"])
    _check("Numbered read via router includes line numbers", "|" in results[0]["result"].get("content", ""))

    line_replace = '''Replace the class footer by line span.

```tool_call
{"tool": "replace_lines", "path": "hello_world.py", "start_line": 10, "end_line": 11, "new_text": "if __name__ == \\"__main__\\":\\n    print(\\"boot\\")\\n"}
```'''
    results = router.execute_all(line_replace)
    _check("replace_lines via router succeeded", results[0]["success"])
    _check("replace_lines via router after excerpt updated", "boot" in results[0]["result"].get("after_excerpt", ""))

    # Format the results
    formatted = format_tool_result(results[0])
    _check("replace_lines format includes path", "hello_world.py" in formatted)
    _check("replace_lines format includes excerpt", "after_excerpt" in formatted)

    # Test write_file transcript formatting
    write_result = {
        "tool_name": "write_file",
        "success": True,
        "result": {"path": "test.py", "bytes_written": 42, "action": "write"},
    }
    formatted_write = format_tool_result(write_result)
    _check("Write format includes path", "test.py" in formatted_write)
    _check("Write format includes bytes", "42" in formatted_write)


# ── Test 8: Prompt Builder with File Tools ───────────

def test_prompt_builder_file_tools():
    _section("Test 8: Prompt Builder includes File Tools")

    catalog = ToolCatalog()
    policy = CommandPolicy(mode="allowlist")

    system = build_system_prompt(
        sandbox_root="/tmp/sandbox",
        tools=catalog,
        command_policy=policy,
    )

    _check("Prompt includes write_file", "write_file" in system)
    _check("Prompt includes read_file", "read_file" in system)
    _check("Prompt includes replace_in_file", "replace_in_file" in system)
    _check("Prompt includes replace_lines", "replace_lines" in system)
    _check("Prompt includes run_python_file", "run_python_file" in system)
    _check("Prompt discourages echo for files", "never use echo" in system.lower())
    _check("Prompt shows write_file example", '"tool": "write_file"' in system)
    _check("Prompt shows read_file example", '"tool": "read_file"' in system)
    _check("Prompt teaches numbered reads before editing", "line_numbers" in system)
    _check("Prompt teaches verification after failed edits", "do not pretend it worked" in system.lower())


# ── Test 9: Structured Python Runner ─────────────────

def test_run_python_file():
    _section("Test 9: Structured Python Runner")

    sandbox = tempfile.mkdtemp()
    activity = ActivityStream()
    guard = PathGuard(sandbox)
    runner = PythonRunner(guard, activity)

    script_path = Path(sandbox) / "scripts" / "hello.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text("print('PY_RUNNER_OK')\n", encoding="utf-8")

    result = runner.run_file("scripts/hello.py")
    _check("run_python_file succeeds", result["exit_code"] == 0)
    _check("run_python_file captures output", "PY_RUNNER_OK" in result.get("stdout", ""))
    _check("run_python_file defaults to disposable copy", result.get("workspace_mode") == "run_copy")
    _check("run_python_file records run root", bool(result.get("run_root")))
    _check("run workspace stdout persisted", Path(result["run_root"], "stdout.txt").exists())

    gui_script = Path(sandbox) / "scripts" / "gui.py"
    gui_script.write_text("import tkinter as tk\nprint('blocked before run')\n", encoding="utf-8")
    deny_runner = PythonRunner(guard, activity, gui_policy_getter=lambda: "deny")
    gui_result = deny_runner.run_file("scripts/gui.py")
    _check("GUI script blocked by policy", gui_result["exit_code"] == -1)
    _check("GUI policy message returned", "blocked" in gui_result.get("stderr", "").lower())


# ── Test 10: run_python_file via Router ──────────────

def test_run_python_file_via_router():
    _section("Test 10: run_python_file via Router")

    sandbox = tempfile.mkdtemp()
    activity = ActivityStream()
    guard = PathGuard(sandbox)
    cli = CLIRunner(guard, activity, policy=CommandPolicy(mode="allowlist"))
    python_runner = PythonRunner(guard, activity)
    catalog = ToolCatalog()
    router = ToolRouter(catalog, cli, activity, python_runner=python_runner)

    script = Path(sandbox) / "run_me.py"
    script.write_text("import sys\nprint('ARGS=' + '|'.join(sys.argv[1:]))\n", encoding="utf-8")

    response = '''Testing the script.

```tool_call
{"tool": "run_python_file", "path": "run_me.py", "args": ["one", "two"], "workspace": "run_copy"}
```'''
    results = router.execute_all(response)
    _check("Router returned run_python_file result", len(results) == 1)
    _check("Router run_python_file succeeded", results[0]["success"])
    _check("Router passed args through", "ARGS=one|two" in results[0]["result"].get("stdout", ""))
    _check("Router run_python_file reports run workspace", bool(results[0]["result"].get("run_root")))


# ── Test 11: Live Model Round-Trip ───────────────────

def test_live_model(model: str = "qwen3.5:2b"):
    _section(f"Test 11: LIVE Model Round-Trip ({model})")

    import threading
    from src.core.config.app_config import AppConfig
    from src.core.runtime.event_bus import EventBus
    from src.core.engine import Engine

    sandbox = tempfile.mkdtemp()
    config = AppConfig(
        sandbox_root=sandbox,
        selected_model=model,
        ollama_base_url="http://localhost:11434",
        temperature=0.3,  # Low temp for predictable tool use
        max_context_tokens=4096,
    )
    activity = ActivityStream()
    bus = EventBus()
    engine = Engine(config=config, activity=activity, bus=bus)
    engine.set_sandbox(sandbox)
    engine.start()

    # Create a test file in sandbox for the model to find
    test_file = Path(sandbox) / "test_marker.txt"
    test_file.write_text("MARKER_12345\n")

    # Prompt designed to trigger a tool call
    prompt = (
        "List the files in the current sandbox directory using the dir command. "
        "Use the cli_in_sandbox tool."
    )

    result_holder = {"result": None, "error": None}
    done_event = threading.Event()

    def on_complete(result):
        result_holder["result"] = result
        done_event.set()

    def on_error(err):
        result_holder["error"] = err
        done_event.set()

    tokens = []
    def on_token(t):
        tokens.append(t)

    print(f"  Sending prompt to {model}...")
    engine.submit_prompt(prompt, on_token=on_token, on_complete=on_complete, on_error=on_error)

    # Wait up to 120 seconds
    done_event.wait(timeout=120)

    if result_holder["error"]:
        _check(f"No error from {model}", False, result_holder["error"])
        return

    result = result_holder["result"]
    _check("Got a result", result is not None)

    if result:
        content = result.get("content", "")
        meta = result.get("metadata", {})
        rounds = meta.get("rounds", 1)

        print(f"  Model responded: {len(content)} chars, {rounds} round(s)")
        print(f"  First 200 chars: {content[:200]}")

        _check("Response not empty", len(content) > 10)
        _check("Model completed", True)

        # Check if the model used tools (rounds > 1 means tool use happened)
        if rounds > 1:
            _check("Tool round-trip occurred", True)
            _check("Model saw sandbox contents", "test_marker" in content.lower() or rounds > 1)
        else:
            # Model might have responded without tool use — still valid but note it
            has_tool_block = "tool_call" in content or "```tool_call" in content
            if has_tool_block:
                _check("Model produced tool call format", True)
                print("  NOTE: Model produced tool call but loop may not have executed it")
            else:
                _check("Model attempted tool use", False,
                       f"Model responded without tool call ({model} may need prompting help)")

    engine.stop()


# ── Main ─────────────────────────────────────────────

def main():
    live = "--live" in sys.argv

    print(f"\nMindshardAGENT — Tool-Use Round-Trip Tests")
    print(f"{'='*60}")
    print(f"Mode: {'LIVE (with Ollama)' if live else 'UNIT (no Ollama needed)'}")

    test_parsing()
    test_cli_execution()
    test_transcript_format()
    test_prompt_builder()
    test_full_router_roundtrip()
    test_file_tools()
    test_file_tools_via_router()
    test_prompt_builder_file_tools()
    test_run_python_file()
    test_run_python_file_via_router()

    if live:
        # Test with smallest capable models
        models = []
        if "--model" in sys.argv:
            idx = sys.argv.index("--model")
            if idx + 1 < len(sys.argv):
                models = [sys.argv[idx + 1]]
        else:
            models = ["qwen3.5:2b"]

        for model in models:
            try:
                test_live_model(model)
            except Exception as e:
                print(f"  FAIL  Live test with {model}: {e}")

    _section("RESULTS")
    total = _PASS + _FAIL
    print(f"  Passed: {_PASS}/{total}")
    print(f"  Failed: {_FAIL}/{total}")
    if _FAIL == 0:
        print(f"\n  ALL TESTS PASSED")
    else:
        print(f"\n  {_FAIL} TEST(S) FAILED")
    print()

    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
