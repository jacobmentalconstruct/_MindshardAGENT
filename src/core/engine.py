"""Main runtime coordinator.

Owns the active session context. Receives UI actions, routes them to
model/tool/session subsystems, and pushes structured activity events
back to the UI via the activity stream and event bus.
"""

import threading
from typing import Any, Callable

from src.core.config.app_config import AppConfig
from src.core.agent.direct_chat_loop import DirectChatLoop
from src.core.agent.loop_manager import LoopManager
from src.core.agent.loop_types import LoopRequest
from src.core.agent.model_roles import EMBEDDING_ROLE, PRIMARY_CHAT_ROLE, resolve_model_for_role
from src.core.agent.planner_only_loop import PlannerOnlyLoop
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
from src.core.sandbox.python_runner import PythonRunner
from src.core.agent.tool_router import ToolRouter
from src.core.agent.response_loop import ResponseLoop
from src.core.agent.thought_chain_loop import ThoughtChainLoop
from src.core.agent.thought_chain import ThoughtChain
from src.core.sandbox.command_policy import CommandPolicy
from src.core.sandbox.tool_discovery import register_discovered_tools
from src.core.sessions.knowledge_store import KnowledgeStore
from src.core.runtime.action_journal import ActionJournal
from src.core.vcs.mindshard_vcs import MindshardVCS
from src.core.project.project_meta import ProjectMeta
from src.core.vault.memory_vault import MemoryVault
from src.core.agent.prompt_builder import PromptBuildResult
import src.core.runtime.action_journal as aj

log = get_logger("engine")


