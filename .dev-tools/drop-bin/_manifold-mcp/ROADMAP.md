# Roadmap

## Implemented Now

- reversible corpus ingest
- query to evidence bag
- evidence-bag extraction
- MCP server

## Recommended Next

- indexed store reads to avoid full corpus scans
- graph neighborhood scoring and contradiction surfacing
- richer entity extraction
- graph merge across multiple corpora
- manifold compare and diff tools
- optional embeddings as a secondary retrieval lane
- consumer examples that import the SDK without copying internals

## Non-Negotiable Rule

Any optimization must preserve exact evidence-span reversibility.
