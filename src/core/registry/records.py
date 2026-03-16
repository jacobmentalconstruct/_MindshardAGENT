"""Typed record definitions for the lean prototype state registry.

These records preserve stable identity, typed relations, and serializable
payloads. They are designed for mechanical promotion into richer graph
nodes/edges later without invalidating identity.

Adapted from the prototype_registry_state_graph blueprint for chatbot use.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NodeRecord:
    """Registry-controlled entity that may later become a graph node."""
    node_id: str
    node_type: str          # app, session, message, tool_run, sandbox, model
    label: str = ""
    parent_id: str | None = None
    state_flags: set[str] = field(default_factory=set)
    facet_ids: list[str] = field(default_factory=list)
    child_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FacetRecord:
    """Typed facet attached to a node."""
    facet_id: str
    owner_id: str
    owner_kind: str         # "node"
    facet_type: str         # "config", "metrics", "state", "trace"
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class RelationRecord:
    """Typed relation between registry entities."""
    relation_id: str
    relation_type: str      # CHILD_OF, OWNS_MESSAGE, HAS_TOOL_RUN, etc.
    source_id: str
    target_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