class Engine:
    """Central runtime coordinator for the application."""

    def __init__(self, config: AppConfig, activity: ActivityStream, bus: EventBus,
                 on_confirm_destructive=None, on_tools_reloaded=None,
                 on_confirm_gui_launch=None):
        self.config = config
        self.activity = activity
        self.bus = bus
        self.tokenizer = TokenizerAdapter()
        self._running = False
        self._chat_history: list[dict[str, str]] = []
        self._on_confirm_destructive = on_confirm_destructive
        self._on_tools_reloaded = on_tools_reloaded  # callback(count, names)
        self._on_confirm_gui_launch = on_confirm_gui_launch

        # Active project path (relative to sandbox root)
        # "" means sandbox root IS the project; "my_app" means sandbox/my_app/ is the project
        self.active_project: str = ""

        # Project metadata — .mindshard/state/project_meta.json (set in set_sandbox)
        self.project_meta: ProjectMeta | None = None

        # Sandbox + tools (initialized when sandbox is set)
        self.sandbox: SandboxManager | None = None
        self.docker_manager = DockerManager(activity, sandbox_root=config.sandbox_root or "")
        self.docker_runner: DockerRunner | None = None
        self.tool_catalog = ToolCatalog()
        self.tool_router: ToolRouter | None = None
        self.response_loop: ResponseLoop | None = None
        self.python_runner: PythonRunner | None = None
        self.loop_manager = LoopManager(activity)

        # RAG
        self.knowledge: KnowledgeStore | None = None
        self._embedding_available = False
        self._session_id_fn = None  # set by app.py

        # Action journal (initialized when sandbox is set)
        self.journal: ActionJournal | None = None

        # Local VCS — .mindshard/ git repo inside sandbox root
        self.vcs = MindshardVCS()

        # Global memory vault — index of all detached projects
        self.vault = MemoryVault()

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
        # Update Docker container name for this sandbox path
        self.docker_manager.set_sandbox_root(sandbox_root)

        # Always create the local sandbox manager (for PathGuard, AuditLog, structure)
        self.sandbox = SandboxManager(sandbox_root, self.activity,
                                       on_confirm_destructive=self._on_confirm_destructive,
                                       gui_policy_getter=lambda: self.config.gui_launch_policy,
                                       on_confirm_gui_launch=self._on_confirm_gui_launch)

        # Ensure standard workspace dirs exist
        self._init_workspace_dirs(sandbox_root)

        # Project metadata
        self.project_meta = ProjectMeta(sandbox_root)

        # Action journal
        self.journal = ActionJournal(sandbox_root)

        # VCS — attach to sandbox root (creates .mindshard/ if new)
        try:
            self.vcs.attach(sandbox_root)
        except Exception as e:
            log.warning("VCS attach failed: %s", e)

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
            self.python_runner = PythonRunner(
                self.sandbox.guard,
                self.activity,
                audit_log=self.sandbox.audit,
                docker_manager=self.docker_manager,
                gui_policy_getter=lambda: self.config.gui_launch_policy,
                on_confirm_gui_launch=self._on_confirm_gui_launch,
            )
            self.activity.info("engine",
                f"Docker sandbox mode — container: {self.docker_manager.container_status()}")
        else:
            # Local mode — commands run in Windows subprocess with allowlist
            self.command_policy = CommandPolicy(mode="allowlist")
            cli_runner = self.sandbox.cli
            self.docker_runner = None
            self.python_runner = PythonRunner(
                self.sandbox.guard,
                self.activity,
                audit_log=self.sandbox.audit,
                gui_policy_getter=lambda: self.config.gui_launch_policy,
                on_confirm_gui_launch=self._on_confirm_gui_launch,
            )
            if self.config.docker_enabled:
                self.activity.warn("engine",
                    "Docker enabled but not available — falling back to local sandbox")

        self.tool_router = ToolRouter(
            self.tool_catalog, cli_runner, self.activity,
            file_writer=self.file_writer,
            sandbox_root=sandbox_root,
            on_tools_reloaded=self._on_tools_reloaded,
            python_runner=self.python_runner,
        )
        self.response_loop = ResponseLoop(
            self.config, self.tool_catalog, self.tool_router, self.activity,
            command_policy=self.command_policy if not self.docker_runner else None,
            knowledge_store=self.knowledge,
            embed_fn=self._embed if self._embedding_available else None,
            session_id_fn=self._session_id_fn,
            docker_mode=bool(self.docker_runner),
            journal=self.journal,
            file_writer=self.file_writer,
        )
        self.response_loop._vcs = self.vcs
        self.response_loop._active_project = self.active_project
        self.response_loop._project_meta = self.project_meta
        self._register_loops()
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

    def _init_workspace_dirs(self, sandbox_root: str) -> None:
        """Create .mindshard/ sidecar subdirectories if they don't exist."""
        from pathlib import Path
        root = Path(sandbox_root)
        sidecar = root / ".mindshard"
        for d in ("vcs", "sessions", "logs", "tools", "parts", "ref", "outputs", "state", "runs"):
            (sidecar / d).mkdir(parents=True, exist_ok=True)

    def set_active_project(self, project_path: str) -> None:
        """Set the focal project path (relative to sandbox root).

        Pass "" to clear (sandbox root = workspace).
        Pass "my_app" when that folder is the thing being worked on.
        """
        self.active_project = project_path
        if self.response_loop:
            self.response_loop._active_project = project_path
        self._register_loops()
        log.info("Active project: %s", project_path or "(sandbox root)")

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
        self._register_loops()

    def _register_loops(self) -> None:
        """Rebuild the loop registry from the current runtime state."""
        self.loop_manager = LoopManager(self.activity)
        self.loop_manager.register(DirectChatLoop(self.config, self.activity))
        self.loop_manager.register(
            PlannerOnlyLoop(
                self.config,
                self.activity,
                self.tool_catalog,
                sandbox_root_getter=lambda: self.config.sandbox_root,
                active_project_getter=lambda: self.active_project,
            )
        )
        self.loop_manager.register(ThoughtChainLoop(self.config, self.activity))
        if self.response_loop is not None:
            self.loop_manager.register(self.response_loop)

    def check_embeddings(self) -> bool:
        """Check if the embedding model is available. Call on startup."""
        info = check_embedding_model(
            base_url=self.config.ollama_base_url,
            model=resolve_model_for_role(self.config, EMBEDDING_ROLE),
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
                f"Embedding model {resolve_model_for_role(self.config, EMBEDDING_ROLE)} not available — RAG disabled")
        return self._embedding_available

    def _embed(self, text: str) -> list[float]:
        """Embed text using the configured Ollama model."""
        return embed_text(
            text,
            base_url=self.config.ollama_base_url,
            model=resolve_model_for_role(self.config, EMBEDDING_ROLE),
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
        """Submit a user prompt through the loop manager."""

        model = resolve_model_for_role(self.config, PRIMARY_CHAT_ROLE)
        if not model:
            if on_error:
                on_error("No model selected")
            return

        token_est = self.tokenizer.count(user_text)
        self.activity.model("engine", f"Sending prompt to {model} (~{token_est} tokens)")

        request = LoopRequest(
            user_text=user_text,
            chat_history=list(self._chat_history),
            on_token=on_token,
            on_complete=lambda result: self._handle_loop_complete(result, on_complete),
            on_error=on_error,
        )
        try:
            selected_loop = self.loop_manager.run(request)
            self.activity.info("engine", f"Loop dispatched: {selected_loop}")
        except Exception as exc:
            self.activity.error("engine", f"Loop dispatch failed: {exc}")
            if on_error:
                on_error(str(exc))

    def run_thought_chain(
        self,
        goal: str,
        depth: int = 3,
        on_round: Callable[[int, str], None] | None = None,
        on_complete: Callable[[dict[str, Any]], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        """Run a Cannibalistic Thought Chain to decompose a goal into tasks."""
        chain = ThoughtChain(self.config, self.activity)
        chain.run(goal, depth=depth,
                  on_round=on_round, on_complete=on_complete, on_error=on_error)

    def _handle_loop_complete(self, result: dict, on_complete) -> None:
        additions = result.get("history_addition", [])
        self._chat_history.extend(additions)
        meta = result.get("metadata", {})
        # Learn tokenizer ratio from actual response
        content = result.get("content", "")
        tokens_out_raw = str(meta.get("tokens_out", "")).replace("~", "")
        current_model = resolve_model_for_role(self.config, PRIMARY_CHAT_ROLE)
        if tokens_out_raw.isdigit() and int(tokens_out_raw) > 0 and content and current_model:
            self.tokenizer.learn_from_response(
                current_model, len(content), int(tokens_out_raw))
        self.activity.model("engine",
                            f"Response complete [{meta.get('loop_mode', 'unknown')}]: {meta.get('tokens_out', '?')} tokens, "
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
        model = resolve_model_for_role(self.config, PRIMARY_CHAT_ROLE)
        self._chat_history.append({"role": "user", "content": user_text})

        def _worker():
            try:
                result = chat_stream(
                    base_url=self.config.ollama_base_url,
                    model=model,
                    messages=list(self._chat_history),
                    on_token=on_token,
                    temperature=self.config.temperature,
                    num_ctx=self.config.max_context_tokens,
                )
                content = result.get("content", "")
                self._chat_history.append({"role": "assistant", "content": content})
                meta = {
                    "model": result.get("model", model),
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

    def request_stop(self) -> None:
        """Request that the active loop stop as soon as possible."""
        self.loop_manager.request_stop()
        self.activity.info("engine", "Stop requested")

    def get_history(self) -> list[dict[str, str]]:
        return list(self._chat_history)

    def preview_system_prompt(
        self,
        user_text: str = "",
        chat_history: list[dict[str, str]] | None = None,
    ) -> PromptBuildResult | None:
        """Build the prompt bundle used for previews and the next agent turn."""
        if not self.response_loop:
            return None
        history = list(chat_history) if chat_history is not None else list(self._chat_history)
        return self.response_loop.preview_prompt(user_text=user_text, chat_history=history)

    def detach_project(self, on_progress=None, keep_sidecar: bool = False) -> dict:
        """Final snapshot → archive .mindshard/ → register in vault → delete sidecar."""
        from src.core.project.project_archiver import archive_sidecar, remove_sidecar
        result = {"success": False, "error": None, "archive_path": "", "sidecar_retained": keep_sidecar}

        if not self.config.sandbox_root:
            result["error"] = "No project attached"
            return result

        # 1. Final VCS snapshot
        snap_hash = None
        if self.vcs.is_attached:
            try:
                snap_hash = self.vcs.snapshot("Final snapshot — MindshardAGENT detaching")
            except Exception as e:
                log.warning("Final snapshot failed: %s", e)

        if on_progress:
            on_progress("Archiving .mindshard/ ...")

        # 2. Archive sidecar
        archive_result = archive_sidecar(
            self.config.sandbox_root,
            self.vault.vault_dir,
            final_snapshot_hash=snap_hash,
        )
        if not archive_result["success"]:
            result["error"] = archive_result.get("error", "Archive failed")
            return result

        if on_progress:
            on_progress("Registering in memory vault ...")

        # 3. Register in vault
        meta_data = {}
        if self.project_meta:
            meta_data = {
                "project_root": self.config.sandbox_root,
                "source_path": self.project_meta.source_path or "",
                "profile": self.project_meta.profile,
                "project_purpose": self.project_meta.get("project_purpose", ""),
                "current_goal": self.project_meta.get("current_goal", ""),
            }
        self.vault.register(archive_result, meta_data)

        if not keep_sidecar:
            if on_progress:
                on_progress("Removing .mindshard/ ...")

            # 4. Remove sidecar
            removed = remove_sidecar(self.config.sandbox_root)
            if not removed:
                result["error"] = "Archive saved but sidecar removal failed"
                result["archive_path"] = archive_result["archive_path"]
                return result

        # 5. Clear runtime state
        self.vcs = MindshardVCS()  # reset
        self.project_meta = None
        self.config.sandbox_root = ""

        result["success"] = True
        result["archive_path"] = archive_result["archive_path"]
        result["project_name"] = archive_result["project_name"]
        return result

    def set_history(self, history: list[dict[str, str]]) -> None:
        self._chat_history = list(history)
