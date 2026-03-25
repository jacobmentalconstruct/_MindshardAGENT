"""
FILE: bag_navigate.py
ROLE: Structural navigator for the evidence bag — tree view and node focus.
WHAT IT DOES: Exposes two operations on the bag:
  - inspect: returns a tree of all documents + item manifest (what's stored, at a glance)
  - focus: returns full content of a specific node and its immediate neighbors
HOW TO USE:
  - Metadata: python _manifold-mcp/tools/bag_navigate.py metadata
  - Run (inspect): python _manifold-mcp/tools/bag_navigate.py run --input-json "{\"session_dir\":\"...\",\"action\":\"inspect\"}"
  - Run (focus):   python _manifold-mcp/tools/bag_navigate.py run --input-json "{\"session_dir\":\"...\",\"action\":\"focus\",\"node_id\":\"node_doc_...\"}"
INPUT OBJECT:
  - session_dir: path to .mindshard/sessions/ directory (required)
  - action: "inspect" or "focus" (required)
  - corpus_id: optional corpus identifier, defaults to "evidence"
  - node_id: required when action="focus" — node_id from inspect() tree output
NOTES:
  - inspect() is the starting point: use it to see what is in the bag before querying.
  - focus() drills into a document node to read its full content, or a claim node to
    read that sentence and its siblings in the same document.
  - For scored query-based retrieval, use bag_inspect with a query string instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result
from sdk.evidence_package import EvidencePackage


FILE_METADATA = {
    "tool_name": "bag_navigate",
    "version": "1.0.0",
    "entrypoint": "tools/bag_navigate.py",
    "category": "inspect",
    "summary": "Structural tree view and node-focus viewport for the evidence bag.",
    "mcp_name": "bag_navigate",
    "input_schema": {
        "type": "object",
        "properties": {
            "session_dir": {
                "type": "string",
                "description": "Path to .mindshard/sessions/ directory",
            },
            "action": {
                "type": "string",
                "enum": ["inspect", "focus"],
                "description": "'inspect' returns the full tree + manifest; 'focus' returns one node's content + neighbors",
            },
            "corpus_id": {
                "type": "string",
                "default": "evidence",
                "description": "Corpus identifier, defaults to 'evidence'",
            },
            "node_id": {
                "type": "string",
                "description": "Node ID to focus on (required when action='focus'). Use a node_id from inspect() output.",
            },
        },
        "required": ["session_dir", "action"],
        "additionalProperties": False,
    },
}


def run(arguments: dict) -> dict:
    session_dir = Path(arguments["session_dir"]).resolve()
    action = str(arguments["action"])
    corpus_id = str(arguments.get("corpus_id") or "evidence")

    if not session_dir.exists():
        return tool_result(FILE_METADATA["tool_name"], arguments, {
            "status": "empty",
            "message": f"Session directory not found: {session_dir}",
        })

    db_path = session_dir / f"{corpus_id}.db"
    pkg = EvidencePackage(db_path=db_path)

    try:
        if action == "inspect":
            result = pkg.inspect()
            result["session_dir"] = str(session_dir)
            result["corpus_id"] = corpus_id
        elif action == "focus":
            node_id = str(arguments.get("node_id") or "")
            if not node_id:
                result = {
                    "error": "node_id is required when action='focus'. "
                             "Call inspect first to find node IDs.",
                }
            else:
                result = pkg.focus(node_id)
                result["session_dir"] = str(session_dir)
                result["corpus_id"] = corpus_id
        else:
            result = {"error": f"Unknown action '{action}'. Use 'inspect' or 'focus'."}
    finally:
        pkg.close()

    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
