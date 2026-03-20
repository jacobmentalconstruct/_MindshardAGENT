"""Ollama embedding client — calls /api/embeddings for vector generation.

Primary embedder uses all-minilm (384-dim, 22MB).
Stdlib only (urllib + json), consistent with ollama_client.py.
"""

import json
import urllib.request
import urllib.error
from typing import Any

from src.core.runtime.runtime_logger import get_logger

log = get_logger("embedding_client")


def embed_text(
    text: str,
    base_url: str = "http://localhost:11434",
    model: str = "all-minilm:latest",
    timeout: int = 30,
) -> list[float]:
    """Generate an embedding vector for a single text string.

    Args:
        text: The text to embed.
        base_url: Ollama API base URL.
        model: Embedding model name.
        timeout: Request timeout in seconds.

    Returns:
        List of floats (embedding vector).

    Raises:
        RuntimeError: If the embedding request fails.
    """
    url = f"{base_url}/api/embeddings"
    payload = json.dumps({"model": model, "prompt": text}).encode("utf-8")

    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            embedding = data.get("embedding", [])
            if not embedding:
                raise RuntimeError(f"Empty embedding returned for model {model}")
            return embedding
    except urllib.error.URLError as e:
        log.error("Embedding request failed: %s", e)
        raise RuntimeError(f"Ollama embedding failed: {e}") from e


def embed_batch(
    texts: list[str],
    base_url: str = "http://localhost:11434",
    model: str = "all-minilm:latest",
    timeout: int = 60,
) -> list[list[float]]:
    """Embed multiple texts sequentially.

    Args:
        texts: List of strings to embed.
        base_url: Ollama API base URL.
        model: Embedding model name.
        timeout: Per-request timeout.

    Returns:
        List of embedding vectors (same order as input).
    """
    results = []
    for text in texts:
        vec = embed_text(text, base_url=base_url, model=model, timeout=timeout)
        results.append(vec)
    return results


def check_embedding_model(
    base_url: str = "http://localhost:11434",
    model: str = "all-minilm:latest",
    timeout: int = 10,
) -> dict[str, Any]:
    """Check if an embedding model is available and return its info.

    Returns:
        Dict with keys: available (bool), model (str), dim (int or None).
    """
    try:
        vec = embed_text("test", base_url=base_url, model=model, timeout=timeout)
        return {"available": True, "model": model, "dim": len(vec)}
    except Exception as e:
        log.warning("Embedding model %s not available: %s", model, e)
        return {"available": False, "model": model, "dim": None}
