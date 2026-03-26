"""Review/judge execution loop.

Runs the full tool-agent to generate an initial response, then passes
the result through the review model for a second-pass critique and
improvement. The combined output is returned to the user.

Selected when user text signals review/critique intent (e.g. "review this",
"is this correct", "fact-check this"), or via mode_hint="review_judge".
"""

from __future__ import annotations

from src.core.agent.loop_types import (
    LoopRequest,
    LoopRunner,
    REVIEW_JUDGE_LOOP,
    patch_loop_result,
)
from src.core.agent.model_roles import REVIEW_ROLE, resolve_model_for_role
from src.core.config.app_config import AppConfig
from src.core.ollama.ollama_client import chat_stream
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.runtime_logger import get_logger

log = get_logger("review_judge_loop")

_REVIEW_PROMPT_TEMPLATE = (
    "You are a review judge. An AI agent has produced the following response to a user request.\n"
    "Your job is to:\n"
    "1. Identify any factual errors, logical flaws, or missing information.\n"
    "2. Note whether the response actually answers the user's question.\n"
    "3. Suggest concrete improvements (be specific, not vague).\n"
    "4. If the response is good, say so and explain what makes it strong.\n\n"
    "USER QUESTION:\n{user_text}\n\n"
    "AGENT RESPONSE:\n{agent_response}\n\n"
    "REVIEW:"
)


class ReviewJudgeLoop:
    """Runs tool-agent then passes result through review model.

    Phase 1: Delegates to the tool_agent (ResponseLoop) for full execution.
    Phase 2: Runs the review model on the combined output.
    Phase 3: Appends the review as a separate section in the final response.
    """

    loop_id = REVIEW_JUDGE_LOOP

    def __init__(
        self,
        config: AppConfig,
        activity: ActivityStream,
        tool_agent_loop: LoopRunner,
    ) -> None:
        self._config = config
        self._activity = activity
        self._tool_agent = tool_agent_loop
        self._stop_requested = False

    def run(self, request: LoopRequest) -> None:
        self._stop_requested = False
        self._activity.info("loop", "Review-judge loop selected — will critique agent output")

        # Intercept on_complete to run the judge pass after the agent responds
        def _on_agent_complete(result: dict) -> None:
            if self._stop_requested:
                if request.on_complete:
                    request.on_complete(
                        patch_loop_result(
                            result,
                            loop_id=self.loop_id,
                            metadata_updates={"review_generated": False, "stopped": True},
                        )
                    )
                return

            agent_content = result.get("content", "")
            review = self._run_review(request.user_text, agent_content)

            if review:
                combined = f"{agent_content}\n\n---\n**Review:**\n{review}"
            else:
                combined = agent_content

            final_result = patch_loop_result(
                result,
                loop_id=self.loop_id,
                user_text=request.user_text,
                content=combined,
                metadata_updates={"review_generated": bool(review)},
            )

            if request.on_complete:
                request.on_complete(final_result)

        review_request = LoopRequest(
            user_text=request.user_text,
            chat_history=request.chat_history,
            on_token=request.on_token,
            on_complete=_on_agent_complete,
            on_error=request.on_error,
            on_tool_start=request.on_tool_start,
            on_tool_result=request.on_tool_result,
            mode_hint=None,
        )

        self._tool_agent.run(review_request)

    def _run_review(self, user_text: str, agent_response: str) -> str:
        """Call the review model on the agent's output. Returns review text or empty string."""
        model = resolve_model_for_role(self._config, REVIEW_ROLE)
        if not model:
            log.warning("No review model configured; skipping review pass")
            return ""

        review_prompt = _REVIEW_PROMPT_TEMPLATE.format(
            user_text=user_text[:600],
            agent_response=agent_response[:2000],
        )
        messages = [{"role": "user", "content": review_prompt}]
        self._activity.info("loop", f"Review judge: running review pass with {model}")

        try:
            result = chat_stream(
                base_url=self._config.ollama_base_url,
                model=model,
                messages=messages,
                temperature=0.3,
                num_ctx=min(getattr(self._config, "max_context_tokens", 4096), 4096),
                should_stop=lambda: self._stop_requested,
            )
            return result.get("content", "").strip()
        except Exception as exc:
            log.warning("Review pass failed: %s", exc)
            self._activity.warn("loop", f"Review pass failed: {exc}")
            return ""

    def request_stop(self) -> None:
        self._stop_requested = True
        self._tool_agent.request_stop()

    def join(self, timeout: float = 3.0) -> None:
        if hasattr(self._tool_agent, "join"):
            self._tool_agent.join(timeout=timeout)
