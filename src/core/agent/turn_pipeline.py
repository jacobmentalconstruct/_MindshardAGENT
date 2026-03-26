"""Turn pipeline — owns the sequential stage algorithm for one agent turn.

Extracted from response_loop._run_turn_sync (was 217 lines inline).

Owns:
  - Stage sequencing: planner → context gather → probe → turn assembly →
    streaming+tool loop → evidence pass → RAG storage → metadata build
  - Prompt context building: RAG retrieval, journal summary, VCS context, project brief
  - Prompt bundle construction (delegates to prompt_builder)

Does NOT own:
  - Threading or async scheduling (that is ResponseLoop's job)
  - Stop-request state (caller passes `should_stop` callable)
  - Workspace/RAG binding state (caller passes all context at construction)

Usage:
  pipeline = TurnPipeline(config, catalog, router, activity, ...)
  result = pipeline.run(user_text, chat_history, on_token, on_complete, on_error)
  prompt_build = pipeline.build_prompt(user_text)
"""

from __future__ import annotations

from typing import Any, Callable

from src.core.agent.context_gatherer import gather_workspace_context
from src.core.agent.evidence_pass import run_evidence_pass
from src.core.agent.execution_planner import run_execution_planner
from src.core.agent.loop_types import TOOL_AGENT_LOOP, build_loop_result
from src.core.agent.model_roles import PRIMARY_CHAT_ROLE, resolve_model_for_role
from src.core.agent.probe_stage import run_probe_stage
from src.core.agent.prompt_builder import PromptBuildResult, build_system_prompt_bundle
from src.core.agent.stage_context import StageContext, format_stage_context
from src.core.agent.tool_router import ToolRouter
from src.core.agent.tool_agent_turn_runner import run_tool_agent_turn
from src.core.agent.turn_prompt_context import (
    build_journal_context,
    build_rag_context,
    build_vcs_context,
)
from src.core.agent.turn_assembler import assemble_turn
from src.core.config.app_config import AppConfig
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.runtime_logger import get_logger
from src.core.sandbox.command_policy import CommandPolicy
from src.core.sandbox.file_writer import FileWriter
from src.core.sandbox.tool_catalog import ToolCatalog
from src.core.sessions.knowledge_store import KnowledgeStore
from src.core.sessions.turn_knowledge_writer import store_turn_knowledge

log = get_logger("turn_pipeline")


