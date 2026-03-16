"""Discover locally available Ollama models.

Calls the Ollama REST API to list installed models.
"""

import json
import urllib.request
import urllib.error

from src.core.runtime.runtime_logger import get_logger

log = get_logger("model_scanner")


def scan_models(base_url: str = "http://localhost:11434") -> list[str]:
    """Return sorted list of locally available Ollama model names."""
    url = f"{base_url}/api/tags"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = sorted(m["name"] for m in data.get("models", []))
        log.info("Scanned %d model(s) from %s", len(models), base_url)
        return models
    except urllib.error.URLError as e:
        log.error("Failed to reach Ollama at %s: %s", base_url, e)
        raise
    except Exception:
        log.exception("Unexpected error scanning models")
        raise
