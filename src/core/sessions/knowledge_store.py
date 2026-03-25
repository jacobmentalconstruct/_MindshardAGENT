"""Knowledge store — session-scoped RAG with cosine similarity retrieval.

Stores text chunks with their embedding vectors in the same SQLite DB
as sessions. Retrieval uses brute-force cosine similarity over the
session's knowledge base (fast enough for <10k chunks per session).

Usage:
    from src.core.sessions.knowledge_store import KnowledgeStore
    ks = KnowledgeStore(db_path)
    ks.add_chunk(session_id, "some text", embedding_vec, source="assistant")
    results = ks.query(session_id, query_vec, top_k=5)
"""

import struct
import math
import sqlite3
from pathlib import Path
from typing import Any

from src.core.utils.ids import make_id
from src.core.utils.clock import utc_iso
from src.core.runtime.runtime_logger import get_logger

log = get_logger("knowledge_store")


def _vec_to_blob(vec: list[float]) -> bytes:
    """Pack a float vector into a compact binary blob (float32)."""
    return struct.pack(f"{len(vec)}f", *vec)


def _blob_to_vec(blob: bytes) -> list[float]:
    """Unpack a binary blob back into a float vector."""
    n = len(blob) // 4  # float32 = 4 bytes
    return list(struct.unpack(f"{n}f", blob))


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Returns 0.0 immediately on dimension mismatch — this happens when the
    embedding model changes mid-session and stored vectors have a different
    dimensionality than the query vector.  Silently comparing via zip() would
    truncate and produce a meaningless score; 0.0 correctly signals no match.
    """
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def chunk_text(text: str, max_chars: int = 512, overlap: int = 64) -> list[str]:
    """Split text into overlapping chunks for embedding.

    Splits on sentence boundaries when possible, falling back to
    word boundaries, then hard character limits.

    Args:
        text: Input text to chunk.
        max_chars: Maximum characters per chunk.
        overlap: Character overlap between consecutive chunks.

    Returns:
        List of text chunks.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars

        if end < len(text):
            # Try to break at sentence boundary
            segment = text[start:end]
            for sep in (". ", ".\n", "! ", "? ", "\n\n", "\n"):
                last = segment.rfind(sep)
                if last > max_chars // 3:
                    end = start + last + len(sep)
                    break
            else:
                # Fall back to word boundary
                space = segment.rfind(" ")
                if space > max_chars // 3:
                    end = start + space + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Advance with overlap
        start = end - overlap if end < len(text) else end

    return chunks


class KnowledgeStore:
    """Session-scoped knowledge base with vector retrieval."""

    def __init__(self, db_path: str | Path):
        """Initialize against the sessions database path.

        Args:
            db_path: SQLite DB path (schema must already include the knowledge table).
        """
        self._db_path = str(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def add_chunk(
        self,
        session_id: str,
        content: str,
        embedding: list[float],
        source: str = "",
        source_role: str = "",
    ) -> str:
        """Store a text chunk with its embedding vector.

        Args:
            session_id: Session this knowledge belongs to.
            content: The text content.
            embedding: The embedding vector (list of floats).
            source: Free-form source label (e.g. "user_msg", "tool_output").
            source_role: Role that generated this content ("user", "assistant", "tool").

        Returns:
            The chunk_id of the stored chunk.
        """
        chunk_id = make_id("knw")
        blob = _vec_to_blob(embedding)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO knowledge (chunk_id, session_id, content, embedding, "
                "source, source_role, dim, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (chunk_id, session_id, content, blob, source, source_role,
                 len(embedding), utc_iso()),
            )
            conn.commit()
        return chunk_id

    def add_text(
        self,
        session_id: str,
        text: str,
        embed_fn,
        source: str = "",
        source_role: str = "",
        max_chunk_chars: int = 512,
    ) -> list[str]:
        """Chunk text and store each chunk with its embedding.

        Args:
            session_id: Session this knowledge belongs to.
            text: Full text to chunk and embed.
            embed_fn: Callable(str) -> list[float] that produces embeddings.
            source: Source label.
            source_role: Role that generated the content.
            max_chunk_chars: Max chars per chunk.

        Returns:
            List of chunk_ids created.
        """
        chunks = chunk_text(text, max_chars=max_chunk_chars)
        if not chunks:
            return []

        ids = []
        for chunk in chunks:
            try:
                vec = embed_fn(chunk)
                cid = self.add_chunk(session_id, chunk, vec, source, source_role)
                ids.append(cid)
            except Exception as e:
                log.warning("Failed to embed chunk (%d chars): %s", len(chunk), e)

        log.info("Stored %d/%d chunks for session %s", len(ids), len(chunks), session_id)
        return ids

    def query(
        self,
        session_id: str,
        query_embedding: list[float],
        top_k: int = 5,
        min_score: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Retrieve the most relevant chunks for a query vector.

        Args:
            session_id: Session to search within.
            query_embedding: The query embedding vector.
            top_k: Maximum number of results.
            min_score: Minimum cosine similarity threshold.

        Returns:
            List of dicts with keys: chunk_id, content, source, source_role,
            score, created_at — sorted by descending score.
        """
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT chunk_id, content, embedding, source, source_role, created_at "
                "FROM knowledge WHERE session_id = ?",
                (session_id,),
            )

            scored = []
            for row in cur:
                chunk_id, content, blob, source, source_role, created_at = row
                stored_vec = _blob_to_vec(blob)
                score = _cosine_similarity(query_embedding, stored_vec)
                if score >= min_score:
                    scored.append({
                        "chunk_id": chunk_id,
                        "content": content,
                        "source": source,
                        "source_role": source_role,
                        "score": round(score, 4),
                        "created_at": created_at,
                    })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def count(self, session_id: str) -> int:
        """Count knowledge chunks in a session."""
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM knowledge WHERE session_id = ?", (session_id,))
            return cur.fetchone()[0]

    def delete_session_knowledge(self, session_id: str) -> int:
        """Delete all knowledge chunks for a session. Returns count deleted."""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM knowledge WHERE session_id = ?", (session_id,))
            conn.commit()
            return cur.rowcount

    def delete_by_source(self, session_id: str, source: str) -> int:
        """Delete all knowledge chunks for a session with a specific source label.

        Used to invalidate stale derived summaries (e.g. source='evidence_bag')
        before re-embedding updated content.  Returns count deleted.
        """
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM knowledge WHERE session_id = ? AND source = ?",
                (session_id, source),
            )
            conn.commit()
            return cur.rowcount

    def get_all_chunks(self, session_id: str) -> list[dict[str, Any]]:
        """Get all chunks for a session (without embeddings, for inspection)."""
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT chunk_id, content, source, source_role, dim, created_at "
                "FROM knowledge WHERE session_id = ? ORDER BY created_at",
                (session_id,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
