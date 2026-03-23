"""
FILE: manifold_store.py
ROLE: Internal reversible storage helpers for _manifold-mcp.
WHAT IT DOES: Builds and loads reversible corpus bundles, evidence bags, and graph records.
HOW TO USE:
  - Import from user-facing tools under tools/.
  - This is internal support code, not a direct tool entrypoint.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from common import ensure_dir, now_stamp, read_json, write_json


SENTENCE_PATTERN = re.compile(r"[^.!?\n]+[.!?]?|\n")
ENTITY_PATTERN = re.compile(r"\b[A-Z][A-Za-z0-9_-]{2,}(?:\s+[A-Z][A-Za-z0-9_-]{2,})*")
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]{2,}")


def corpus_store_dir(base_dir: str | Path, corpus_id: str) -> Path:
    return Path(base_dir).resolve() / corpus_id


def corpus_bundle_path(base_dir: str | Path, corpus_id: str) -> Path:
    return corpus_store_dir(base_dir, corpus_id) / "corpus.json"


def bag_path(base_dir: str | Path, corpus_id: str, bag_id: str) -> Path:
    return corpus_store_dir(base_dir, corpus_id) / "bags" / f"{bag_id}.json"


def slugify(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    return text or "corpus"


def deterministic_id(prefix: str, payload: str) -> str:
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def split_sentences(text: str) -> list[dict[str, Any]]:
    spans = []
    for match in SENTENCE_PATTERN.finditer(text):
        fragment = match.group(0)
        if fragment == "\n":
            continue
        normalized = fragment.strip()
        if not normalized:
            continue
        spans.append({
            "start": match.start(),
            "end": match.end(),
            "text": text[match.start():match.end()],
        })
    return spans


def extract_entities(text: str) -> list[str]:
    seen = []
    seen_set = set()
    for match in ENTITY_PATTERN.finditer(text):
        entity = match.group(0).strip()
        if entity not in seen_set:
            seen.append(entity)
            seen_set.add(entity)
    return seen


def load_text_inputs(arguments: dict, *, repo_root: Path) -> list[dict[str, Any]]:
    documents = []

    for index, item in enumerate(arguments.get("texts", []), start=1):
        if not isinstance(item, dict):
            raise ValueError("Each texts[] entry must be an object.")
        text = str(item.get("text", ""))
        if not text.strip():
            continue
        document_id = str(item.get("id") or deterministic_id("doc", f"inline:{index}:{text[:80]}"))
        documents.append({
            "document_id": document_id,
            "title": str(item.get("title") or document_id),
            "source_type": "inline",
            "source_path": "",
            "metadata": dict(item.get("metadata", {})),
            "text": text,
        })

    for raw_path in arguments.get("files", []):
        path = Path(raw_path)
        if not path.is_absolute():
            path = (repo_root / path).resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Input file not found: {path}")
        text = path.read_text(encoding="utf-8", errors="replace")
        document_id = deterministic_id("doc", str(path))
        documents.append({
            "document_id": document_id,
            "title": path.name,
            "source_type": "file",
            "source_path": str(path),
            "metadata": {"suffix": path.suffix.lower()},
            "text": text,
        })

    if not documents:
        raise ValueError("Provide at least one inline text or file.")
    return documents


def build_corpus_bundle(corpus_id: str, documents: list[dict[str, Any]]) -> dict[str, Any]:
    corpus = {
        "corpus_id": corpus_id,
        "created_at": now_stamp(),
        "documents": [],
        "evidence_spans": [],
        "nodes": [],
        "hyperedges": [],
    }

    entity_node_ids: dict[str, str] = {}
    entity_to_evidence: dict[str, list[str]] = defaultdict(list)

    for document in documents:
        document_text = document["text"]
        corpus["documents"].append({
            "document_id": document["document_id"],
            "title": document["title"],
            "source_type": document["source_type"],
            "source_path": document["source_path"],
            "metadata": document["metadata"],
            "char_count": len(document_text),
        })

        document_node_id = deterministic_id("node_doc", document["document_id"])
        corpus["nodes"].append({
            "node_id": document_node_id,
            "kind": "document",
            "label": document["title"],
            "document_id": document["document_id"],
            "evidence_span_ids": [],
            "text": "",
        })

        for sentence_index, sentence in enumerate(split_sentences(document_text), start=1):
            evidence_span_id = deterministic_id(
                "ev",
                f"{document['document_id']}:{sentence['start']}:{sentence['end']}:{sentence['text']}",
            )
            corpus["evidence_spans"].append({
                "evidence_span_id": evidence_span_id,
                "document_id": document["document_id"],
                "start": sentence["start"],
                "end": sentence["end"],
                "text": sentence["text"],
                "tokens": tokenize(sentence["text"]),
            })

            claim_node_id = deterministic_id("node_claim", evidence_span_id)
            corpus["nodes"].append({
                "node_id": claim_node_id,
                "kind": "claim",
                "label": sentence["text"].strip()[:120],
                "document_id": document["document_id"],
                "evidence_span_ids": [evidence_span_id],
                "text": sentence["text"],
                "sentence_index": sentence_index,
            })

            corpus["hyperedges"].append({
                "hyperedge_id": deterministic_id("edge_doc_claim", f"{document_node_id}:{claim_node_id}"),
                "kind": "document_contains_claim",
                "node_ids": [document_node_id, claim_node_id],
                "evidence_span_ids": [evidence_span_id],
                "document_id": document["document_id"],
            })
            corpus["hyperedges"].append({
                "hyperedge_id": deterministic_id("edge_claim_evidence", f"{claim_node_id}:{evidence_span_id}"),
                "kind": "claim_grounded_in_evidence",
                "node_ids": [claim_node_id],
                "evidence_span_ids": [evidence_span_id],
                "document_id": document["document_id"],
            })

            entity_ids = []
            for entity in extract_entities(sentence["text"]):
                entity_node_id = entity_node_ids.get(entity)
                if entity_node_id is None:
                    entity_node_id = deterministic_id("node_entity", entity)
                    entity_node_ids[entity] = entity_node_id
                    corpus["nodes"].append({
                        "node_id": entity_node_id,
                        "kind": "entity",
                        "label": entity,
                        "document_id": document["document_id"],
                        "evidence_span_ids": [],
                        "text": "",
                    })
                entity_ids.append(entity_node_id)
                entity_to_evidence[entity_node_id].append(evidence_span_id)
                corpus["hyperedges"].append({
                    "hyperedge_id": deterministic_id("edge_claim_entity", f"{claim_node_id}:{entity_node_id}:{evidence_span_id}"),
                    "kind": "claim_mentions_entity",
                    "node_ids": [claim_node_id, entity_node_id],
                    "evidence_span_ids": [evidence_span_id],
                    "document_id": document["document_id"],
                })

            unique_entity_ids = sorted(set(entity_ids))
            if len(unique_entity_ids) > 1:
                corpus["hyperedges"].append({
                    "hyperedge_id": deterministic_id("edge_entity_co", f"{evidence_span_id}:{'|'.join(unique_entity_ids)}"),
                    "kind": "entity_cooccurrence",
                    "node_ids": unique_entity_ids,
                    "evidence_span_ids": [evidence_span_id],
                    "document_id": document["document_id"],
                })

    for node in corpus["nodes"]:
        if node["kind"] == "entity":
            node["evidence_span_ids"] = sorted(set(entity_to_evidence.get(node["node_id"], [])))

    corpus["documents"].sort(key=lambda item: item["document_id"])
    corpus["evidence_spans"].sort(key=lambda item: (item["document_id"], item["start"], item["evidence_span_id"]))
    corpus["nodes"].sort(key=lambda item: (item["kind"], item["node_id"]))
    corpus["hyperedges"].sort(key=lambda item: (item["kind"], item["hyperedge_id"]))
    return corpus


def save_corpus_bundle(store_root: str | Path, corpus_bundle: dict[str, Any]) -> Path:
    target_dir = ensure_dir(corpus_store_dir(store_root, corpus_bundle["corpus_id"]))
    ensure_dir(target_dir / "bags")
    target_path = target_dir / "corpus.json"
    write_json(target_path, corpus_bundle)
    return target_path


def load_corpus_bundle(store_root: str | Path, corpus_id: str) -> dict[str, Any]:
    path = corpus_bundle_path(store_root, corpus_id)
    if not path.exists():
        raise FileNotFoundError(f"Corpus bundle not found: {path}")
    return read_json(path)


def build_evidence_bag(corpus_bundle: dict[str, Any], query: str, *, top_n: int) -> dict[str, Any]:
    query_tokens = set(tokenize(query))
    if not query_tokens:
        raise ValueError("Query must contain at least one searchable token.")

    nodes_by_id = {node["node_id"]: node for node in corpus_bundle["nodes"]}
    evidence_by_id = {item["evidence_span_id"]: item for item in corpus_bundle["evidence_spans"]}
    scored = []
    for node in corpus_bundle["nodes"]:
        searchable = " ".join(filter(None, [node.get("label", ""), node.get("text", "")]))
        overlap = sorted(query_tokens & set(tokenize(searchable)))
        if overlap:
            score = len(overlap)
            if node["kind"] == "claim":
                score += 2
            elif node["kind"] == "entity":
                score += 1
            scored.append({
                "node_id": node["node_id"],
                "kind": node["kind"],
                "label": node.get("label", ""),
                "score": score,
                "overlap_tokens": overlap,
            })

    scored.sort(key=lambda item: (-item["score"], item["kind"], item["node_id"]))
    selected_nodes = scored[:top_n]
    selected_node_ids = {item["node_id"] for item in selected_nodes}

    selected_edge_ids = []
    selected_evidence_ids = set()
    for edge in corpus_bundle["hyperedges"]:
        if selected_node_ids.intersection(edge["node_ids"]):
            selected_edge_ids.append(edge["hyperedge_id"])
            selected_evidence_ids.update(edge.get("evidence_span_ids", []))

    for node_id in selected_node_ids:
        selected_evidence_ids.update(nodes_by_id[node_id].get("evidence_span_ids", []))

    ordered_evidence = sorted(
        (evidence_by_id[evidence_id] for evidence_id in selected_evidence_ids if evidence_id in evidence_by_id),
        key=lambda item: (item["document_id"], item["start"], item["evidence_span_id"]),
    )

    bag_id = f"bag_{now_stamp()}"
    return {
        "bag_id": bag_id,
        "created_at": now_stamp(),
        "corpus_id": corpus_bundle["corpus_id"],
        "query": query,
        "selected_nodes": selected_nodes,
        "selected_node_ids": sorted(selected_node_ids),
        "selected_hyperedge_ids": sorted(set(selected_edge_ids)),
        "evidence_spans": ordered_evidence,
        "evidence_span_ids": [item["evidence_span_id"] for item in ordered_evidence],
        "summary": {
            "node_count": len(selected_nodes),
            "hyperedge_count": len(set(selected_edge_ids)),
            "evidence_span_count": len(ordered_evidence),
        },
    }


def save_bag(store_root: str | Path, corpus_id: str, bag: dict[str, Any]) -> Path:
    path = bag_path(store_root, corpus_id, bag["bag_id"])
    ensure_dir(path.parent)
    write_json(path, bag)
    return path


def load_bag(store_root: str | Path, corpus_id: str, bag_id: str | None = None, bag_file: str | Path | None = None) -> dict[str, Any]:
    if bag_file:
        return read_json(Path(bag_file).resolve())
    if not bag_id:
        raise ValueError("Provide bag_id or bag_file.")
    path = bag_path(store_root, corpus_id, bag_id)
    if not path.exists():
        raise FileNotFoundError(f"Bag not found: {path}")
    return read_json(path)


def reconstruct_text_from_bag(bag: dict[str, Any], *, mode: str = "grouped") -> dict[str, Any]:
    spans = list(bag.get("evidence_spans", []))
    if not spans:
        return {"text": "", "documents": [], "span_count": 0}

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for span in spans:
        grouped[span["document_id"]].append(span)

    documents = []
    for document_id in sorted(grouped):
        ordered = sorted(grouped[document_id], key=lambda item: (item["start"], item["evidence_span_id"]))
        merged_parts = []
        current = None
        for span in ordered:
            if current is None:
                current = dict(span)
                continue
            if span["start"] <= current["end"]:
                overlap = max(0, current["end"] - span["start"])
                current["text"] += span["text"][overlap:]
                current["end"] = max(current["end"], span["end"])
            else:
                merged_parts.append(current)
                current = dict(span)
        if current is not None:
            merged_parts.append(current)

        documents.append({
            "document_id": document_id,
            "text": "\n".join(part["text"] for part in merged_parts).strip(),
            "merged_span_count": len(merged_parts),
            "source_span_ids": [span["evidence_span_id"] for span in ordered],
        })

    if mode == "verbatim":
        text = "\n\n".join(item["text"] for item in documents)
    else:
        text = "\n\n".join(f"[{item['document_id']}]\n{item['text']}" for item in documents)

    return {
        "text": text.strip(),
        "documents": documents,
        "span_count": len(spans),
    }
