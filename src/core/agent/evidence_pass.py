"""Evidence pass — two-pass retrieval when the model needs more context.

After the main streaming loop completes, this module checks if the model's
response signals uncertainty about prior context. If so, it retrieves deeper
evidence from the bag and re-runs inference once (never recursive).

WARNING: The evidence bag is NOT a replacement for the sliding window (STM)
or knowledge store (RAG). It is a retrieval supplement only. Without temporal
flow from the STM window, models produce factually-referenced but causally
disconnected output: snippets, not scripts. Always pair with STM.
"""

from __future__ import annotations

from typing import Any, Callable

from src.core.agent.model_roles import PRIMARY_CHAT_ROLE, resolve_model_for_role
from src.core.agent.transcript_formatter import compact_tool_call_transcript
from src.core.config.app_config import AppConfig
from src.core.ollama.ollama_client import chat_stream
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.runtime_logger import get_logger

log = get_logger("evidence_pass")

# Heuristic markers that the model needs more context.
# Deliberately loose — tighten later with probe-model classification if needed.
_UNCERTAINTY_MARKERS = [
    "i don't have", "i'm not sure", "earlier in our conversation",
    "previously", "as mentioned before", "i don't recall",
    "let me check", "i would need to", "i can't recall",
    "from what i remember", "if i recall",
]


def needs_evidence_dive(
    assistant_text: str,
    bag_summary: str,
) -> bool:
    """Does the model's response suggest it needs more context from the bag?"""
    if not bag_summary:
        return False
    lower = assistant_text.lower()
    return any(marker in lower for marker in _UNCERTAINTY_MARKERS)


def run_evidence_pass(
    *,
    config: AppConfig,
    activity: ActivityStream,
    evidence_bag,
    messages: list[dict[str, str]],
    user_text: str,
    assistant_text: str,
    bag_summary: str,
    on_token: Callable[[str], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, Any] | None:
    """Run pass-2 evidence retrieval if the model signals uncertainty.

    Returns a dict with 'content' and 'result' keys if pass-2 ran,
    or None if it wasn't needed or failed.
    """
    if not (
        evidence_bag
        and config.evidence_bag_enabled
        and bag_summary
        and needs_evidence_dive(assistant_text, bag_summary)
    ):
        return None

    if should_stop and should_stop():
        return None

    activity.info("evidence", "Pass-2: retrieving deeper evidence from bag")
    try:
        deep_evidence = evidence_bag.retrieve(
            user_text,
            token_budget=config.evidence_bag_retrieval_budget,
        )
        if not deep_evidence:
            return None

        # Re-run with deeper evidence injected
        pass2_messages = list(messages)
        pass2_messages.append({"role": "assistant", "content": assistant_text})
        pass2_messages.append({
            "role": "user",
            "content": (
                "[Evidence Retrieved]\n"
                "Here is more specific evidence from earlier in our conversation. "
                "Please revise your response using this context:\n\n"
                f"{deep_evidence}"
            ),
        })

        pass2_tokens: list[str] = []
        if on_token:
            on_token("\n\n---\n*[Revising with deeper evidence...]*\n\n")

        pass2_result = chat_stream(
            base_url=config.ollama_base_url,
            model=resolve_model_for_role(config, PRIMARY_CHAT_ROLE),
            messages=pass2_messages,
            on_token=lambda t: (pass2_tokens.append(t), on_token(t) if on_token else None),
            should_stop=should_stop or (lambda: False),
            temperature=config.temperature,
            num_ctx=config.max_context_tokens,
        )

        pass2_text = pass2_result.get("content", "".join(pass2_tokens))
        activity.info("evidence", "Pass-2 complete")

        return {
            "content": compact_tool_call_transcript(pass2_text),
            "result": pass2_result,
            "text": pass2_text,
        }
    except Exception as exc:
        log.warning("Evidence pass-2 failed: %s", exc)
        return None
