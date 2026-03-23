"""
FILE: manifold_extract.py
ROLE: Agent-facing reversible extraction tool.
WHAT IT DOES: Reconstructs verbatim text from an evidence bag or explicit evidence spans.
HOW TO USE:
  - Metadata: python _manifold-mcp/tools/manifold_extract.py metadata
  - Run: python _manifold-mcp/tools/manifold_extract.py run --input-json "{\"store_dir\":\"...\",\"corpus_id\":\"...\",\"bag_file\":\"...\"}"
INPUT OBJECT:
  - store_dir: optional store root, defaults to artifacts/store
  - corpus_id: required when using bag_id instead of bag_file
  - bag_id: optional evidence bag id
  - bag_file: optional path to a bag JSON file
  - bag: optional inline bag object
  - mode: optional output mode, `grouped` or `verbatim`
NOTES:
  - The extraction path uses the evidence bag only.
  - This is the reverse portal from structure back to source text.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result
from lib.manifold_store import load_bag, reconstruct_text_from_bag


FILE_METADATA = {
    "tool_name": "manifold_extract",
    "version": "1.0.0",
    "entrypoint": "tools/manifold_extract.py",
    "category": "extract",
    "summary": "Extract verbatim text from a manifold evidence bag.",
    "mcp_name": "manifold_extract",
    "input_schema": {
        "type": "object",
        "properties": {
            "store_dir": {"type": "string"},
            "corpus_id": {"type": "string"},
            "bag_id": {"type": "string"},
            "bag_file": {"type": "string"},
            "bag": {"type": "object"},
            "mode": {"type": "string", "enum": ["grouped", "verbatim"], "default": "grouped"}
        },
        "additionalProperties": False
    }
}


def run(arguments: dict) -> dict:
    store_dir = Path(arguments.get("store_dir") or (Path(__file__).resolve().parents[1] / "artifacts" / "store")).resolve()
    mode = str(arguments.get("mode", "grouped"))
    if mode not in {"grouped", "verbatim"}:
        raise ValueError("mode must be 'grouped' or 'verbatim'.")

    if arguments.get("bag"):
        bag = dict(arguments["bag"])
    else:
        corpus_id = arguments.get("corpus_id")
        if not corpus_id and not arguments.get("bag_file"):
            raise ValueError("Provide corpus_id when loading by bag_id.")
        bag = load_bag(store_dir, corpus_id or "", bag_id=arguments.get("bag_id"), bag_file=arguments.get("bag_file"))

    reconstruction = reconstruct_text_from_bag(bag, mode=mode)
    result = {
        "bag_id": bag.get("bag_id"),
        "corpus_id": bag.get("corpus_id"),
        "mode": mode,
        "summary": {
            "document_count": len(reconstruction["documents"]),
            "span_count": reconstruction["span_count"],
            "char_count": len(reconstruction["text"])
        },
        "documents": reconstruction["documents"],
        "text": reconstruction["text"]
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
