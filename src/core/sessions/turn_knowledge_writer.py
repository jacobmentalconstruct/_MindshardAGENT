"""Turn-level knowledge-store persistence helpers."""

from __future__ import annotations

from typing import Callable

from src.core.config.app_config import AppConfig
from src.core.runtime.runtime_logger import get_logger
from src.core.sessions.knowledge_store import KnowledgeStore

log = get_logger("turn_knowledge_writer")


def store_turn_knowledge(
    *,
    config: AppConfig,
    knowledge_store: KnowledgeStore | None,
    embed_fn: Callable[[str], list[float]] | None,
    session_id_fn: Callable[[], str] | None,
    user_text: str,
    final_text: str,
    bag_summary: str = "",
) -> None:
    """Persist the turn plus the latest evidence bag summary into RAG storage."""
    if not (config.rag_enabled and knowledge_store and embed_fn and session_id_fn):
        return
    sid = session_id_fn()
    if not sid:
        return
    try:
        if bag_summary:
            deleted = knowledge_store.delete_by_source(sid, "evidence_bag")
            if deleted:
                log.debug("Invalidated %d stale evidence_bag RAG chunk(s)", deleted)
            knowledge_store.add_text(
                sid,
                bag_summary,
                embed_fn,
                source="evidence_bag",
                source_role="system",
                max_chunk_chars=config.rag_chunk_max_chars,
            )

        if len(final_text.strip()) > 20:
            knowledge_store.add_text(
                sid,
                final_text,
                embed_fn,
                source="chat",
                source_role="assistant",
                max_chunk_chars=config.rag_chunk_max_chars,
            )
        if len(user_text.strip()) > 20:
            knowledge_store.add_text(
                sid,
                user_text,
                embed_fn,
                source="chat",
                source_role="user",
                max_chunk_chars=config.rag_chunk_max_chars,
            )
    except Exception as exc:
        log.warning("RAG storage failed: %s", exc)
