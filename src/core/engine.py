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
from src.core.ollama.embedding_client import embed_text, check_embedding_model
from src.core.ollama.tokenizer_adapter import TokenizerAdapter
from src.core.sandbox.sandbox_manager import SandboxManager
from src.core.sandbox.tool_catalog import ToolCatalog
from src.core.sandbox.file_writer import FileWriter
from src.core.sandbox.docker_manager import DockerManager
from src.core.sandbox.docker_runner import DockerRunner
from src.core.agent.tool_router import ToolRouter
from src.core.agent.response_loop import ResponseLoop
from src.core.sandbox.command_policy import CommandPolicy
from src.core.sandbox.tool_discovery import register_discovered_tools
from src.core.sessions.knowledge_store import KnowledgeStore
from src.core.runtime.action_journal import ActionJournal
import src.core.runtime.action_journal as aj

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
        self.docker_manager = DockerManager(activity)
        self.docker_runner: DockerRunner | None = None
        self.tool_catalog = ToolCatalog()
        self.tool_router: ToolRouter | None = None
        self.response_loop: ResponseLoop | None = None

        # RAG
        self.knowledge: KnowledgeStore | None = None
        self._embedding_available = False
        self._session_id_fn = None  # set by app.py

        # Action journal (initialized when sandbox is set)
        self.journal: ActionJournal | None = None

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
        """Initialize or change the sandbox root.

        If docker_enabled is True in config and Docker is available,
        commands execute inside a container. Otherwise falls back to
        local subprocess with allowlist policy.
        """
        # Always create the local sandbox manager (for PathGuard, AuditLog, structure)
        self.sandbox = SandboxManager(sandbox_root, self.activity,
                                       on_confirm_destructive=self._on_confirm_destructive)

        # Action journal
        self.journal = ActionJournal(sandbox_root)

        # File writer always operates host-side (volume mount keeps files in sync)
        self.file_writer = FileWriter(
            self.sandbox.guard, self.activity,
            audit_log=self.sandbox.audit,
        )

        # Choose CLI runner: Docker container or local subprocess
        if self.config.docker_enabled and self.docker_manager.is_docker_available():
            # Docker mode — commands run inside container
            self.docker_runner = DockerRunner(
                self.docker_manager, self.activity,
                on_confirm_destructive=self._on_confirm_destructive,
                audit_log=self.sandbox.audit,
            )
            self.command_policy = CommandPolicy(mode="permissive")
            cli_runner = self.docker_runner
            self.activity.info("engine",
                f"Docker sandbox mode — container: {self.docker_manager.container_status()}")
        else:
            # Local mode — commands run in Windows subprocess with allowlist
            self.command_policy = CommandPolicy(mode="allowlist")
            cli_runner = self.sandbox.cli
            self.docker_runner = None
            if self.config.docker_enabled:
                self.activity.warn("engine",
                    "Docker enabled but not available — falling back to local sandbox")

        self.tool_router = ToolRouter(
            self.tool_catalog, cli_runner, self.activity,
            file_writer=self.file_writer,
        )
        self.response_loop = ResponseLoop(
            self.config, self.tool_catalog, self.tool_router, self.activity,
            command_policy=self.command_policy if not self.docker_runner else None,
            knowledge_store=self.knowledge,
            embed_fn=self._embed if self._embedding_available else None,
            session_id_fn=self._session_id_fn,
            docker_mode=bool(self.docker_runner),
            journal=self.journal,
        )
        self.config.sandbox_root = sandbox_root
        # Discover sandbox-local tools
        n_tools = register_discovered_tools(self.tool_catalog, sandbox_root)

        mode_str = "Docker container" if self.docker_runner else "local subprocess"
        self.activity.info("engine", f"Sandbox set: {sandbox_root} ({mode_str})")
        if not self.docker_runner:
            self.activity.info("engine",
                f"Command policy: allowlist mode, {len(self.command_policy._allowed)} commands permitted")
        if n_tools:
            self.activity.info("engine", f"Discovered {n_tools} sandbox tool(s)")
        self.journal.record(aj.CONFIG_CHANGE, f"Sandbox set: {mode_str} mode",
                            {"sandbox_root": sandbox_root, "mode": mode_str,
                             "tools_discovered": n_tools})
        log.info("Sandbox initialized: %s (mode=%s)", sandbox_root, mode_str)

    def set_knowledge_store(self, knowledge: KnowledgeStore,
                            session_id_fn=None) -> None:
        """Attach a knowledge store for RAG. Called by app.py after session init."""
        self.knowledge = knowledge
        if session_id_fn:
            self._session_id_fn = session_id_fn
        # Update response loop if it exists
        if self.response_loop:
            self.response_loop._knowledge = knowledge
            self.response_loop._session_id_fn = self._session_id_fn
            if self._embedding_available:
                self.response_loop._embed_fn = self._embed

    def check_embeddings(self) -> bool:
        """Check if the embedding model is available. Call on startup."""
        info = check_embedding_model(
            base_url=self.config.ollama_base_url,
            model=self.config.embedding_model,
        )
        self._embedding_available = info["available"]
        if info["available"]:
            self.activity.info("rag",
                f"Embedding model ready: {info['model']} ({info['dim']}-dim)")
            # Update response loop embed fn
            if self.response_loop:
                self.response_loop._embed_fn = self._embed
        else:
            self.activity.warn("rag",
                f"Embedding model {self.config.embedding_model} not available — RAG disabled")
        return self._embedding_available

    def _embed(self, text: str) -> list[float]:
        """Embed text using the configured Ollama model."""
        return embed_text(
            text,
            base_url=self.config.ollama_base_url,
            model=self.config.embedding_model,
        )

    def run_cli(self, command: str, cwd: str | None = None) -> dict[str, Any]:
        """Execute a CLI command directly in the sandbox (for the CLI panel)."""
        if not self.sandbox:
            return {"stdout": "", "stderr": "No sandbox configured", "exit_code": -1,
                    "command": command, "cwd": "", "started_at": "", "finished_at": ""}
        if self.docker_runner:
            return self.docker_runner.run(command, cwd=cwd)
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
        # Learn tokenizer ratio from actual response
        content = result.get("content", "")
        tokens_out_raw = str(meta.get("tokens_out", "")).replace("~", "")
        if tokens_out_raw.isdigit() and int(tokens_out_raw) > 0 and content:
            self.tokenizer.learn_from_response(
                self.config.selected_model, len(content), int(tokens_out_raw))
        self.activity.model("engine",
                            f"Response complete: {meta.get('tokens_out', '?')} tokens, "
                            f"{meta.get('time', '?')}, {meta.get('rounds', 1)} round(s)")
        if self.journal:
            self.journal.record(aj.AGENT_TURN,
                f"Response: {meta.get('tokens_out', '?')} tokens, {meta.get('rounds', 1)} round(s)",
                {"model": meta.get("model", ""), "rounds": meta.get("rounds", 1),
                 "tokens_out": str(meta.get("tokens_out", "")),
                 "content_preview": content[:100] if content else ""})
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
