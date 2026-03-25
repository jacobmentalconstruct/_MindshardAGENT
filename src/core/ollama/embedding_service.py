"""Embedding service — manages availability and text embedding via Ollama.

Owns: embedding model availability check, embed-text callable, activity logging.
Engine holds an instance; callers pass `service.embed` as the embed_fn callback
and call `service.check()` on startup to determine readiness.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.agent.model_roles import EMBEDDING_ROLE, resolve_model_for_role
from src.core.ollama.embedding_client import check_embedding_model, embed_text

if TYPE_CHECKING:
    from src.core.config.app_config import AppConfig
    from src.core.runtime.activity_stream import ActivityStream


class EmbeddingService:
    """Encapsulates embedding model availability and the embed-text operation.

    Owns: "is embedding available?" and "how do I embed text?"
    Engine must not resolve embedding model names or call embed_text directly.
    """

    def __init__(self, config: "AppConfig", activity: "ActivityStream") -> None:
        self._config = config
        self._activity = activity
        self._available = False

    def check(self) -> bool:
        """Check whether the configured embedding model is reachable.

        Updates internal availability state and logs to the activity stream.
        Returns True if the model is ready, False otherwise.
        """
        info = check_embedding_model(
            base_url=self._config.ollama_base_url,
            model=resolve_model_for_role(self._config, EMBEDDING_ROLE),
        )
        self._available = info["available"]
        if info["available"]:
            self._activity.info(
                "rag",
                f"Embedding model ready: {info['model']} ({info['dim']}-dim)",
            )
        else:
            self._activity.warn(
                "rag",
                f"Embedding model {resolve_model_for_role(self._config, EMBEDDING_ROLE)}"
                " not available — RAG disabled",
            )
        return self._available

    @property
    def is_available(self) -> bool:
        """True if the last check() call found the embedding model reachable."""
        return self._available

    def embed(self, text: str) -> list[float]:
        """Embed text using the configured Ollama embedding model."""
        return embed_text(
            text,
            base_url=self._config.ollama_base_url,
            model=resolve_model_for_role(self._config, EMBEDDING_ROLE),
        )

    def get_fn(self):
        """Return the embed callable if available, else None.

        Pass the result directly as the embed_fn parameter wherever it's needed.
        """
        return self.embed if self._available else None
