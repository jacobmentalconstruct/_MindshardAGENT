"""Prompt-context gatherers for tool-agent turns."""

from __future__ import annotations

from typing import Callable

from src.core.config.app_config import AppConfig
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.runtime_logger import get_logger
from src.core.sessions.knowledge_store import KnowledgeStore

log = get_logger("turn_prompt_context")


def build_rag_context(
    *,
    config: AppConfig,
    knowledge_store: KnowledgeStore | None,
    embed_fn: Callable[[str], list[float]] | None,
    session_id_fn: Callable[[], str] | None,
    activity: ActivityStream,
    user_text: str,
) -> str:
    rag_context = ""
    if not (config.rag_enabled and knowledge_store and embed_fn and session_id_fn):
        return rag_context
    try:
        sid = session_id_fn()
        if sid and knowledge_store.count(sid) > 0:
            query_vec = embed_fn(user_text)
            hits = knowledge_store.query(
                sid,
                query_vec,
                top_k=config.rag_top_k,
                min_score=config.rag_min_score,
            )
            if hits:
                rag_context = "\n---\n".join(
                    f"[{h['source_role']}/{h['source']}] {h['content']}"
                    for h in hits
                )
                activity.info("rag", f"Retrieved {len(hits)} chunks (best={hits[0]['score']:.3f})")
    except Exception as exc:
        log.warning("RAG retrieval failed: %s", exc)
    return rag_context


def build_journal_context(journal) -> str:
    if not journal:
        return ""
    try:
        return journal.summary_since(10)
    except Exception:
        return ""


def build_vcs_context(vcs) -> str:
    if not (vcs and vcs.is_attached):
        return ""
    try:
        return vcs.onboarding_context(limit=5)
    except Exception:
        return ""
