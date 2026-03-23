"""
FILE: manifold_query.py
ROLE: Agent-facing manifold query tool.
WHAT IT DOES: Queries a reversible corpus bundle, scores matching nodes, and emits a self-sufficient evidence bag.
HOW TO USE:
  - Metadata: python _manifold-mcp/tools/manifold_query.py metadata
  - Run: python _manifold-mcp/tools/manifold_query.py run --input-json "{\"store_dir\":\"...\",\"corpus_id\":\"...\",\"query\":\"...\"}"
INPUT OBJECT:
  - store_dir: optional store root, defaults to artifacts/store
  - corpus_id: required corpus identifier
  - query: required search query
  - top_n: optional count of top matched nodes, defaults 12
NOTES:
  - The evidence bag is the portal object for later extraction.
  - The bag contains exact evidence spans so it can be used without re-querying.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result
from lib.manifold_store import build_evidence_bag, load_corpus_bundle, save_bag


FILE_METADATA = {
    "tool_name": "manifold_query",
    "version": "1.0.0",
    "entrypoint": "tools/manifold_query.py",
    "category": "query",
    "summary": "Query a reversible manifold corpus and produce an evidence bag.",
    "mcp_name": "manifold_query",
    "input_schema": {
        "type": "object",
        "properties": {
            "store_dir": {"type": "string"},
            "corpus_id": {"type": "string"},
            "query": {"type": "string"},
            "top_n": {"type": "integer", "default": 12}
        },
        "required": ["corpus_id", "query"],
        "additionalProperties": False
    }
}


def run(arguments: dict) -> dict:
    store_dir = Path(arguments.get("store_dir") or (Path(__file__).resolve().parents[1] / "artifacts" / "store")).resolve()
    corpus_id = str(arguments["corpus_id"])
    query = str(arguments["query"])
    top_n = max(1, int(arguments.get("top_n", 12)))

    corpus_bundle = load_corpus_bundle(store_dir, corpus_id)
    bag = build_evidence_bag(corpus_bundle, query, top_n=top_n)
    bag_file = save_bag(store_dir, corpus_id, bag)
    result = {
        "corpus_id": corpus_id,
        "store_dir": str(store_dir),
        "query": query,
        "bag_id": bag["bag_id"],
        "bag_file": str(bag_file),
        "summary": bag["summary"],
        "selected_nodes": bag["selected_nodes"],
        "evidence_spans": bag["evidence_spans"][:20],
        "selected_hyperedge_ids": bag["selected_hyperedge_ids"],
        "artifacts": {
            "bag": str(bag_file)
        }
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
