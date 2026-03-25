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

    # ── Structural layer ─────────────────────────────────────────────────────

    def inspect(self) -> dict[str, Any]:
        """Return a structural tree + flat manifest of the bag contents.

        The tree groups entries by document (each ingest_turn() = one document).
        Use focus(node_id) to read the full content of any document or claim node.

        Returns:
          goal       — current active goal string
          tree       — list of DocumentEntry dicts (one per ingested turn)
          stats      — aggregate counts
        """
        corpus = self._load_corpus()
        docs = {d["document_id"]: d for d in corpus.get("documents", [])}
        nodes = corpus.get("nodes", [])
        spans = corpus.get("evidence_spans", [])

        # Span text lookup by id
        span_text = {s["evidence_span_id"]: s["text"] for s in spans}

        # Group claim nodes by document_id
        claims_by_doc: dict[str, list[dict]] = {}
        doc_nodes: dict[str, dict] = {}
        for node in nodes:
            if node["kind"] == "document":
                doc_nodes[node["document_id"]] = node
            elif node["kind"] == "claim":
                claims_by_doc.setdefault(node["document_id"], []).append(node)

        tree = []
        for doc_id, doc in docs.items():
            doc_node = doc_nodes.get(doc_id, {})
            doc_claims = claims_by_doc.get(doc_id, [])
            # Parse source_role from title (format: "source_role:source")
            title_parts = doc.get("title", "").split(":", 1)
            source_role = title_parts[0] if title_parts else "unknown"
            source = title_parts[1] if len(title_parts) > 1 else ""
            tree.append({
                "node_id": doc_node.get("node_id", ""),
                "document_id": doc_id,
                "source_role": source_role,
                "source": source,
                "source_type": doc.get("source_type", ""),
                "chars": doc.get("char_count", 0),
                "claim_count": len(doc_claims),
                "preview": doc_claims[0]["text"][:120].strip() if doc_claims else "",
            })

        total_claims = sum(1 for n in nodes if n["kind"] == "claim")
        total_entities = sum(1 for n in nodes if n["kind"] == "entity")

        return {
            "goal": self.goal,
            "tree": tree,
            "stats": {
                "document_count": len(docs),
                "claim_count": total_claims,
                "entity_count": total_entities,
                "span_count": len(spans),
                "total_chars": sum(d.get("char_count", 0) for d in docs.values()),
            },
        }

    def focus(self, node_id: str) -> dict[str, Any]:
        """Return the full content of a node and its immediate neighbors.

        Supports document nodes (returns all claims in the document) and
        claim nodes (returns the sentence + sibling claims in the same document).

        Args:
          node_id — node_id from inspect() tree output

        Returns:
          node      — the node record
          content   — reconstructed readable text for this node
          neighbors — list of related nodes (siblings, connected via hyperedges)
        """
        corpus = self._load_corpus()
        nodes_by_id = {n["node_id"]: n for n in corpus.get("nodes", [])}
        spans_by_id = {s["evidence_span_id"]: s for s in corpus.get("evidence_spans", [])}
        hyperedges = corpus.get("hyperedges", [])

        node = nodes_by_id.get(node_id)
        if node is None:
            return {
                "node": None,
                "content": "",
                "neighbors": [],
                "error": f"Node '{node_id}' not found in corpus",
            }

        # Gather text content for this node
        if node["kind"] == "document":
            # Return all claims in this document, in order
            doc_id = node["document_id"]
            claims = sorted(
                [n for n in corpus["nodes"]
                 if n["kind"] == "claim" and n["document_id"] == doc_id],
                key=lambda n: n.get("sentence_index", 0),
            )
            content = " ".join(c["text"] for c in claims)
            neighbor_ids = {c["node_id"] for c in claims}
        elif node["kind"] == "claim":
            # Return own text; find sibling claims in same document
            content = node.get("text", "")
            doc_id = node["document_id"]
            neighbor_ids = {
                n["node_id"] for n in corpus["nodes"]
                if n["kind"] == "claim"
                and n["document_id"] == doc_id
                and n["node_id"] != node_id
            }
        else:
            # Entity: gather all evidence spans this entity appears in
            span_ids = set(node.get("evidence_span_ids", []))
            content = " ".join(
                spans_by_id[sid]["text"]
                for sid in span_ids
                if sid in spans_by_id
            )
            # Neighbors: other nodes that share any of the same spans
            neighbor_ids = {
                n["node_id"] for n in corpus["nodes"]
                if n["node_id"] != node_id
                and span_ids.intersection(n.get("evidence_span_ids", []))
            }

        neighbors = [
            {
                "node_id": nid,
                "kind": nodes_by_id[nid]["kind"],
                "label": nodes_by_id[nid].get("label", "")[:120],
            }
            for nid in list(neighbor_ids)[:12]
            if nid in nodes_by_id
        ]

        return {
            "node": {
                "node_id": node["node_id"],
                "kind": node["kind"],
                "label": node.get("label", "")[:120],
                "document_id": node.get("document_id", ""),
            },
            "content": content,
            "neighbors": neighbors,
        }

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
