"""Agent response loop — threading interface and workspace/RAG state binding.

Owns:
  - Background thread spawn for async turn execution
  - Stop-request protocol (flag polled by TurnPipeline via callable)
  - Workspace context state (vcs, active_project, project_meta)
  - RAG/embedding state (knowledge store, embed_fn, session_id_fn)
  - Public loop interface (run_turn, run, request_stop, preview_prompt)

Delegates all stage sequencing logic to TurnPipeline.

Flow:
  1. run_turn() spawns a worker thread
  2. Worker calls self._make_pipeline().run(...)
  3. TurnPipeline owns the full stage algorithm
  4. request_stop() sets a flag; TurnPipeline polls it via should_stop callable
"""

import threading
from typing import Any, Callable

from src.core.agent.loop_types import TOOL_AGENT_LOOP
from src.core.agent.prompt_builder import PromptBuildResult
from src.core.agent.tool_router import ToolRouter
from src.core.agent.turn_pipeline import TurnPipeline
from src.core.config.app_config import AppConfig
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.runtime_logger import get_logger
from src.core.sandbox.command_policy import CommandPolicy
from src.core.sandbox.file_writer import FileWriter
from src.core.sandbox.tool_catalog import ToolCatalog
from src.core.sessions.knowledge_store import KnowledgeStore

log = get_logger("response_loop")


class ResponseLoop:
    """Threading interface and state binder for the turn pipeline."""

    loop_id = TOOL_AGENT_LOOP

    def __init__(
        self,
        config: AppConfig,
        tool_catalog: ToolCatalog,
        tool_router: ToolRouter,
        activity: ActivityStream,
        command_policy: CommandPolicy | None = None,
        knowledge_store: KnowledgeStore | None = None,
        embed_fn=None,
        session_id_fn=None,
        docker_mode: bool = False,
        journal=None,
        file_writer: FileWriter | None = None,
        evidence_bag=None,
    ):
        self._config = config
        self._command_policy = command_policy
        self._catalog = tool_catalog
        self._router = tool_router
        self._activity = activity
        self._knowledge = knowledge_store
        self._file_writer = file_writer
        self._embed_fn = embed_fn
        self._session_id_fn = session_id_fn
        self._docker_mode = docker_mode
        self._journal = journal
        self._evidence_bag = evidence_bag
        self._vcs = None
        self._active_project: str = ""
        self._project_meta = None
        self._last_prompt_build: PromptBuildResult | None = None
        self._last_source_fingerprint: str = ""
        self._stop_requested = False
        self._worker_thread: threading.Thread | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def set_workspace(self, *, vcs=None, active_project: str = "", project_meta=None):
        """Set workspace context. Called by engine when project/VCS state changes."""
        self._vcs = vcs
        self._active_project = active_project
        self._project_meta = project_meta

    def set_rag_context(self, *, knowledge=None, session_id_fn=None, embed_fn=None):
        """Update RAG/embedding context. Called by engine when knowledge store changes."""
        if knowledge is not None:
            self._knowledge = knowledge
        if session_id_fn is not None:
            self._session_id_fn = session_id_fn
        if embed_fn is not None:
            self._embed_fn = embed_fn

    def set_evidence_bag(self, evidence_bag) -> None:
        """Attach or replace the evidence bag adapter. Called by engine."""
        self._evidence_bag = evidence_bag

    def run_turn(
        self,
        user_text: str,
        chat_history: list[dict[str, str]],
        on_token: Callable[[str], None] | None = None,
        on_complete: Callable[[dict[str, Any]], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_tool_start: Callable[[str], None] | None = None,
        on_tool_result: Callable[[dict], None] | None = None,
    ) -> None:
        """Run a full user turn in a background thread."""
        def _worker():
            try:
                self._stop_requested = False
                self._make_pipeline().run(
                    user_text, chat_history,
                    on_token, on_complete, on_error,
                    on_tool_start, on_tool_result,
                )
            except Exception as e:
                log.exception("Response loop error")
                if on_error:
                    on_error(str(e))

        thread = threading.Thread(target=_worker, daemon=True, name="response-loop")
        self._worker_thread = thread
        thread.start()

    def run(self, request) -> None:
        """Adapter entrypoint so the response loop can be managed as a loop module."""
        self.run_turn(
            user_text=request.user_text,
            chat_history=request.chat_history,
            on_token=request.on_token,
            on_complete=request.on_complete,
            on_error=request.on_error,
            on_tool_start=request.on_tool_start,
            on_tool_result=request.on_tool_result,
        )

    def request_stop(self) -> None:
        """Request that the current response loop stop after the next stream chunk."""
        self._stop_requested = True

    def join(self, timeout: float = 3.0) -> None:
        """Block until the worker thread finishes (or timeout expires).

        Call this during shutdown before closing the session store or any other
        shared resource, to prevent the in-flight turn from hitting closed state.
        """
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)

    def preview_prompt(
        self,
        user_text: str = "",
        chat_history: list[dict[str, str]] | None = None,
    ) -> PromptBuildResult:
        """Build the exact prompt bundle used for the next agent turn."""
        result = self._make_pipeline().build_prompt(user_text=user_text)

        if (
            self._last_source_fingerprint
            and result.source_fingerprint != self._last_source_fingerprint
        ):
            self._activity.info("prompt", "Prompt docs changed; using refreshed prompt sources")

        self._last_source_fingerprint = result.source_fingerprint
        self._last_prompt_build = result
        return result

    # ── Private ───────────────────────────────────────────────────────────────

    def _make_pipeline(self) -> TurnPipeline:
        """Construct a TurnPipeline with the current workspace/RAG state snapshot."""
        return TurnPipeline(
            self._config,
            self._catalog,
            self._router,
            self._activity,
            command_policy=self._command_policy,
            knowledge_store=self._knowledge,
            embed_fn=self._embed_fn,
            session_id_fn=self._session_id_fn,
            docker_mode=self._docker_mode,
            journal=self._journal,
            file_writer=self._file_writer,
            evidence_bag=self._evidence_bag,
            vcs=self._vcs,
            active_project=self._active_project,
            project_meta=self._project_meta,
            should_stop=lambda: self._stop_requested,
        )
