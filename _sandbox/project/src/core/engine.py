"""Main runtime coordinator.

Owns the active session context. Receives UI actions, routes them to
model/tool/session subsystems, and pushes structured activity events
back to the UI via the activity stream and event bus.
"""

import threading
from typing import Any, Callable

from src.core.config.app_config import AppConfig
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.event_bus import EventBus
from src.core.runtime.runtime_logger import get_logger
from src.core.ollama.ollama_client import chat_stream
from src.core.ollama.tokenizer_adapter import TokenizerAdapter
from src.core.sandbox.sandbox_manager import SandboxManager
from src.core.sandbox.tool_catalog import ToolCatalog
from src.core.agent.tool_router import ToolRouter
from src.core.agent.response_loop import ResponseLoop
from src.core.sandbox.command_policy import CommandPolicy

log = get_logger("engine")


class Engine:
    """Central runtime coordinator for the application."""

    def __init__(self, config: AppConfig, activity: ActivityStream, bus: EventBus,
                 on_confirm_destructive=None):
        self.config = config
        self.activity = activity
        self.bus = bus
        self.tokenizer = TokenizerAdapter()
        self._running = False
        self._chat_history: list[dict[str, str]] = []
        self._on_confirm_destructive = on_confirm_destructive

        # Sandbox + tools (initialized when sandbox is set)
        self.sandbox: SandboxManager | None = None
        self.tool_catalog = ToolCatalog()
        self.tool_router: ToolRouter | None = None
        self.response_loop: ResponseLoop | None = None

        log.info("Engine created")

    def start(self) -> None:
        self._running = True
        self.activity.info("engine", "Engine started")
        self.bus.emit("engine.started")
        log.info("Engine started")

    def stop(self) -> None:
        self._running = False
        self.activity.info("engine", "Engine stopping")
        self.bus.emit("engine.stopped")
        log.info("Engine stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    def set_sandbox(self, sandbox_root: str) -> None:
        """Initialize or change the sandbox root."""
        self.command_policy = CommandPolicy(mode="allowlist")
        self.sandbox = SandboxManager(sandbox_root, self.activity,
                                       on_confirm_destructive=self._on_confirm_destructive)
        self.tool_router = ToolRouter(self.tool_catalog, self.sandbox.cli, self.activity)
        self.response_loop = ResponseLoop(
            self.config, self.tool_catalog, self.tool_router, self.activity,
            command_policy=self.command_policy)
        self.config.sandbox_root = sandbox_root
        self.activity.info("engine", f"Sandbox set: {sandbox_root}")
        self.activity.info("engine",
            f"Command policy: allowlist mode, {len(self.command_policy._allowed)} commands permitted")
        log.info("Sandbox initialized: %s", sandbox_root)

    def run_cli(self, command: str, cwd: str | None = None) -> dict[str, Any]:
        """Execute a CLI command directly in the sandbox (for the CLI panel)."""
        if not self.sandbox:
            return {"stdout": "", "stderr": "No sandbox configured", "exit_code": -1,
                    "command": command, "cwd": "", "started_at": "", "finished_at": ""}
        return self.sandbox.cli.run(command, cwd=cwd)

    def submit_prompt(
        self,
        user_text: str,
        on_token: Callable[[str], None] | None = None,
        on_complete: Callable[[dict[str, Any]], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        """Submit a user prompt. Uses the full response loop with tool support
        when sandbox is configured, falls back to simple streaming otherwise."""

        if not self.config.selected_model:
            if on_error:
                on_error("No model selected")
            return

        token_est = self.tokenizer.count(user_text)
        self.activity.model("engine", f"Sending prompt to {self.config.selected_model} (~{token_est} tokens)")

        if self.response_loop and self.sandbox:
            self.response_loop.run_turn(
                user_text=user_text,
                chat_history=list(self._chat_history),
                on_token=on_token,
                on_complete=lambda result: self._handle_loop_complete(result, on_complete),
                on_error=on_error,
            )
        else:
            self._simple_chat(user_text, on_token, on_complete, on_error)

    def _handle_loop_complete(self, result: dict, on_complete) -> None:
        additions = result.get("history_addition", [])
        self._chat_history.extend(additions)
        meta = result.get("metadata", {})
        self.activity.model("engine",
                            f"Response complete: {meta.get('tokens_out', '?')} tokens, "
                            f"{meta.get('time', '?')}, {meta.get('rounds', 1)} round(s)")
        if on_complete:
            on_complete(result)

    def _simple_chat(self, user_text, on_token, on_complete, on_error):
        self._chat_history.append({"role": "user", "content": user_text})

        def _worker():
            try:
                result = chat_stream(
                    base_url=self.config.ollama_base_url,
                    model=self.config.selected_model,
                    messages=list(self._chat_history),
                    on_token=on_token,
                    temperature=self.config.temperature,
                    num_ctx=self.config.max_context_tokens,
                )
                content = result.get("content", "")
                self._chat_history.append({"role": "assistant", "content": content})
                meta = {
                    "model": result.get("model", self.config.selected_model),
                    "tokens_in": f"~{result.get('prompt_eval_count', '?')}",
                    "tokens_out": f"~{result.get('eval_count', '?')}",
                    "time": f"{result.get('wall_ms', 0):.0f}ms",
                }
                if on_complete:
                    on_complete({"content": content, "metadata": meta})
            except Exception as e:
                log.exception("Chat request failed")
                self.activity.error("engine", f"Chat failed: {e}")
                if self._chat_history and self._chat_history[-1]["role"] == "user":
                    self._chat_history.pop()
                if on_error:
                    on_error(str(e))

        threading.Thread(target=_worker, daemon=True, name="chat-worker").start()

    def clear_history(self) -> None:
        self._chat_history.clear()
        self.activity.info("engine", "Chat history cleared")

    def get_history(self) -> list[dict[str, str]]:
        return list(self._chat_history)

    def set_history(self, history: list[dict[str, str]]) -> None:
        self._chat_history = list(history)
