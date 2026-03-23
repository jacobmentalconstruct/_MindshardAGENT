# Manifold MCP

This folder is an isolated MCP-first subproject for reversible text-to-graph and graph-to-text workflows.

The governing idea is simple:

- text is ingested into exact evidence spans
- graph structure is built on top of those spans
- queries return an evidence bag
- extraction reconstructs verbatim text from that bag

The evidence bag is the portal between latent structure and recoverable source text.

## Purpose

Use this project to:

- ingest text, notes, code docs, or local files into a reversible manifold
- project source text into a hypergraph-like record set
- query the graph without losing exact source provenance
- reconstruct verbatim supporting text from evidence bags

## Layout

- `tools/`
  - stable user-facing tools
- `lib/`
  - shared reversible storage and graph helpers
- `sdk/`
  - thin in-process adapters for agents that want direct object APIs
- `jobs/`
  - machine-run example jobs
- `artifacts/`
  - corpus stores, bags, and extraction outputs
- `templates/`
  - reusable sample inputs
- `drop-bin/`
  - rough scripts awaiting conversion
- `common.py`
  - shared runtime and CLI contract
- `mcp_server.py`
  - MCP stdio entrypoint
- `smoke_test.py`
  - portable verification
- `tool_manifest.json`
  - machine-readable manifest
- `CONTRACT.md`
  - builder pledge and reversible contract
- `ROADMAP.md`
  - next implementation steps

## Current Tools

- `manifold_ingest`
- `manifold_query`
- `manifold_extract`

## SDK Surface

- `sdk.EvidencePackage`

This gives agents a thin direct API for:

- `set_goal(...)`
- `ingest_turn(...)`
- `window(...)`
- `reconstruct(...)`
- `close()`

## Vendoring

Zip or copy the entire `_manifold-mcp` folder as one unit.

- keep the folder name stable when possible
- preserve `tools/`, `lib/`, `sdk/`, and `mcp_server.py`
- treat `artifacts/` as runtime output, not source
- point agents at this folder directly for MCP or SDK use

The package is intentionally standalone. Consumer apps should import or call it from `.dev-tools` rather than re-homing its internals into app-local modules.

## MCP First

Start the MCP server with:

```powershell
python _manifold-mcp\mcp_server.py
```

The MCP server calls the same `run(arguments)` function used by the CLI tools.

## Standard CLI Contract

```powershell
python _manifold-mcp\tools\<tool>.py metadata
python _manifold-mcp\tools\<tool>.py run --input-json "{...}"
python _manifold-mcp\tools\<tool>.py run --input-file _manifold-mcp\jobs\examples\<job>.json
```

## Reversibility Contract

- Every graph claim must point back to one or more exact evidence spans.
- Every evidence span must preserve source document id, character offsets, and verbatim text.
- Every evidence bag must be sufficient for extraction without re-querying the graph.
- Text reconstruction must be possible from evidence alone.
- The thin SDK adapter must remain usable without any app-specific imports.
