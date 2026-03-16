# Prototype Registry State Graph

## Intent

This prototype is the **lean base kernel** for app-state registry and graph-like coordination.

It is deliberately **not** a full graph backend.

Its purpose is to:

- preserve stable identity
- preserve parent/child and containment relations
- preserve hunk-level processing state
- preserve facet attachment
- preserve exact references to CAS/CIS-backed payloads
- preserve enough structure that it can later be **strangled upward** into a fuller multi-facet graph system without throwing away the prototype data model

The prototype therefore behaves like a **registry with graph semantics**, not a full graph database.

---

## Design Requirement

The prototype must be built so that every core record can later be promoted into a richer graph node or edge without invalidating identity.

That means:

- IDs must already be stable
- records must already be typed
- parent/child references must already exist
- facet ownership must already exist
- hunk lineage must already exist
- CAS/CIS references must already exist
- semantic processing outputs must already be attachable as facets

The upgrade path is:

> prototype registry record -> promoted graph node / graph edge / graph facet node

rather than:

> prototype is discarded and rewritten from scratch

---

# 1. Core Architectural Position

This prototype is a **single-script state registry** that manages app state as a set of typed records and indexed relations.

Instead of implementing a true graph engine, it uses:

- dataclasses
- dictionaries
- adjacency indexes
- owner indexes
- stable IDs
- typed relation records

This gives you:

- simplicity
- debuggability
- serializability
- testability
- clean upgrade path

---

# 2. Conceptual Model

## 2.1 The Registry

The registry is the single in-memory authority for all known stateful entities relevant to the app-state graph layer.

It owns:

- nodes
- hunks
- facets
- relations
- token pools
- span records
- provenance entries

## 2.2 Graph Semantics Without Full Graph Machinery

The prototype should already *think* in graph terms, even if implementation is registry-based.

That means the registry already models:

- node identity
- typed relations
- parent/child containment
- ownership
- sequence
- attachment
- provenance

But these are stored as compact records and indexes rather than heavyweight graph-native objects.

---

# 3. Main Records

## 3.1 NodeRecord

Represents a registry-controlled object that may later become a full graph node.

Examples:
- source artifact
- app state object
- file state
- logical region
- hunk owner
- UI component state root

Suggested fields:

```python
@dataclass
class NodeRecord:
    node_id: str
    node_type: str
    label: str = ""
    parent_id: str | None = None
    state_flags: set[str] = field(default_factory=set)
    facet_ids: list[str] = field(default_factory=list)
    child_ids: list[str] = field(default_factory=list)
    hunk_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

Purpose:
- stable identity carrier
- upgrade target for future graph node promotion

---

## 3.2 HunkRecord

Represents a processing unit derived from a node.

Suggested fields:

```python
@dataclass
class HunkRecord:
    hunk_id: str
    owner_node_id: str
    sequence_index: int
    verbatim_ref: str | None = None
    token_span_ids: list[str] = field(default_factory=list)
    token_occurrence_ids: list[str] = field(default_factory=list)
    facet_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

Purpose:
- local processing carrier
- semantic projection input unit
- later promotable into a subgraph root node

---

## 3.3 FacetRecord

Represents an attached typed facet.

Suggested fields:

```python
@dataclass
class FacetRecord:
    facet_id: str
    owner_id: str
    owner_kind: str   # "node" | "hunk" | "span"
    facet_type: str   # "verbatim" | "semantic" | "structural" | "trace" | "rehydration"
    payload: dict[str, Any] = field(default_factory=dict)
```

Purpose:
- attach typed channel data without bloating the core records
- preserve same concept as later multi-facet graph nodes

---

## 3.4 RelationRecord

Represents typed relation semantics in registry form.

Suggested fields:

```python
@dataclass
class RelationRecord:
    relation_id: str
    relation_type: str
    source_id: str
    target_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
```

Examples:
- `CHILD_OF`
- `OWNS_HUNK`
- `HAS_FACET`
- `NEXT_HUNK`
- `USES_TOKEN`
- `DERIVED_FROM`

Purpose:
- preserve graph semantics explicitly
- easy to promote into future graph edges

---

## 3.5 CanonicalTokenRecord

Represents deduplicated token identity.

Suggested fields:

```python
@dataclass
class CanonicalTokenRecord:
    canonical_token_id: str
    token_text: str
    token_namespace: str
    token_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)
```

Purpose:
- deduped token pool
- shared token identity
- upgrade target for canonical token graph node

---

## 3.6 TokenSpanRecord

Represents ordered token references compactly.

Suggested fields:

```python
@dataclass
class TokenSpanRecord:
    span_id: str
    hunk_id: str
    ordered_token_ids: list[str] = field(default_factory=list)
    start_index: int = 0
    end_index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
```

