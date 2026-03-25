"""
FILE: bag_inspect.py
ROLE: Inspect the agent's evidence bag — see what the agent sees.
WHAT IT DOES: Opens the agent's evidence bag for a given session directory,
    returns both the full bag contents (all nodes/spans) and the prompt-injected
    summary slice the agent would receive at a given token budget.
HOW TO USE:
  - Metadata: python _manifold-mcp/tools/bag_inspect.py metadata
  - Run: python _manifold-mcp/tools/bag_inspect.py run --input-json "{\"session_dir\":\"...\",\"query\":\"...\"}"
INPUT OBJECT:
  - session_dir: path to .mindshard/sessions/ directory
  - corpus_id: optional corpus identifier, defaults to "evidence"
  - query: optional query to score against (defaults to empty)
  - summary_budget: optional token budget for the summary slice (default 128)
  - retrieval_budget: optional token budget for deep retrieval view (default 512)
NOTES:
  - Shows two views: the compact summary (what goes into every prompt) and the
    deep retrieval (what pass-2 would pull). Also lists all documents in the corpus.
  - The evidence bag is NOT a replacement for STM/RAG — it is a retrieval supplement.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result
from sdk.evidence_package import EvidencePackage


FILE_METADATA = {
    "tool_name": "bag_inspect",
    "version": "1.1.0",
    "entrypoint": "tools/bag_inspect.py",
    "category": "inspect",
    "summary": "Inspect the agent's evidence bag — see full contents, the prompt summary slice, and deep retrieval view.",
    "mcp_name": "bag_inspect",
    "input_schema": {
        "type": "object",
        "properties": {
            "session_dir": {"type": "string", "description": "Path to .mindshard/sessions/ directory"},
            "corpus_id": {"type": "string", "default": "evidence"},
            "query": {"type": "string", "default": ""},
            "summary_budget": {"type": "integer", "default": 128},
            "retrieval_budget": {"type": "integer", "default": 512},
        },
        "required": ["session_dir"],
        "additionalProperties": False,
    },
}


def run(arguments: dict) -> dict:
    session_dir = Path(arguments["session_dir"]).resolve()
    corpus_id = str(arguments.get("corpus_id") or "evidence")
    query = str(arguments.get("query") or "")
    summary_budget = max(32, int(arguments.get("summary_budget", 128)))
    retrieval_budget = max(64, int(arguments.get("retrieval_budget", 512)))

    db_path = session_dir / f"{corpus_id}.db"
    if not db_path.parent.exists():
        return tool_result(FILE_METADATA["tool_name"], arguments, {
            "status": "empty",
            "message": f"Session directory not found: {session_dir}",
            "corpus_exists": False,
        })

    pkg = EvidencePackage(db_path=db_path)

    # Load full corpus inventory
    corpus = pkg._load_corpus()
    all_documents = corpus.get("documents", [])
    all_spans = corpus.get("evidence_spans", [])
    all_nodes = corpus.get("nodes", [])

    # Build the summary slice (what the agent sees every turn)
    summary_window = pkg.window(query, token_budget=summary_budget) if query else {
        "text": "", "summary": {"span_count": 0, "char_count": 0, "node_count": 0},
        "selected_nodes": [], "evidence_spans": [],
    }

    # Build the deep retrieval view (what pass-2 would pull)
    retrieval_window = pkg.window(query, token_budget=retrieval_budget) if query else {
        "text": "", "summary": {"span_count": 0, "char_count": 0, "node_count": 0},
        "selected_nodes": [], "evidence_spans": [],
    }

    # Document inventory (compact — just IDs and titles, not full text)
    doc_inventory = [
        {
            "document_id": doc["document_id"],
            "title": doc.get("title", ""),
            "source_type": doc.get("source_type", ""),
            "text_preview": doc.get("text", "")[:200] if "text" in doc else "",
            "text_length": doc.get("char_count", 0),
        }
        for doc in all_documents
    ]

    result = {
        "corpus_id": corpus_id,
        "session_dir": str(session_dir),
        "goal": pkg.goal,
        "corpus_stats": {
            "document_count": len(all_documents),
            "span_count": len(all_spans),
            "node_count": len(all_nodes),
            "total_chars": sum(d.get("char_count", 0) for d in all_documents),
        },
        "documents": doc_inventory,
        "agent_sees": {
            "description": "This is the summary slice injected into the agent's prompt every turn",
            "token_budget": summary_budget,
            "summary": summary_window["summary"],
            "text": summary_window["text"],
            "node_count": len(summary_window["selected_nodes"]),
        },
        "pass2_retrieval": {
            "description": "This is what pass-2 deep retrieval would return if triggered",
            "token_budget": retrieval_budget,
            "summary": retrieval_window["summary"],
            "text": retrieval_window["text"],
            "node_count": len(retrieval_window["selected_nodes"]),
        },
    }

    pkg.close()
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
