"""Simple direct-chat loop for lightweight conversational turns."""

from __future__ import annotations

import threading

from src.core.agent.loop_types import DIRECT_CHAT_LOOP, LoopRequest, build_loop_result
from src.core.agent.model_roles import PRIMARY_CHAT_ROLE, resolve_model_for_role
from src.core.config.app_config import AppConfig
from src.core.ollama.ollama_client import chat_stream
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.runtime_logger import get_logger

log = get_logger("direct_chat_loop")


class DirectChatLoop:
    loop_id = DIRECT_CHAT_LOOP

    def __init__(self, config: AppConfig, activity: ActivityStream):
        self._config = config
        self._activity = activity
        self._stop_requested = False
        self._worker_thread: threading.Thread | None = None

    def run(self, request: LoopRequest) -> None:
        def _worker():
            try:
                self._stop_requested = False
                self._run_sync(request)
            except Exception as exc:
                log.exception("Direct chat loop failed")
                if request.on_error:
                    request.on_error(str(exc))

        thread = threading.Thread(target=_worker, daemon=True, name="direct-chat-loop")
        self._worker_thread = thread
        thread.start()

    def _run_sync(self, request: LoopRequest) -> None:
        model = resolve_model_for_role(self._config, PRIMARY_CHAT_ROLE)
        if not model:
            if request.on_error:
                request.on_error("No model selected")
            return

        messages = list(request.chat_history)
        messages.append({"role": "user", "content": request.user_text})
        round_tokens: list[str] = []
        self._activity.model("loop", f"{self.loop_id}: requesting response from {model}")
        result = chat_stream(
            base_url=self._config.ollama_base_url,
            model=model,
            messages=messages,
            on_token=lambda t: (round_tokens.append(t), request.on_token(t) if request.on_token else None),
            should_stop=lambda: self._stop_requested,
            temperature=self._config.temperature,
            num_ctx=self._config.max_context_tokens,
        )
        content = result.get("content", "".join(round_tokens))
        payload = build_loop_result(
            user_text=request.user_text,
            content=content,
            loop_id=self.loop_id,
            metadata={
                "model": result.get("model", model),
                "tokens_in": f"~{result.get('prompt_eval_count', '?')}",
                "tokens_out": f"~{result.get('eval_count', '?')}",
                "time": f"{result.get('wall_ms', 0):.0f}ms",
                "rounds": 1,
                "stopped": bool(result.get("stopped", False) or self._stop_requested),
            },
        )
        if request.on_complete:
            request.on_complete(payload)

    def request_stop(self) -> None:
        self._stop_requested = True

    def join(self, timeout: float = 3.0) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)