Purpose:
- preserve local sequence without spawning huge occurrence graphs
- later promotable into a proper subgraph span node

---

## 3.7 TokenOccurrenceRecord (optional)

Used only when exact per-occurrence identity is needed.

Suggested fields:

```python
@dataclass
class TokenOccurrenceRecord:
    occurrence_id: str
    hunk_id: str
    canonical_token_id: str
    position_index: int
    metadata: dict[str, Any] = field(default_factory=dict)
```

Default should be **off** unless exact per-token graph traversal is needed.

---

## 3.8 ProvenanceRecord

Represents transformation lineage and processing trace.

Suggested fields:

```python
@dataclass
class ProvenanceRecord:
    provenance_id: str
    stage: str
    input_ids: list[str] = field(default_factory=list)
    output_ids: list[str] = field(default_factory=list)
    operator_name: str = ""
    operator_version: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
```

Purpose:
- preserve how something was produced
- later promotable into a trace/provenance subgraph

---

# 4. Registry Container

The entire prototype lives inside one primary container.

```python
@dataclass
class RegistryState:
    nodes: dict[str, NodeRecord] = field(default_factory=dict)
    hunks: dict[str, HunkRecord] = field(default_factory=dict)
    facets: dict[str, FacetRecord] = field(default_factory=dict)
    relations: dict[str, RelationRecord] = field(default_factory=dict)
    canonical_tokens: dict[str, CanonicalTokenRecord] = field(default_factory=dict)
    spans: dict[str, TokenSpanRecord] = field(default_factory=dict)
    occurrences: dict[str, TokenOccurrenceRecord] = field(default_factory=dict)
    provenance: dict[str, ProvenanceRecord] = field(default_factory=dict)

    children_by_parent: dict[str, list[str]] = field(default_factory=dict)
    hunks_by_owner: dict[str, list[str]] = field(default_factory=dict)
    facets_by_owner: dict[str, list[str]] = field(default_factory=dict)
    outgoing_relations: dict[str, list[str]] = field(default_factory=dict)
    incoming_relations: dict[str, list[str]] = field(default_factory=dict)
```

This gives you graph-like traversal while remaining lightweight.

---

# 5. Minimal API Surface

The prototype should expose a small, strict surface.

## 5.1 Node lifecycle

```python
create_node(node_type: str, label: str = "", parent_id: str | None = None, metadata: dict | None = None) -> NodeRecord
get_node(node_id: str) -> NodeRecord
list_children(node_id: str) -> list[NodeRecord]
```

## 5.2 Hunk lifecycle

```python
create_hunk(owner_node_id: str, sequence_index: int, verbatim_ref: str | None = None, metadata: dict | None = None) -> HunkRecord
list_hunks(owner_node_id: str) -> list[HunkRecord]
```

## 5.3 Facet lifecycle

```python
attach_facet(owner_id: str, owner_kind: str, facet_type: str, payload: dict) -> FacetRecord
get_facets(owner_id: str) -> list[FacetRecord]
get_facets_by_type(owner_id: str, facet_type: str) -> list[FacetRecord]
```

## 5.4 Relations

```python
link(source_id: str, target_id: str, relation_type: str, metadata: dict | None = None) -> RelationRecord
get_outgoing(source_id: str, relation_type: str | None = None) -> list[RelationRecord]
get_incoming(target_id: str, relation_type: str | None = None) -> list[RelationRecord]
```

## 5.5 Canonical token pool

```python
get_or_create_canonical_token(token_text: str, token_namespace: str) -> CanonicalTokenRecord
```

## 5.6 Span handling

```python
create_span(hunk_id: str, ordered_token_ids: list[str], start_index: int, end_index: int, metadata: dict | None = None) -> TokenSpanRecord
```

## 5.7 Provenance

```python
record_provenance(stage: str, input_ids: list[str], output_ids: list[str], operator_name: str = "", operator_version: str = "", metadata: dict | None = None) -> ProvenanceRecord
```

## 5.8 Serialization

```python
to_dict() -> dict
from_dict(data: dict) -> RegistryState
save_json(path: str) -> None
load_json(path: str) -> RegistryState
```

---

# 6. Processing Layout

## 6.1 Ingesting an artifact

Prototype flow:

1. create a root `NodeRecord` for the artifact
2. attach verbatim facet pointing to CAS/CIS blob ref
3. optionally create child nodes for logical regions
4. split into hunks
5. register `HunkRecord`s
6. attach structural facet(s)

This already mirrors the later richer graph flow.

---

## 6.2 Feeding the embedder

The embedder should not consume a loose string if the registry is available.

Instead the prototype should build a deterministic **Hunk Envelope**:

