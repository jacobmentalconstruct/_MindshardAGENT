"""Agent response loop — manages one user turn through model + optional tool round-trips.

Flow:
  1. User submits prompt
  2. Prompt builder constructs system + session + tool instructions
  3. Model responds (streaming)
  4. If tool call detected, tool router validates and executes
  5. Tool output appended to conversation
  6. Model continues if needed (up to max_rounds)
  7. Final assistant response stored
"""

import threading
from typing import Any, Callable

from src.core.agent.prompt_builder import PromptBuildResult, build_messages, build_system_prompt_bundle
from src.core.agent.tool_router import ToolRouter
from src.core.agent.transcript_formatter import format_all_results
from src.core.ollama.ollama_client import chat_stream
from src.core.sandbox.tool_catalog import ToolCatalog
from src.core.sandbox.command_policy import CommandPolicy
from src.core.config.app_config import AppConfig
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.runtime_logger import get_logger
from src.core.sessions.knowledge_store import KnowledgeStore

log = get_logger("response_loop")

MAX_TOOL_ROUNDS = 5


class ResponseLoop:
    """Manages a single user turn including tool round-trips."""

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
    ):
        self._config = config
        self._command_policy = command_policy
        self._catalog = tool_catalog
        self._router = tool_router
        self._activity = activity
        self._knowledge = knowledge_store
        self._embed_fn = embed_fn          # Callable(str) -> list[float]
        self._session_id_fn = session_id_fn  # Callable() -> str | None
        self._docker_mode = docker_mode
        self._journal = journal            # ActionJournal | None
        self._vcs = None                   # MindshardVCS | None — set by engine
        self._active_project: str = ""     # relative path within sandbox; "" = root
        self._project_meta = None          # ProjectMeta | None — set by engine
        self._last_prompt_build: PromptBuildResult | None = None
        self._last_source_fingerprint: str = ""

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
        """Run a full user turn in a background thread.

        Handles streaming, tool round-trips, and final result delivery.
        """
        def _worker():
            try:
                self._run_turn_sync(
                    user_text, chat_history,
                    on_token, on_complete, on_error,
                    on_tool_start, on_tool_result)
            except Exception as e:
                log.exception("Response loop error")
                if on_error:
                    on_error(str(e))

        thread = threading.Thread(target=_worker, daemon=True, name="response-loop")
        thread.start()

    def _run_turn_sync(
        self,
        user_text: str,
        chat_history: list[dict[str, str]],
        on_token, on_complete, on_error,
        on_tool_start, on_tool_result,
    ) -> None:
        prompt_build = self.preview_prompt(user_text=user_text)

        # Add user message
        history = list(chat_history)
        history.append({"role": "user", "content": user_text})
        messages = build_messages(prompt_build.prompt, history)

        total_content = []
        rounds = 0

        while rounds < MAX_TOOL_ROUNDS:
            rounds += 1
            round_tokens: list[str] = []

            # Stream model response
            self._activity.model("agent", f"Round {rounds}: requesting model response")
            result = chat_stream(
                base_url=self._config.ollama_base_url,
                model=self._config.selected_model,
                messages=messages,
                on_token=lambda t: (round_tokens.append(t), on_token(t) if on_token else None),
                temperature=self._config.temperature,
                num_ctx=self._config.max_context_tokens,
            )

            assistant_text = result.get("content", "".join(round_tokens))
            total_content.append(assistant_text)

            # Check for tool calls
            if self._router.has_tool_calls(assistant_text):
                self._activity.tool("agent", "Tool call detected in response")
                if on_tool_start:
                    on_tool_start(assistant_text)

                tool_results = self._router.execute_all(assistant_text)
                tool_output = format_all_results(tool_results)

                if on_tool_result:
                    on_tool_result({"results": tool_results, "formatted": tool_output})

                # Append assistant message and tool result to history
                messages.append({"role": "assistant", "content": assistant_text})
                messages.append({"role": "user", "content": f"[Tool Results]\n{tool_output}"})

                self._activity.tool("agent", f"Tool round {rounds} complete, continuing...")
                continue
            else:
                # No tool calls, we're done
                break

        # RAG: store user query and assistant response as knowledge
        final_text = "\n".join(total_content)
        if (self._config.rag_enabled and self._knowledge
                and self._embed_fn and self._session_id_fn):
            sid = self._session_id_fn()
            if sid and len(final_text.strip()) > 20:
                try:
                    self._knowledge.add_text(
                        sid, final_text, self._embed_fn,
                        source="chat", source_role="assistant",
                        max_chunk_chars=self._config.rag_chunk_max_chars,
                    )
                    # Also store user query for future context
                    if len(user_text.strip()) > 20:
                        self._knowledge.add_text(
                            sid, user_text, self._embed_fn,
                            source="chat", source_role="user",
                            max_chunk_chars=self._config.rag_chunk_max_chars,
                        )
                except Exception as e:
                    log.warning("RAG storage failed: %s", e)

        # Final result
        meta = {
            "model": result.get("model", self._config.selected_model),
            "tokens_in": f"~{result.get('prompt_eval_count', '?')}",
            "tokens_out": f"~{result.get('eval_count', '?')}",
            "time": f"{result.get('wall_ms', 0):.0f}ms",
            "rounds": rounds,
        }

        if on_complete:
            on_complete({
                "content": "\n".join(total_content),
                "metadata": meta,
                "prompt_build": prompt_build,
                "history_addition": [
                    {"role": "user", "content": user_text},
                    {"role": "assistant", "content": "\n".join(total_content)},
                ],
            })

    def preview_prompt(
        self,
        user_text: str = "",
        chat_history: list[dict[str, str]] | None = None,
    ) -> PromptBuildResult:
        """Build the exact prompt bundle used for the next agent turn."""

        rag_context = self._build_rag_context(user_text)
        journal_context = self._build_journal_context()
        vcs_context = self._build_vcs_context()
        project_brief = ""
        project_meta_path = ""
        if self._project_meta is not None:
            try:
                project_brief = self._project_meta.prompt_context()
                project_meta_path = str(self._project_meta.path)
            except Exception:
                pass

        prompt_build = build_system_prompt_bundle(
            sandbox_root=self._config.sandbox_root,
            tools=self._catalog,
            command_policy=self._command_policy,
            session_title="",
            model_name=self._config.selected_model,
            rag_context=rag_context,
            docker_mode=self._docker_mode,
            journal_context=journal_context,
            vcs_context=vcs_context,
            active_project=self._active_project,
            project_brief=project_brief,
            project_meta_path=project_meta_path,
        )

        if (
            self._last_source_fingerprint
            and prompt_build.source_fingerprint != self._last_source_fingerprint
        ):
            self._activity.info("prompt", "Prompt docs changed; using refreshed prompt sources")

        for warning in prompt_build.warnings:
            log.warning("Prompt source warning: %s", warning)

        self._last_source_fingerprint = prompt_build.source_fingerprint
        self._last_prompt_build = prompt_build
        return prompt_build

    def _build_rag_context(self, user_text: str) -> str:
        rag_context = ""
        if (self._config.rag_enabled and self._knowledge
                and self._embed_fn and self._session_id_fn):
            try:
                sid = self._session_id_fn()
                if sid and self._knowledge.count(sid) > 0:
                    query_vec = self._embed_fn(user_text)
                    hits = self._knowledge.query(
                        sid, query_vec,
                        top_k=self._config.rag_top_k,
                        min_score=self._config.rag_min_score,
                    )
                    if hits:
                        rag_context = "\n---\n".join(
                            f"[{h['source_role']}/{h['source']}] {h['content']}"
                            for h in hits
                        )
                        self._activity.info(
                            "rag", f"Retrieved {len(hits)} chunks (best={hits[0]['score']:.3f})"
                        )
            except Exception as exc:
                log.warning("RAG retrieval failed: %s", exc)
        return rag_context

    def _build_journal_context(self) -> str:
        if self._journal:
            try:
                return self._journal.summary_since(10)
            except Exception:
                return ""
        return ""

    def _build_vcs_context(self) -> str:
        if self._vcs and self._vcs.is_attached:
            try:
                return self._vcs.onboarding_context(limit=5)
            except Exception:
                return ""
        return ""
