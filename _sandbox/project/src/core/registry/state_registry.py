"""Lean in-memory app state registry with graph semantics.

Single authority for all tracked stateful entities. Uses typed records,
dictionary storage, and adjacency indexes. Designed for promotion into
a richer graph backend later.
"""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.core.registry.records import NodeRecord, FacetRecord, RelationRecord
from src.core.utils.ids import make_node_id, make_id
from src.core.runtime.runtime_logger import get_logger

log = get_logger("state_registry")


class StateRegistry:
    """Lean prototype state registry with graph-like traversal."""

    def __init__(self):
        self.nodes: dict[str, NodeRecord] = {}
        self.facets: dict[str, FacetRecord] = {}
        self.relations: dict[str, RelationRecord] = {}

        # Indexes
        self.children_by_parent: dict[str, list[str]] = {}
        self.facets_by_owner: dict[str, list[str]] = {}
        self.outgoing_relations: dict[str, list[str]] = {}
        self.incoming_relations: dict[str, list[str]] = {}

    # ── Node lifecycle ────────────────────────────────

    def create_node(self, node_type: str, label: str = "",
                    parent_id: str | None = None,
                    metadata: dict | None = None) -> NodeRecord:
        node = NodeRecord(
            node_id=make_node_id(node_type),
            node_type=node_type,
            label=label,
            parent_id=parent_id,
            metadata=metadata or {},
        )
        self.nodes[node.node_id] = node
        if parent_id:
            self.children_by_parent.setdefault(parent_id, []).append(node.node_id)
            if parent_id in self.nodes:
                self.nodes[parent_id].child_ids.append(node.node_id)
        log.debug("Node created: %s (%s)", node.node_id, node_type)
        return node

    def get_node(self, node_id: str) -> NodeRecord | None:
        return self.nodes.get(node_id)

    def list_children(self, node_id: str) -> list[NodeRecord]:
        child_ids = self.children_by_parent.get(node_id, [])
        return [self.nodes[cid] for cid in child_ids if cid in self.nodes]

    # ── Facet lifecycle ───────────────────────────────

    def attach_facet(self, owner_id: str, facet_type: str,
                     payload: dict) -> FacetRecord:
        facet = FacetRecord(
            facet_id=make_id("facet"),
            owner_id=owner_id,
            owner_kind="node",
            facet_type=facet_type,
            payload=payload,
        )
        self.facets[facet.facet_id] = facet
        self.facets_by_owner.setdefault(owner_id, []).append(facet.facet_id)
        if owner_id in self.nodes:
            self.nodes[owner_id].facet_ids.append(facet.facet_id)
        return facet

    def get_facets(self, owner_id: str) -> list[FacetRecord]:
        fids = self.facets_by_owner.get(owner_id, [])
        return [self.facets[fid] for fid in fids if fid in self.facets]

    # ── Relations ─────────────────────────────────────

    def link(self, source_id: str, target_id: str, relation_type: str,
             metadata: dict | None = None) -> RelationRecord:
        rel = RelationRecord(
            relation_id=make_id("rel"),
            relation_type=relation_type,
            source_id=source_id,
            target_id=target_id,
            metadata=metadata or {},
        )
        self.relations[rel.relation_id] = rel
        self.outgoing_relations.setdefault(source_id, []).append(rel.relation_id)
        self.incoming_relations.setdefault(target_id, []).append(rel.relation_id)
        return rel

    def get_outgoing(self, source_id: str,
                     relation_type: str | None = None) -> list[RelationRecord]:
        rids = self.outgoing_relations.get(source_id, [])
        rels = [self.relations[rid] for rid in rids if rid in self.relations]
        if relation_type:
            rels = [r for r in rels if r.relation_type == relation_type]
        return rels

    # ── Serialization ─────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        def _convert(obj):
            d = asdict(obj)
            # Convert sets to lists for JSON
            for k, v in d.items():
                if isinstance(v, set):
                    d[k] = list(v)
            return d
        return {
            "nodes": {k: _convert(v) for k, v in self.nodes.items()},
            "facets": {k: _convert(v) for k, v in self.facets.items()},
            "relations": {k: _convert(v) for k, v in self.relations.items()},
        }

    def save_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        log.info("Registry saved to %s", path)

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def relation_count(self) -> int:
        return len(self.relations)
