"""Ollama HTTP client for chat completions with streaming.

Uses only stdlib (urllib + json) to avoid external dependencies.
Streams response tokens via a callback.
"""

import json
import urllib.request
import urllib.error
from typing import Any, Callable

from src.core.runtime.runtime_logger import get_logger
from src.core.utils.clock import Stopwatch

log = get_logger("ollama_client")


def chat_stream(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    on_token: Callable[[str], None] | None = None,
    on_done: Callable[[dict[str, Any]], None] | None = None,
    temperature: float = 0.7,
    num_ctx: int = 8192,
    timeout: int = 120,
) -> dict[str, Any]:
    """Send a chat request to Ollama and stream the response.

    Args:
        base_url: Ollama API base (e.g. http://localhost:11434)
        model: Model name
        messages: Chat message list [{"role": "...", "content": "..."}]
        on_token: Called with each text fragment as it streams
        on_done: Called with the final aggregated result
        temperature: Sampling temperature
        timeout: Request timeout in seconds

    Returns:
        Dict with keys: content, model, total_duration_ms, eval_count,
        prompt_eval_count, done_reason
    """
    url = f"{base_url}/api/chat"
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {"temperature": temperature, "num_ctx": num_ctx},
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, method="POST",
                                 headers={"Content-Type": "application/json"})

    sw = Stopwatch()
    full_content = []
    final_meta: dict[str, Any] = {}

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                chunk = json.loads(line)

                # Stream token
                token = chunk.get("message", {}).get("content", "")
                if token and on_token:
                    on_token(token)
                full_content.append(token)

                # Final chunk
                if chunk.get("done"):
                    final_meta = {
                        "content": "".join(full_content),
                        "model": chunk.get("model", model),
                        "total_duration_ms": chunk.get("total_duration", 0) / 1_000_000,
                        "eval_count": chunk.get("eval_count", 0),
                        "prompt_eval_count": chunk.get("prompt_eval_count", 0),
                        "done_reason": chunk.get("done_reason", ""),
                    }

    except urllib.error.URLError as e:
        log.error("Ollama request failed: %s", e)
        raise
    except Exception:
        log.exception("Unexpected error during chat stream")
        raise

    elapsed = sw.elapsed_ms()
    final_meta.setdefault("content", "".join(full_content))
    final_meta.setdefault("model", model)
    final_meta["wall_ms"] = round(elapsed, 1)

    log.info("Chat complete: model=%s, tokens_out=%s, wall=%.0fms",
             model, final_meta.get("eval_count", "?"), elapsed)

    if on_done:
        on_done(final_meta)

    return final_meta
