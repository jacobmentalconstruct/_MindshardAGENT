"""
FILE: manifold_ingest.py
ROLE: Agent-facing reversible ingest tool.
WHAT IT DOES: Ingests inline text or local files into a reversible corpus bundle with evidence spans, graph nodes, and hyperedges.
HOW TO USE:
  - Metadata: python _manifold-mcp/tools/manifold_ingest.py metadata
  - Run: python _manifold-mcp/tools/manifold_ingest.py run --input-file _manifold-mcp/jobs/examples/ingest_inline.json
INPUT OBJECT:
  - corpus_id: optional corpus identifier
  - store_dir: optional output directory, defaults to artifacts/store
  - texts: optional list of inline text objects with text/title/id/metadata
  - files: optional list of local file paths
NOTES:
  - Reversibility is anchored at exact sentence-level evidence spans.
  - Graph records are additive and never replace evidence text.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result
from lib.manifold_store import build_corpus_bundle, corpus_bundle_path, load_text_inputs, save_corpus_bundle, slugify


FILE_METADATA = {
    "tool_name": "manifold_ingest",
    "version": "1.0.0",
    "entrypoint": "tools/manifold_ingest.py",
    "category": "ingest",
    "summary": "Ingest text or files into a reversible manifold corpus bundle.",
    "mcp_name": "manifold_ingest",
    "input_schema": {
        "type": "object",
        "properties": {
            "corpus_id": {"type": "string"},
            "store_dir": {"type": "string"},
            "texts": {"type": "array", "items": {"type": "object"}, "default": []},
            "files": {"type": "array", "items": {"type": "string"}, "default": []}
        },
        "additionalProperties": False
    }
}


def run(arguments: dict) -> dict:
    repo_root = Path(__file__).resolve().parents[3]
    store_dir = Path(arguments.get("store_dir") or (Path(__file__).resolve().parents[1] / "artifacts" / "store")).resolve()
    documents = load_text_inputs(arguments, repo_root=repo_root)
    corpus_id = str(arguments.get("corpus_id") or slugify(documents[0]["title"]))
    corpus_bundle = build_corpus_bundle(corpus_id, documents)
    target_path = save_corpus_bundle(store_dir, corpus_bundle)
    result = {
        "corpus_id": corpus_id,
        "store_dir": str(store_dir),
        "corpus_bundle_path": str(target_path),
        "counts": {
            "document_count": len(corpus_bundle["documents"]),
            "evidence_span_count": len(corpus_bundle["evidence_spans"]),
            "node_count": len(corpus_bundle["nodes"]),
            "hyperedge_count": len(corpus_bundle["hyperedges"])
        },
        "documents": corpus_bundle["documents"][:10],
        "sample_evidence_spans": corpus_bundle["evidence_spans"][:10],
        "sample_nodes": corpus_bundle["nodes"][:10],
        "sample_hyperedges": corpus_bundle["hyperedges"][:10],
        "artifacts": {
            "corpus_bundle": str(corpus_bundle_path(store_dir, corpus_id))
        }
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
