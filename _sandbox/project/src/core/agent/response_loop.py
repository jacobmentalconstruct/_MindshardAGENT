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

from src.core.agent.prompt_builder import build_system_prompt, build_messages
from src.core.agent.tool_router import ToolRouter
from src.core.agent.transcript_formatter import format_all_results
from src.core.ollama.ollama_client import chat_stream
from src.core.sandbox.tool_catalog import ToolCatalog
from src.core.sandbox.command_policy import CommandPolicy
from src.core.config.app_config import AppConfig
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.runtime_logger import get_logger

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
    ):
        self._config = config
        self._command_policy = command_policy
        self._catalog = tool_catalog
        self._router = tool_router
        self._activity = activity

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
        # Build system prompt
        system = build_system_prompt(
            sandbox_root=self._config.sandbox_root,
            tools=self._catalog,
            command_policy=self._command_policy,
            session_title="",
            model_name=self._config.selected_model,
        )

        # Add user message
        history = list(chat_history)
        history.append({"role": "user", "content": user_text})
        messages = build_messages(system, history)

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
                "history_addition": [
                    {"role": "user", "content": user_text},
                    {"role": "assistant", "content": "\n".join(total_content)},
                ],
            })