```python
@dataclass
class HunkEnvelope:
    hunk_id: str
    owner_node_id: str
    verbatim_ref: str | None
    token_span_ids: list[str]
    canonical_projection: dict[str, Any]
```

The embedder can then:

1. read the hunk envelope
2. compute semantic projection
3. emit semantic payload
4. attach semantic facet back to the `HunkRecord`
5. record provenance

This ensures the prototype already behaves like a future multi-facet graph pipeline.

---

## 6.3 Attaching semantic facets

Example payload:

```python
{
    "embedder_name": "bdvec",
    "embedder_version": "vX",
    "mode": "semantic_neighbors",
    "vector_dim": 384,
    "vector_ref": "vec://...",
    "projection_hash": "...",
    "loss_profile": "semantic_only"
}
```

The semantic facet is **owned by the hunk** or **owned by the node**, depending on scope.

Default recommendation:
- hunk-level semantic facets for local processing
- node-level semantic facets only for aggregated representations

---

# 7. Promotion Path to a Rich Graph Backend

This is the most important section.

The prototype must be shaped so that future graph promotion is a **mechanical migration**, not a conceptual rewrite.

## 7.1 Promotion mapping

| Prototype Record | Future Rich Graph Form |
|---|---|
| `NodeRecord` | graph node |
| `HunkRecord` | hunk node / subgraph root |
| `FacetRecord` | facet node or typed node payload |
| `RelationRecord` | graph edge |
| `CanonicalTokenRecord` | canonical token node |
| `TokenSpanRecord` | sequence/span node |
| `TokenOccurrenceRecord` | token occurrence node |
| `ProvenanceRecord` | provenance/trace node or subgraph |

## 7.2 Required invariant for promotion

Every prototype record must already have:

- stable ID
- stable type
- ownership context
- serializable payload
- explicit relation references

If those exist, migration is straightforward.

---

# 8. Why This Prototype Can Be “Strangled” Into the Bigger System

Because it already preserves the same **semantic categories** as the large design:

- identity
- containment
- facet attachment
- relation typing
- token dedupe
- span preservation
- provenance

The fancy graph backend merely adds:

- richer traversal
- richer indexing
- richer subgraph operations
- more native graph behavior

It does **not** require a different worldview.

That is exactly what makes strangler migration possible.

---

# 9. Efficiency Rules

The prototype must remain lean.

## 9.1 Defaults

Recommended defaults:

- canonical token dedupe: **on**
- token occurrence records: **off**
- token span records: **on**
- semantic facets: **on when needed**
- node-level aggregated semantic facets: **off by default**
- provenance recording: **minimal**

## 9.2 Things to avoid in prototype

Do not:

- duplicate verbatim payload inline if CAS/CIS ref exists
- create occurrence objects for every token by default
- over-model edge types too early
- embed everything automatically
- store giant vectors inline if vector refs are enough

## 9.3 Lean philosophy

The prototype is not trying to become the final graph.
It is trying to preserve the **upgradeable skeleton**.

---

# 10. Suggested Single-Script File Layout

If implemented as one file, organize it in this order:

1. imports
2. ID helpers
3. dataclasses
4. registry container
5. create/get/list helpers
6. relation helpers
7. token/span helpers
8. facet helpers
9. provenance helpers
10. serialization helpers
11. optional demo/test harness

---

# 11. Example Working Pattern

## Example: ingest one file

1. create root node:
   - `node_type="source_artifact"`
2. attach verbatim facet:
   - `facet_type="verbatim"`
   - payload includes CAS/CIS hash ref
3. create hunk records for each region
4. build token spans using canonical token pool
5. pass hunk envelopes to embedder
6. attach semantic facets to hunks
7. attach structural facet to root or child nodes
8. record provenance of embedding pass

This gives you enough state to:

- inspect app state
- reason over hunk ownership
- see which semantic passes occurred
- preserve upgrade path to a richer graph backend

---

# 12. Prototype Success Criteria

The prototype is successful if it can:

1. register nodes and hunks with stable IDs
2. attach multiple facet types without schema chaos
3. preserve parent/child structure
4. preserve hunk-to-node lineage
5. preserve deduped canonical token identity
6. preserve token order compactly via spans
7. attach semantic outputs as facets
8. serialize and reload cleanly
9. be promoted later into richer graph nodes and edges without data loss

---

# 13. Final Recommendation

Build the prototype first as a **strict registry kernel**.

Do not start with a hypergraph backend.
Do not start with token occurrence explosion.
Do not start with a heavy provenance engine.

Instead:

- keep it typed
- keep it serializable
- keep it upgradeable
- keep it graph-minded
- keep it lean

That gives you a working app-state graph prototype that can later be expanded into the richer multi-facet registry state graph without forcing a reset of your conceptual m