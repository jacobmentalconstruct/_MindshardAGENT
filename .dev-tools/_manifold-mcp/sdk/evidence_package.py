"""
FILE: evidence_package.py
ROLE: Thin agent-facing SDK adapter for reversible evidence bags.
WHAT IT DOES: Provides a small in-process API over the manifold store so any agent can ingest text, set a goal, open an evidence window, and reconstruct exact supporting text.
HOW TO USE:
  - Add `_manifold-mcp` to `sys.path`
  - Import: `from sdk.evidence_package import EvidencePackage`
  - Create: `pkg = EvidencePackage(db_path=session_dir / "evidence.db")`
  - Use: `pkg.ingest_turn(...)`, `pkg.set_goal(...)`, `pkg.window(...)`, `pkg.close()`
NOTES:
  - `db_path` is the session anchor path for portability, but the current implementation stores reversible corpus and bag artifacts as JSON files alongside it.
  - This adapter is intentionally app-agnostic and safe to vendor into any agent environment that can access `.dev-tools/_manifold-mcp`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lib.manifold_store import (
    bag_path,
    build_corpus_bundle,
    build_evidence_bag,
    corpus_bundle_path,
    deterministic_id,
    load_bag,
    load_corpus_bundle,
    reconstruct_text_from_bag,
    save_bag,
    save_corpus_bundle,
)


class EvidencePackage:
    """Small app-agnostic adapter around the reversible manifold store."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_root = self.db_path.parent
        self.corpus_id = self.db_path.stem
        self.state_path = self.store_root / f"{self.corpus_id}_state.json"
        self.goal = ""
        self._load_state()
        self._ensure_corpus()

    def close(self) -> None:
        self._save_state()

    def set_goal(self, goal: str) -> None:
        self.goal = (goal or "").strip()
        self._save_state()

    def ingest_turn(
        self,
        text: str,
        *,
        source: str = "chat",
        source_role: str = "assistant",
        turn_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        content = (text or "").strip()
        if not content:
            return None

        document = {
            "document_id": deterministic_id(
                "turn",
                f"{source_role}:{source}:{turn_id}:{len(content)}:{content[:120]}",
            ),
            "title": f"{source_role}:{source}",
            "source_type": "session_turn",
            "source_path": "",
            "metadata": dict(metadata or {}),
            "text": content,
        }

        incoming = build_corpus_bundle(self.corpus_id, [document])
        existing = self._load_corpus()
        existing["documents"].extend(incoming["documents"])
        existing["evidence_spans"].extend(incoming["evidence_spans"])
        existing["nodes"].extend(incoming["nodes"])
        existing["hyperedges"].extend(incoming["hyperedges"])
        self._normalize_corpus(existing)
        save_corpus_bundle(self.store_root, existing)
        return document["document_id"]

    def window(self, query: str, token_budget: int = 512) -> dict[str, Any]:
        corpus = self._load_corpus()
        if not corpus.get("evidence_spans"):
            return {
                "query": query,
                "goal": self.goal,
                "bag_id": "",
                "bag_file": "",
                "text": "",
                "summary": {"span_count": 0, "char_count": 0, "node_count": 0},
                "selected_nodes": [],
                "evidence_spans": [],
            }

        effective_query = self._effective_query(query)
        top_n = max(6, min(24, max(1, token_budget // 64)))
        bag = build_evidence_bag(corpus, effective_query, top_n=top_n)
        trimmed_bag = self._trim_bag_to_budget(bag, token_budget)
        bag_file = save_bag(self.store_root, self.corpus_id, trimmed_bag)
        reconstruction = reconstruct_text_from_bag(trimmed_bag, mode="grouped")
        return {
            "query": query,
            "goal": self.goal,
            "bag_id": trimmed_bag["bag_id"],
            "bag_file": str(bag_file),
            "text": reconstruction["text"],
            "summary": {
                "span_count": reconstruction["span_count"],
                "char_count": len(reconstruction["text"]),
                "node_count": len(trimmed_bag["selected_nodes"]),
            },
            "selected_nodes": trimmed_bag["selected_nodes"],
            "evidence_spans": trimmed_bag["evidence_spans"],
        }

    def reconstruct(
        self,
        *,
        bag_id: str | None = None,
        bag_file: str | Path | None = None,
        mode: str = "grouped",
    ) -> dict[str, Any]:
        bag = load_bag(self.store_root, self.corpus_id, bag_id=bag_id, bag_file=bag_file)
        return reconstruct_text_from_bag(bag, mode=mode)

    def latest_bag_path(self, bag_id: str) -> Path:
        return bag_path(self.store_root, self.corpus_id, bag_id)

    def corpus_path(self) -> Path:
        return corpus_bundle_path(self.store_root, self.corpus_id)

    def _effective_query(self, query: str) -> str:
        query_text = (query or "").strip()
        if self.goal:
            return f"{self.goal}\n{query_text}".strip()
        return query_text

    def _trim_bag_to_budget(self, bag: dict[str, Any], token_budget: int) -> dict[str, Any]:
        char_budget = max(400, token_budget * 4)
        kept_spans = []
        char_count = 0
        for span in bag.get("evidence_spans", []):
            span_text = span.get("text", "")
            if kept_spans and char_count + len(span_text) > char_budget:
                break
            kept_spans.append(span)
            char_count += len(span_text)

        if not kept_spans:
            kept_spans = list(bag.get("evidence_spans", [])[:1])

        kept_span_ids = {span["evidence_span_id"] for span in kept_spans}
        node_evidence_map = self._node_evidence_map()
        trimmed = dict(bag)
        trimmed["evidence_spans"] = kept_spans
        trimmed["evidence_span_ids"] = [span["evidence_span_id"] for span in kept_spans]
        trimmed["selected_nodes"] = [
            node for node in bag.get("selected_nodes", [])
            if node["kind"] == "entity"
            or kept_span_ids.intersection(node_evidence_map.get(node["node_id"], set()))
        ]
        trimmed["summary"] = {
            "node_count": len(trimmed["selected_nodes"]),
            "hyperedge_count": len(trimmed.get("selected_hyperedge_ids", [])),
            "evidence_span_count": len(kept_spans),
        }
        return trimmed

    def _node_evidence_map(self) -> dict[str, set[str]]:
        corpus = self._load_corpus()
        return {
            node["node_id"]: set(node.get("evidence_span_ids", []))
            for node in corpus.get("nodes", [])
        }

    def _ensure_corpus(self) -> None:
        if not self.corpus_path().exists():
            save_corpus_bundle(self.store_root, build_corpus_bundle(self.corpus_id, []))

    def _load_corpus(self) -> dict[str, Any]:
        return load_corpus_bundle(self.store_root, self.corpus_id)

    def _normalize_corpus(self, corpus: dict[str, Any]) -> None:
        corpus["documents"].sort(key=lambda item: item["document_id"])
        corpus["evidence_spans"].sort(key=lambda item: (item["document_id"], item["start"], item["evidence_span_id"]))
        corpus["nodes"].sort(key=lambda item: (item["kind"], item["node_id"]))
        corpus["hyperedges"].sort(key=lambda item: (item["kind"], item["hyperedge_id"]))

    def _load_state(self) -> None:
        if not self.state_path.exists():
            return
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.goal = str(payload.get("goal", "") or "")

    def _save_state(self) -> None:
        self.state_path.write_text(json.dumps({"goal": self.goal}, indent=2), encoding="utf-8")
