"""Central application configuration.

All runtime-relevant settings live here. No scattered magic constants.
Persisted as JSON in the project root.
"""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from src.core.runtime.runtime_logger import get_logger

log = get_logger("config")

_CONFIG_FILE = "app_config.json"


@dataclass
class AppConfig:
    """Canonical application configuration."""

    # Sandbox boundaries
    sandbox_root: str = ""
    toolbox_root: str = ""

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    selected_model: str = ""
    max_context_tokens: int = 8192       # constrain num_ctx to protect VRAM
    temperature: float = 0.7

    # Session
    current_session_id: str = ""
    auto_save_on_close: bool = True

    # UI
    window_width: int = 1400
    window_height: int = 900

    # Resource polling
    resource_poll_interval_ms: int = 5000

    # RAG / Embeddings
    embedding_model: str = "all-minilm:latest"
    rag_enabled: bool = True
    rag_top_k: int = 5
    rag_min_score: float = 0.3
    rag_chunk_max_chars: int = 512

    # Logging
    log_dir: str = "_logs"

    def save(self, project_root: Path) -> None:
        path = project_root / _CONFIG_FILE
        try:
            path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
            log.info("Config saved to %s", path)
        except Exception:
            log.exception("Failed to save config")

    @classmethod
    def load(cls, project_root: Path) -> "AppConfig":
        path = project_root / _CONFIG_FILE
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                log.info("Config loaded from %s", path)
                return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            except Exception:
                log.exception("Failed to load config, using defaults")
        return cls()
