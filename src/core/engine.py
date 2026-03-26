"""Main runtime coordinator.

Owns the active session context. Receives UI actions, routes them to
model/tool/session subsystems, and pushes structured activity events
back to the UI via the activity stream and event bus.
"""

from typing import Any, Callable

from src.core.config.app_config import AppConfig
from src.core.agent.loop_manager import LoopManager
from src.core.agent.loop_registry import build_loop_manager
from src.core.agent.loop_types import LoopRequest
from src.core.agent.model_roles import PRIMARY_CHAT_ROLE, resolve_model_for_role
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.event_bus import EventBus
from src.core.runtime.runtime_logger import get_logger
from src.core.ollama.embedding_service import EmbeddingService
from src.core.ollama.tokenizer_adapter import TokenizerAdapter
from src.core.sandbox.sandbox_manager import SandboxManager
from src.core.sandbox.sandbox_runtime_factory import build_sandbox_runtime
from src.core.sandbox.tool_catalog import ToolCatalog
from src.core.sandbox.file_writer import FileWriter
from src.core.sandbox.docker_manager import DockerManager
from src.core.agent.tool_router import ToolRouter
from src.core.agent.response_loop import ResponseLoop
from src.core.agent.thought_chain import ThoughtChain
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
        self.docker_runner = None        # set by build_sandbox_runtime
        self.tool_catalog = ToolCatalog()
        self.tool_router: ToolRouter | None = None
        self.response_loop: ResponseLoop | None = None
        self.python_runner = None        # set by build_sandbox_runtime
        self.loop_manager = LoopManager(activity)

        # Embedding (availability check + embed function — owned by EmbeddingService)
        self.embedding_service = EmbeddingService(config, activity)

        # RAG
        self.knowledge: KnowledgeStore | None = None
        self._session_id_fn = None  # set by app.py

        # Evidence bag (tiered memory — STM falloff destination)
        self.evidence_bag = None  # EvidenceBagAdapter | None

        # Action journal (initialized when sandbox is set)
        self.journal: ActionJournal | None = None

        # Standalone thought chain (Plan button path — tracked for shutdown drain)
        self._active_thought_chain: ThoughtChain | None = None

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

        Delegates backend selection to sandbox_runtime_factory — engine stores
        the result but does not own the docker-vs-local decision.
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

        # Select execution backend (Docker container or local subprocess)
        runtime = build_sandbox_runtime(
            self.config, self.sandbox, self.docker_manager,
            activity=self.activity,
            on_confirm_destructive=self._on_confirm_destructive,
            on_confirm_gui_launch=self._on_confirm_gui_launch,
        )
        self.docker_runner = runtime.docker_runner
        self.python_runner = runtime.python_runner
        self.command_policy = runtime.command_policy

        self.tool_router = ToolRouter(
            self.tool_catalog, runtime.cli_runner, self.activity,
            file_writer=self.file_writer,
            sandbox_root=sandbox_root,
            on_tools_reloaded=self._on_tools_reloaded,
            reload_tools_fn=self.reload_discovered_tools,
            python_runner=self.python_runner,
        )

        # Initialize evidence bag adapter if enabled
        if self.config.evidence_bag_enabled:
            try:
                from src.core.sessions.evidence_adapter import EvidenceBagAdapter
                from pathlib import Path
                evidence_dir = Path(sandbox_root) / ".mindshard" / "sessions"
                self.evidence_bag = EvidenceBagAdapter(evidence_dir)
                self.activity.info("engine", "Evidence bag adapter initialized")
            except Exception as exc:
                log.warning("Evidence bag init failed (non-fatal): %s", exc)
                self.evidence_bag = None

        self.response_loop = ResponseLoop(
            self.config, self.tool_catalog, self.tool_router, self.activity,
            command_policy=self.command_policy if not self.docker_runner else None,
            knowledge_store=self.knowledge,
            embed_fn=self.embedding_service.get_fn(),
            session_id_fn=self._session_id_fn,
            docker_mode=bool(self.docker_runner),
            journal=self.journal,
            file_writer=self.file_writer,
            evidence_bag=self.evidence_bag,
        )
        self.response_loop.set_workspace(
            vcs=self.vcs,
            active_project=self.active_project,
            project_meta=self.project_meta,
        )
        self._rebuild_loops()
        self.config.sandbox_root = sandbox_root

        discovered_names = self.reload_discovered_tools()
        n_tools = len([name for name in discovered_names if self.tool_catalog.get(name).source == "sandbox_local"])
        n_toolbox = len([name for name in discovered_names if self.tool_catalog.get(name).source == "toolbox"])

        mode_str = "Docker container" if self.docker_runner else "local subprocess"
        self.activity.info("engine", f"Sandbox set: {sandbox_root} ({mode_str})")
        if not self.docker_runner:
            self.activity.info("engine",
                f"Command policy: allowlist mode, {len(self.command_policy._allowed)} commands permitted")
        if n_tools:
            self.activity.info("engine", f"Discovered {n_tools} sandbox tool(s)")
        if n_toolbox:
            self.activity.info("engine", f"Discovered {n_toolbox} toolbox tool(s)")
        self.journal.record(aj.CONFIG_CHANGE, f"Sandbox set: {mode_str} mode",
                            {"sandbox_root": sandbox_root, "mode": mode_str,
                             "tools_discovered": len(discovered_names)})
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
            self.response_loop.set_workspace(
                vcs=self.vcs,
                active_project=project_path,
                project_meta=self.project_meta,
            )
        self._rebuild_loops()
        log.info("Active project: %s", project_path or "(sandbox root)")

    def set_knowledge_store(self, knowledge: KnowledgeStore,
                            session_id_fn=None) -> None:
        """Attach a knowledge store for RAG. Called by app.py after session init."""
        self.knowledge = knowledge
        if session_id_fn:
            self._session_id_fn = session_id_fn
        if self.response_loop:
            self.response_loop.set_rag_context(
                knowledge=knowledge,
                session_id_fn=self._session_id_fn,
                embed_fn=self.embedding_service.get_fn(),
            )
        self._rebuild_loops()

    def set_evidence_bag(self, evidence_bag) -> None:
        """Attach an evidence bag adapter. Called if bag is initialized after engine setup."""
        self.evidence_bag = evidence_bag
        if self.response_loop:
            self.response_loop.set_evidence_bag(evidence_bag)

    def _rebuild_loops(self) -> None:
        """Rebuild the loop manager from current runtime state via loop_registry."""
        self.loop_manager = build_loop_manager(
            config=self.config,
            activity=self.activity,
            tool_catalog=self.tool_catalog,
            response_loop=self.response_loop,
            sandbox_root_getter=lambda: self.config.sandbox_root,
            active_project_getter=lambda: self.active_project,
        )

    def check_embeddings(self) -> bool:
        """Check if the embedding model is available. Call on startup."""
        available = self.embedding_service.check()
        if available and self.response_loop:
            self.response_loop.set_rag_context(embed_fn=self.embedding_service.embed)
        return available

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
        mode_hint: str | None = None,
    ) -> None:
        """Submit a user prompt through the loop manager.

        mode_hint — when non-empty, forces a specific loop mode (e.g. "direct_chat",
        "tool_agent", "planner_only", "thought_chain").  None or empty string means
        automatic selection via loop_selector.
        """
        model = resolve_model_for_role(self.config, PRIMARY_CHAT_ROLE)
        if not model:
            if on_error:
                on_error("No model selected")
            return

        token_est = self.tokenizer.count(user_text)
        effective_mode = mode_hint or None
        self.activity.model(
            "engine",
            f"Sending prompt to {model} (~{token_est} tokens)"
            + (f" [mode: {effective_mode}]" if effective_mode else ""),
        )

        request = LoopRequest(
            user_text=user_text,
            chat_history=list(self._chat_history),
            on_token=on_token,
            on_complete=lambda result: self._handle_loop_complete(result, on_complete),
            on_error=on_error,
            mode_hint=effective_mode,
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
        goal_context: str = "",
        depth: int = 3,
        on_round: Callable[[int, str], None] | None = None,
        on_complete: Callable[[dict[str, Any]], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        """Run a Cannibalistic Thought Chain to decompose a goal into tasks."""
        chain = ThoughtChain(self.config, self.activity)
        self._active_thought_chain = chain

        def _clear_active() -> None:
            if self._active_thought_chain is chain:
                self._active_thought_chain = None

        def _wrapped_complete(result: dict[str, Any]) -> None:
            _clear_active()
            if on_complete:
                on_complete(result)

        def _wrapped_error(err: str) -> None:
            _clear_active()
            if on_error:
                on_error(err)

        chain.run(
            goal,
            goal_context=goal_context,
            depth=depth,
            on_round=on_round,
            on_complete=_wrapped_complete,
            on_error=_wrapped_error,
        )

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

    def clear_history(self) -> None:
        self._chat_history.clear()
        self.activity.info("engine", "Chat history cleared")

    def request_stop(self) -> None:
        """Request that the active loop stop as soon as possible."""
        self.loop_manager.request_stop()
        if self._active_thought_chain is not None:
            self._active_thought_chain.request_stop()
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
        """Delegate project detachment to project_lifecycle.detach()."""
        from src.core.project.project_lifecycle import detach
        return detach(self, on_progress=on_progress, keep_sidecar=keep_sidecar)

    def set_history(self, history: list[dict[str, str]]) -> None:
        self._chat_history = list(history)

    def reload_discovered_tools(self) -> list[str]:
        """Reload all non-builtin tools from the active sandbox and toolbox root."""
        from pathlib import Path

        sandbox_root = str(self.config.sandbox_root or "").strip()
        toolbox_root = str(self.config.toolbox_root or "").strip()

        self.tool_catalog.clear_discovered_tools()

        if sandbox_root:
            register_discovered_tools(
                self.tool_catalog,
                sandbox_root,
                source="sandbox_local",
            )

        toolbox_names: list[str] = []
        if toolbox_root:
            if Path(toolbox_root).is_dir():
                before = set(self.tool_catalog.discovered_tool_names())
                register_discovered_tools(
                    self.tool_catalog,
                    toolbox_root,
                    source="toolbox",
                )
                after = self.tool_catalog.discovered_tool_names()
                toolbox_names = [name for name in after if name not in before]
            else:
                self.activity.warn("engine", f"Toolbox root not found: {toolbox_root}")

        names = self.tool_catalog.discovered_tool_names()
        if self._on_tools_reloaded:
            self._on_tools_reloaded(len(names), names)
        log.info(
            "Reloaded discovered tools: %d sandbox, %d toolbox",
            len(self.tool_catalog.sandbox_tool_names()),
            len(toolbox_names),
        )
        return names
