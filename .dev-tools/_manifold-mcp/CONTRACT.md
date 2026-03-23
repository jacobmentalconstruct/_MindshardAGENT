# Contract

This subproject exists to keep text-to-graph workflows reversible.

## Builder Pledge

- Keep the folder isolated and portable.
- Keep the MCP path primary for agent use.
- Make evidence spans the irreversible source of truth.
- Keep graph structure additive, not lossy.
- Make every inference traceable to evidence spans.
- Make every evidence bag self-sufficient for extraction.
- Prefer explicit fields over clever compression.

## Standard Tool Contract

Every tool in `tools/` should:

- include a clear header block
- export `FILE_METADATA`
- export `run(arguments)`
- support `metadata`
- support `run --input-json`
- support `run --input-file`
- return a stable JSON envelope

## MCP Contract

- MCP is the primary operation path for agents.
- MCP tool names should stay stable once published.
- MCP must call the same `run(arguments)` logic as CLI execution.
- Do not fork behavior between MCP and CLI paths.

## Reversible Data Contract

The store should preserve these records explicitly:

- `documents`
- `evidence_spans`
- `nodes`
- `hyperedges`
- `bags`

## Thin Adapter Contract

The external SDK adapter should remain app-agnostic and portable.

Minimum expected methods:

- `set_goal(goal)`
- `ingest_turn(text, ...)`
- `window(query, token_budget=...)`
- `reconstruct(...)`
- `close()`

Minimum reversible fields:

- `document_id`
- `evidence_span_id`
- `start`
- `end`
- `text`
- `node_id`
- `hyperedge_id`
- `bag_id`

## Performance Note

The first version may read a whole corpus bundle for simplicity.
If corpus size grows, prefer adding indexes and partial loads without weakening reversibility.