class TurnPipeline:
    """Stateless-per-turn stage executor for one complete agent turn.

    Constructed fresh for each turn by ResponseLoop._make_pipeline(). All context
    is injected via constructor — no mutable state is held between turns.
    """

    def __init__(
        self,
        config: AppConfig,
        tool_catalog: ToolCatalog,
        tool_router: ToolRouter,
        activity: ActivityStream,
        *,
        command_policy: CommandPolicy | None = None,
        knowledge_store: KnowledgeStore | None = None,
        embed_fn=None,
        session_id_fn=None,
        docker_mode: bool = False,
        journal=None,
        file_writer: FileWriter | None = None,
        evidence_bag=None,
        vcs=None,
        active_project: str = "",
        project_meta=None,
        should_stop: Callable[[], bool] | None = None,
    ) -> None:
        self._config = config
        self._catalog = tool_catalog
        self._router = tool_router
        self._activity = activity
        self._command_policy = command_policy
        self._knowledge = knowledge_store
        self._embed_fn = embed_fn
        self._session_id_fn = session_id_fn
        self._docker_mode = docker_mode
        self._journal = journal
        self._file_writer = file_writer
        self._evidence_bag = evidence_bag
        self._vcs = vcs
        self._active_project = active_project
        self._project_meta = project_meta
        self._should_stop = should_stop or (lambda: False)

    # ── Public API ────────────────────────────────────────────────────────────

    def run(
        self,
        user_text: str,
        chat_history: list[dict[str, str]],
        on_token: Callable[[str], None] | None = None,
        on_complete: Callable[[dict[str, Any]], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_tool_start: Callable[[str], None] | None = None,
        on_tool_result: Callable[[dict], None] | None = None,
    ) -> None:
        """Execute the full turn stage pipeline synchronously.

        Called from a background thread by ResponseLoop. Must not be called
        from the main (UI) thread.
        """
        prompt_build = self.build_prompt(user_text=user_text)

        # ── Stage 1: Planner ──
        planner_result = None
        planner_text = ""
        planner_messages: list[dict[str, str]] = []
        try:
            planner_result = run_execution_planner(
                config=self._config,
                activity=self._activity,
                tool_catalog=self._catalog,
                user_text=user_text,
                sandbox_root=self._config.sandbox_root,
                active_project=self._active_project,
                should_stop=self._should_stop,
            )
        except Exception as exc:
            log.warning("Planner stage failed: %s", exc)
            self._activity.warn("planner", f"Planner stage failed: {exc}")
        if planner_result and planner_result.plan_text:
            planner_text = planner_result.plan_text
            planner_messages.append(
                {
                    "role": "system",
                    "content": (
                        "Planner guidance for this turn. Use it as internal execution guidance, "
                        "but still inspect reality before acting.\n\n"
                        f"{planner_text}"
                    ),
                }
            )

        # ── Stage 2: Context gathering (no model, direct calls) ──
        gathered = None
        if self._file_writer:
            try:
                gathered = gather_workspace_context(
                    file_writer=self._file_writer,
                    active_project=self._active_project,
                    project_meta=self._project_meta,
                    journal=self._journal,
                )
                if gathered:
                    self._activity.info(
                        "context",
                        f"Context gathered: {gathered.file_count} files, "
                        f"{len(gathered.key_file_snippets)} key files, "
                        f"{gathered.gathering_ms:.0f}ms"
                    )
            except Exception as exc:
                log.warning("Context gather stage failed: %s", exc)

        # ── Stage 3: Probe stage (FAST_PROBE model, text-in/text-out) ──
        probe_result = None
        try:
            probe_result = run_probe_stage(
                config=self._config,
                activity=self._activity,
                user_text=user_text,
                gathered=gathered,
            )
        except Exception as exc:
            log.warning("Probe stage failed: %s", exc)

        # ── Assemble stage context injection ──
        stage_ctx = StageContext(
            gathered=gathered,
            probes=probe_result,
            planner=planner_result,
        )
        stage_injection = format_stage_context(stage_ctx)
        stage_messages: list[dict[str, str]] = []
        if stage_injection:
            stage_messages.append({
                "role": "system",
                "content": (
                    "Pre-gathered workspace context for this turn. "
                    "Use this to orient yourself — do not re-discover "
                    "information that is already provided here.\n\n"
                    f"{stage_injection}"
                ),
            })

        # ── Turn assembly (STM window, evidence bag, budget guard) ──
        assembled = assemble_turn(
            config=self._config,
            activity=self._activity,
            chat_history=chat_history,
            user_text=user_text,
            system_prompt=prompt_build.prompt,
            planner_messages=planner_messages,
            stage_messages=stage_messages,
            planner_text=planner_text,
            evidence_bag=self._evidence_bag,
        )
        messages = assembled.messages

        # ── Guard: model must be configured before entering the loop ──
        _primary_model = resolve_model_for_role(self._config, PRIMARY_CHAT_ROLE)
        if not _primary_model:
            msg = (
                "No model selected. Open Settings (Ctrl+,) and choose a Primary Chat model, "
                "or select one from the model picker in the Session tab."
            )
            self._activity.warn("turn_pipeline", msg)
            if on_error:
                on_error(msg)
            return

        turn_outcome = run_tool_agent_turn(
            config=self._config,
            tool_router=self._router,
            activity=self._activity,
            user_text=user_text,
            messages=messages,
            on_token=on_token,
            on_tool_start=on_tool_start,
            on_tool_result=on_tool_result,
            should_stop=self._should_stop,
        )
        total_content = list(turn_outcome.total_content)
        result = turn_outcome.result
        assistant_text = turn_outcome.assistant_text
        rounds = turn_outcome.rounds

        # ── Evidence pass-2 (if model signals uncertainty) ──
        pass2 = run_evidence_pass(
            config=self._config,
            activity=self._activity,
            evidence_bag=self._evidence_bag,
            messages=messages,
            user_text=user_text,
            assistant_text=assistant_text,
            bag_summary=assembled.bag_summary,
            on_token=on_token,
            should_stop=self._should_stop,
        )
        if pass2:
            total_content.append(pass2["content"])
            assistant_text = pass2["text"]
            result = pass2["result"]

        # ── RAG: store user query and assistant response ──
        final_text = "\n".join(total_content)
        store_turn_knowledge(
            config=self._config,
            knowledge_store=self._knowledge,
            embed_fn=self._embed_fn,
            session_id_fn=self._session_id_fn,
            user_text=user_text,
            final_text=final_text,
            bag_summary=assembled.bag_summary,
        )

        # ── Final result ──
        meta = {
            "model": result.get("model", resolve_model_for_role(self._config, PRIMARY_CHAT_ROLE)),
            "tokens_in": f"~{result.get('prompt_eval_count', '?')}",
            "tokens_out": f"~{result.get('eval_count', '?')}",
            "time": f"{result.get('wall_ms', 0):.0f}ms",
            "rounds": rounds,
            "stopped": bool(result.get("stopped", False) or self._should_stop()),
            "planning_used": bool(planner_result),
            "planner_model": planner_result.model_name if planner_result else "",
            "planner_tokens_in": planner_result.tokens_in if planner_result else 0,
            "planner_tokens_out": planner_result.tokens_out if planner_result else 0,
            "planner_wall_ms": round(planner_result.wall_ms, 1) if planner_result else 0.0,
            "planner_excerpt": planner_text[:240] if planner_text else "",
            "loop_mode": TOOL_AGENT_LOOP,
            "context_gathered": gathered is not None and bool(gathered.file_tree),
            "context_gather_ms": round(gathered.gathering_ms, 1) if gathered else 0.0,
            "probes_run": len(probe_result.probes) if probe_result else 0,
            "probe_total_ms": round(probe_result.total_wall_ms, 1) if probe_result else 0.0,
            "stm_window_size": assembled.window_size,
            "stm_falloff_count": assembled.falloff_count,
            "evidence_bag_active": bool(assembled.bag_summary),
            "budget_total_before": assembled.budget_report.total_before_trim,
            "budget_total_after": assembled.budget_report.total_after_trim,
            "budget_available": assembled.budget_report.available_tokens,
            "budget_trimmed": assembled.budget_report.over_budget,
            "budget_multipass_recommended": assembled.budget_report.would_benefit_from_multipass,
            "recovery_triggered": turn_outcome.recovery_triggered,
        }

        if on_complete:
            on_complete(build_loop_result(
                user_text=user_text,
                content="\n".join(total_content),
                loop_id=TOOL_AGENT_LOOP,
                metadata=meta,
                prompt_build=prompt_build,
            ))

    def build_prompt(
        self,
        user_text: str = "",
        chat_history: list[dict[str, str]] | None = None,
    ) -> PromptBuildResult:
        """Build the exact prompt bundle for the next agent turn.

        Called both from run() (start of each turn) and from
        ResponseLoop.preview_prompt() for inspector display.
        """
        rag_context = build_rag_context(
            config=self._config,
            knowledge_store=self._knowledge,
            embed_fn=self._embed_fn,
            session_id_fn=self._session_id_fn,
            activity=self._activity,
            user_text=user_text,
        )
        journal_context = build_journal_context(self._journal)
        vcs_context = build_vcs_context(self._vcs)
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
            model_name=resolve_model_for_role(self._config, PRIMARY_CHAT_ROLE),
            rag_context=rag_context,
            docker_mode=self._docker_mode,
            journal_context=journal_context,
            vcs_context=vcs_context,
            active_project=self._active_project,
            project_brief=project_brief,
            project_meta_path=project_meta_path,
            self_awareness_enabled=getattr(self._config, "self_awareness_enabled", False),
        )

        for warning in prompt_build.warnings:
            log.warning("Prompt source warning: %s", warning)

        return prompt_build
