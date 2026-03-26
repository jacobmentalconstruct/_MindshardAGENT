"""Local UI control bridge for the running Tk app.

Exposes a localhost-only JSON API so external tools can drive the visible app
without screen scraping. Every mutating action is marshaled onto the Tk main
thread via ``root.after``.
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from src.core.runtime.runtime_logger import get_logger

log = get_logger("ui_bridge")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BRIDGE_INFO_PATH = PROJECT_ROOT / ".mindshard_ui_bridge.json"


class _BridgeHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class UIControlBridgeServer:
    """Small localhost-only bridge for driving the visible GUI."""

    def __init__(self, app_state, *, host: str = "127.0.0.1", port: int = 8765):
        self._s = app_state
        self._host = (host or "127.0.0.1").strip() or "127.0.0.1"
        self._requested_port = max(0, int(port or 0))
        self._port = self._requested_port
        self._server: _BridgeHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self._port}"

    def start(self) -> None:
        if self._server is not None:
            return

        bridge = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "MindshardUIBridge/1.0"

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path == "/health":
                    self._write_json(200, {"ok": True, "bridge_url": bridge.url})
                    return
                if parsed.path == "/state":
                    params = parse_qs(parsed.query)
                    limit = int(params.get("max_messages", ["20"])[0] or 20)
                    try:
                        state = bridge.snapshot_state(max_messages=limit)
                        self._write_json(200, state)
                    except Exception as exc:  # pragma: no cover - defensive path
                        self._write_json(500, {"ok": False, "error": str(exc)})
                    return
                self._write_json(404, {"ok": False, "error": "Not found"})

            def do_POST(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path != "/command":
                    self._write_json(404, {"ok": False, "error": "Not found"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0") or 0)
                    raw = self.rfile.read(length) if length > 0 else b"{}"
                    payload = json.loads(raw.decode("utf-8") or "{}")
                except Exception:
                    self._write_json(400, {"ok": False, "error": "Invalid JSON body"})
                    return

                action = str(payload.get("action", "") or "").strip()
                args = payload.get("args", {}) or {}
                if not action:
                    self._write_json(400, {"ok": False, "error": "action is required"})
                    return
                try:
                    result = bridge.handle_command(action, args)
                    self._write_json(200, {"ok": True, "action": action, "result": result})
                except Exception as exc:
                    log.exception("UI bridge command failed: %s", action)
                    self._write_json(
                        500,
                        {
                            "ok": False,
                            "action": action,
                            "error": str(exc),
                            "traceback": traceback.format_exc(),
                        },
                    )

            def log_message(self, format: str, *args) -> None:  # noqa: A003
                log.info("HTTP %s", format % args)

            def _write_json(self, status: int, payload: dict) -> None:
                body = json.dumps(payload, indent=2).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        try:
            self._server = _BridgeHTTPServer((self._host, self._requested_port), Handler)
        except OSError:
            # Fall back to an ephemeral port if the configured port is busy.
            self._server = _BridgeHTTPServer((self._host, 0), Handler)
        self._port = int(self._server.server_address[1])

        thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="ui-control-bridge",
        )
        self._thread = thread
        thread.start()
        BRIDGE_INFO_PATH.write_text(
            json.dumps({"host": self._host, "port": self._port, "url": self.url}, indent=2),
            encoding="utf-8",
        )
        log.info("UI bridge started at %s", self.url)

    def stop(self) -> None:
        if self._server is None:
            return
        try:
            self._server.shutdown()
            self._server.server_close()
        finally:
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2.0)
            self._server = None
            self._thread = None
            try:
                BRIDGE_INFO_PATH.unlink(missing_ok=True)
            except Exception:
                pass
            log.info("UI bridge stopped")

    def snapshot_state(self, *, max_messages: int = 20) -> dict:
        return self._call_on_ui(lambda: self._snapshot_state_ui(max_messages=max_messages))

    def handle_command(self, action: str, args: dict) -> dict:
        if action == "get_state":
            return self.snapshot_state(max_messages=int(args.get("max_messages", 20) or 20))

        if action == "list_actions":
            return {
                "actions": [
                    "get_state",
                    "attach_project",
                    "new_session",
                    "set_input_text",
                    "append_input_text",
                    "submit_input",
                    "set_loop_mode",
                    "click_faux_button",
                    "run_plan",
                    "reload_tools",
                    "reload_prompt_docs",
                    "request_stop",
                    "clear_chat",
                    "open_settings",
                    "wait_until_idle",
                ]
            }

        if action == "set_input_text":
            text = str(args.get("text", "") or "")
            return self._call_on_ui(lambda: self._set_input_text_ui(text))

        if action == "append_input_text":
            text = str(args.get("text", "") or "")
            return self._call_on_ui(lambda: self._append_input_text_ui(text))

        if action == "submit_input":
            text = args.get("text")
            loop_mode = args.get("loop_mode")
            return self._call_on_ui(lambda: self._submit_input_ui(text=text, loop_mode=loop_mode))

        if action == "set_loop_mode":
            mode = args.get("mode")
            return self._call_on_ui(lambda: self._set_loop_mode_ui(mode))

        if action == "click_faux_button":
            label = str(args.get("label", "") or "").strip()
            if not label:
                raise ValueError("label is required")
            return self._call_on_ui(lambda: self._click_faux_button_ui(label))

        if action == "attach_project":
            path = str(args.get("path", "") or "").strip()
            if not path:
                raise ValueError("path is required")
            return self._call_on_ui(lambda: self._attach_project_ui(path, args))

        if action == "new_session":
            return self._call_on_ui(self._new_session_ui)

        if action == "run_plan":
            goal = str(args.get("goal", "") or "").strip()
            if not goal:
                raise ValueError("goal is required")
            depth = max(2, int(args.get("depth", 3) or 3))
            return self._call_on_ui(lambda: self._run_plan_ui(goal, depth))

        if action == "reload_tools":
            return self._call_on_ui(self._reload_tools_ui)

        if action == "reload_prompt_docs":
            return self._call_on_ui(self._reload_prompt_docs_ui)

        if action == "request_stop":
            return self._call_on_ui(self._request_stop_ui)

        if action == "clear_chat":
            return self._call_on_ui(self._clear_chat_ui)

        if action == "open_settings":
            return self._call_on_ui(self._open_settings_ui)

        if action == "wait_until_idle":
            timeout_ms = int(args.get("timeout_ms", 30000) or 30000)
            poll_ms = int(args.get("poll_ms", 150) or 150)
            return self.wait_until_idle(timeout_ms=timeout_ms, poll_ms=poll_ms)

        raise ValueError(f"Unknown action: {action}")

    def wait_until_idle(self, *, timeout_ms: int = 30000, poll_ms: int = 150) -> dict:
        deadline = time.monotonic() + max(timeout_ms, 1) / 1000.0
        while time.monotonic() < deadline:
            state = self.snapshot_state(max_messages=20)
            if not state.get("is_busy", False):
                return {"idle": True, "state": state}
            time.sleep(max(poll_ms, 25) / 1000.0)
        return {"idle": False, "state": self.snapshot_state(max_messages=20)}

    def _call_on_ui(self, fn, timeout: float = 30.0):
        if self._s.is_closing:
            raise RuntimeError("App is closing")

        done = threading.Event()
        box: dict[str, object] = {}

        def _invoke() -> None:
            try:
                box["result"] = fn()
            except Exception as exc:  # pragma: no cover - defensive path
                box["error"] = exc
                box["traceback"] = traceback.format_exc()
            finally:
                done.set()

        self._s.root.after(0, _invoke)
        if not done.wait(timeout):
            raise TimeoutError(f"UI bridge action timed out after {timeout:.1f}s")
        if "error" in box:
            raise RuntimeError(str(box["error"]))
        return box.get("result")

    def _snapshot_state_ui(self, *, max_messages: int = 20) -> dict:
        ui = self._s.ui_facade.snapshot_state(max_messages=max_messages)
        ui.update(
            {
                "bridge_url": self.url,
                "is_streaming": bool(self._s.ui_state.is_streaming),
                "is_busy": bool(self._s.ui_state.is_busy),
                "busy_kind": str(self._s.ui_state.busy_kind or ""),
                "stop_requested": bool(self._s.ui_state.stop_requested),
                "sandbox_root": str(self._s.config.sandbox_root or ""),
                "toolbox_root": str(self._s.config.toolbox_root or ""),
                "active_session_id": self._s.active_session_id,
                "engine_running": bool(self._s.engine.is_running),
                "tool_names": self._s.engine.tool_catalog.discovered_tool_names(),
                "tool_count": len(self._s.engine.tool_catalog.discovered_tool_names()),
            }
        )
        return ui

    def _set_input_text_ui(self, text: str) -> dict:
        self._s.ui_facade.set_input_text(text)
        self._s.ui_facade.focus_input()
        return {"input_text": self._s.ui_facade.get_input_text()}

    def _append_input_text_ui(self, text: str) -> dict:
        existing = self._s.ui_facade.get_input_text()
        combined = f"{existing}\n{text}".strip() if existing else text
        self._s.ui_facade.set_input_text(combined)
        self._s.ui_facade.focus_input()
        return {"input_text": self._s.ui_facade.get_input_text()}

    def _submit_input_ui(self, *, text=None, loop_mode=None) -> dict:
        if loop_mode is not None:
            self._s.ui_facade.set_loop_mode(str(loop_mode))
        if text is not None:
            self._s.ui_facade.set_input_text(str(text))
        submitted = self._s.ui_facade.submit_input()
        return {
            "submitted": submitted,
            "loop_mode": self._s.ui_facade.snapshot_state(max_messages=0)["loop_mode"],
            "is_streaming": bool(self._s.ui_state.is_streaming),
            "is_busy": bool(self._s.ui_state.is_busy),
            "busy_kind": str(self._s.ui_state.busy_kind or ""),
        }

    def _set_loop_mode_ui(self, mode) -> dict:
        applied = self._s.ui_facade.set_loop_mode(None if mode is None else str(mode))
        return {"loop_mode": applied}

    def _click_faux_button_ui(self, label: str) -> dict:
        from src.app_commands import handle_faux_click

        handle_faux_click(self._s, label)
        return {"clicked": label}

    def _attach_project_ui(self, path: str, args: dict) -> dict:
        from pathlib import Path

        from src.core.project.project_command_handler import attach_sandbox
        from src.core.project.project_meta import PROFILE_STANDARD
        from src.core.utils.clock import utc_iso

        root = Path(path).resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError(f"Project path does not exist: {root}")

        brief_data = {
            "display_name": str(args.get("display_name", "") or "").strip() or root.name,
            "project_purpose": str(args.get("project_purpose", "") or "").strip() or "Visible UI bridge testing workspace",
            "current_goal": str(args.get("current_goal", "") or "").strip() or "Exercise and stabilize the MindshardAGENT UI",
            "project_type": str(args.get("project_type", "") or "").strip() or "Python app",
            "constraints": str(args.get("constraints", "") or "").strip(),
            "profile": str(args.get("profile", "") or "").strip() or PROFILE_STANDARD,
            "source_path": str(args.get("source_path", "") or "").strip(),
            "attached_at": str(args.get("attached_at", "") or "").strip() or utc_iso(),
        }
        attach_sandbox(self._s, str(root), brief_data=brief_data)
        return {
            "attached": str(root),
            "project_name": brief_data["display_name"],
            "state": self._snapshot_state_ui(max_messages=10),
        }

    def _new_session_ui(self) -> dict:
        from src.app_session import on_session_new

        on_session_new(self._s)
        return {
            "session_started": True,
            "state": self._snapshot_state_ui(max_messages=10),
        }

    def _run_plan_ui(self, goal: str, depth: int) -> dict:
        from src.core.agent.thought_chain_command_handler import run_thought_chain

        run_thought_chain(self._s, goal, depth=depth)
        return {"started": True, "goal": goal, "depth": depth}

    def _reload_tools_ui(self) -> dict:
        from src.app_commands import on_reload_tools

        on_reload_tools(self._s)
        names = self._s.engine.tool_catalog.discovered_tool_names()
        return {"tool_count": len(names), "tool_names": names}

    def _reload_prompt_docs_ui(self) -> dict:
        from src.app_commands import on_reload_prompt_docs

        on_reload_prompt_docs(self._s)
        return {"reloaded": True}

    def _request_stop_ui(self) -> dict:
        self._s.engine.request_stop()
        self._s.mark_stop_requested(status_text="Stop requested")
        return {"stop_requested": True}

    def _clear_chat_ui(self) -> dict:
        self._s.ui_facade.clear_chat()
        self._s.engine.clear_history()
        self._s.activity.info("ui_bridge", "Chat cleared via UI bridge")
        return {"cleared": True}

    def _open_settings_ui(self) -> dict:
        from src.app_commands import on_open_settings

        on_open_settings(self._s)
        return {"opened": True}
