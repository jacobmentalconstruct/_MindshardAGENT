"""Thin adapter bridging the manifold evidence bag into MindshardAGENT.

WARNING: The evidence bag is NOT a replacement for the sliding window (STM) or
knowledge store (RAG). It is a retrieval supplement only. Without temporal flow
from the STM window, models produce factually-referenced but causally disconnected
output: snippets, not scripts. Always pair with STM. Never use bag-only context.

The bag holds full text of every turn that falls off the sliding window. Assembly
returns a gravity-scored slice — the originals are never destroyed. Change the
query or raise the budget and different evidence surfaces.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from src.core.runtime.runtime_logger import get_logger

log = get_logger("evidence_adapter")

# Lazy-loaded reference to the SDK class
_EvidencePackage = None


def _ensure_sdk():
    """Lazy-import the manifold SDK so we only touch sys.path when actually used."""
    global _EvidencePackage
    if _EvidencePackage is not None:
        return

    sdk_root = Path(__file__).resolve().parents[3] / ".dev-tools" / "drop-bin" / "_manifold-mcp"
    if not sdk_root.exists():
        raise ImportError(f"Manifold SDK not found at {sdk_root}")

    if str(sdk_root) not in sys.path:
        sys.path.insert(0, str(sdk_root))

    from sdk.evidence_package import EvidencePackage as _EP
    _EvidencePackage = _EP
    log.info("Manifold SDK loaded from %s", sdk_root)


class EvidenceBagAdapter:
    """Wraps EvidencePackage for use by the response loop.

    Responsibilities:
    - Ingest turns that fall off the STM sliding window
    - Generate compact bag summaries for prompt injection
    - Deep-retrieve specific evidence for two-pass re-generation
    """

    def __init__(self, session_dir: Path, corpus_id: str = "evidence"):
        _ensure_sdk()
        db_path = session_dir / f"{corpus_id}.db"
        self._pkg = _EvidencePackage(db_path=db_path)
        self._ingested_ids: set[str] = set()
        log.info("Evidence bag adapter initialized: %s", db_path)

    # ── Ingest ────────────────────────────────────────────────────

    def ingest_falloff(self, turns: list[dict[str, str]]) -> int:
        """Ingest turns that fell off the STM window into the evidence bag.

        Each turn is a dict with 'role' and 'content' keys.
        Skips turns that have already been ingested (dedup by content hash).
        Returns count of newly ingested turns.
        """
        count = 0
        for i, turn in enumerate(turns):
            content = turn.get("content", "").strip()
            if not content:
                continue
            role = turn.get("role", "unknown")
            turn_id = f"falloff_{i}_{hash(content) & 0xFFFFFFFF:08x}"

            if turn_id in self._ingested_ids:
                continue

            doc_id = self._pkg.ingest_turn(
                content,
                source="stm_falloff",
                source_role=role,
                turn_id=turn_id,
            )
            if doc_id:
                self._ingested_ids.add(turn_id)
                count += 1

        if count:
            log.info("Ingested %d falloff turns into evidence bag", count)
        return count

    # ── Goal ──────────────────────────────────────────────────────

    def set_goal(self, goal: str) -> None:
        """Set the current goal for gravity scoring.

        Call when the planner fires, not every turn.
        """
        self._pkg.set_goal(goal)

    # ── Summary (compact, always in prompt) ───────────────────────

    def build_summary(self, query: str, token_budget: int = 128) -> str:
        """Return a compact summary of bag contents for prompt injection.

        This goes into the prompt every turn. Keep it small.
        Returns empty string if bag is empty.
        """
        result = self._pkg.window(query, token_budget=token_budget)
        if not result["text"]:
            return ""

        summary = result["summary"]
        header = (
            f"[Evidence Bag: {summary['span_count']} spans, "
            f"{summary['node_count']} nodes, "
            f"{summary['char_count']} chars]"
        )
        return f"{header}\n{result['text']}"

    # ── Deep retrieval (pass-2 only) ──────────────────────────────

    def retrieve(self, query: str, token_budget: int = 512) -> str:
        """Retrieve specific evidence for pass-2 re-generation.

        Only called when the first pass signals it needs more context.
        Returns fuller evidence text from the bag.
        """
        result = self._pkg.window(query, token_budget=token_budget)
        return result["text"]

    # ── Lifecycle ─────────────────────────────────────────────────

    def close(self) -> None:
        """Persist state and release resources."""
        try:
            self._pkg.close()
            log.info("Evidence bag adapter closed")
        except Exception:
            log.exception("Error closing evidence bag adapter")
