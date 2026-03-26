"""Ollama HTTP client for chat completions with streaming.

Uses only stdlib (urllib + json) to avoid external dependencies.
Streams response tokens via a callback.
"""

import json
import socket
import time
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
    should_stop: Callable[[], bool] | None = None,
    temperature: float = 0.7,
    num_ctx: int = 8192,
    timeout: int = 300,
    read_idle_timeout: float = 5.0,
    heartbeat_sec: float = 10.0,
    first_token_warn_sec: float = 20.0,
    max_output_chars: int | None = None,
    progress_label: str = "",
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
    content_chars = 0
    first_token_ms: float | None = None
    last_heartbeat_at = time.monotonic()
    label = progress_label or model

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            _configure_stream_timeout(resp, read_idle_timeout)
            while True:
                if should_stop and should_stop():
                    final_meta = {
                        "content": "".join(full_content),
                        "model": model,
                        "done_reason": "stopped",
                        "stopped": True,
                    }
                    break
                try:
                    raw_line = resp.readline()
                except socket.timeout:
                    elapsed = sw.elapsed_ms()
                    if should_stop and should_stop():
                        final_meta = {
                            "content": "".join(full_content),
                            "model": model,
                            "done_reason": "stopped",
                            "stopped": True,
                        }
                        break
                    if timeout and elapsed >= float(timeout) * 1000.0:
                        final_meta = {
                            "content": "".join(full_content),
                            "model": model,
                            "done_reason": "timeout",
                            "stopped": True,
                            "timed_out": True,
                        }
                        log.warning("Chat timeout: %s exceeded %ss", label, timeout)
                        break
                    now = time.monotonic()
                    if heartbeat_sec and (now - last_heartbeat_at) >= heartbeat_sec:
                        log.info(
                            "Chat heartbeat: %s still running, elapsed=%.0fms, chars=%d",
                            label,
                            elapsed,
                            content_chars,
                        )
                        last_heartbeat_at = now
                    continue
                if not raw_line:
                    break
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                chunk = json.loads(line)

                # Stream token
                token = chunk.get("message", {}).get("content", "")
                if token and on_token:
                    on_token(token)
                full_content.append(token)
                if token:
                    content_chars += len(token)
                    if first_token_ms is None:
                        first_token_ms = round(sw.elapsed_ms(), 1)
                        if first_token_warn_sec and first_token_ms >= first_token_warn_sec * 1000.0:
                            log.warning("First token latency high: %s took %.0fms", label, first_token_ms)
                        else:
                            log.info("First token: %s in %.0fms", label, first_token_ms)
                    if max_output_chars and content_chars >= max_output_chars:
                        final_meta = {
                            "content": "".join(full_content),
                            "model": model,
                            "done_reason": "output_cap",
                            "stopped": True,
                            "output_capped": True,
                        }
                        log.warning("Chat output capped: %s reached %d chars", label, max_output_chars)
                        break

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
    final_meta.setdefault("stopped", False)
    if first_token_ms is not None:
        final_meta.setdefault("first_token_ms", first_token_ms)
    final_meta["wall_ms"] = round(elapsed, 1)

    log.info("Chat complete: model=%s, tokens_out=%s, wall=%.0fms",
             model, final_meta.get("eval_count", "?"), elapsed)

    if on_done:
        on_done(final_meta)

    return final_meta


def _configure_stream_timeout(resp: Any, timeout: float) -> None:
    """Best-effort socket read timeout for streamed responses."""
    if timeout <= 0:
        return
    try:
        sock = resp.fp.raw._sock  # type: ignore[attr-defined]
    except Exception:
        sock = None
    if sock is not None:
        try:
            sock.settimeout(timeout)
        except Exception:
            pass
