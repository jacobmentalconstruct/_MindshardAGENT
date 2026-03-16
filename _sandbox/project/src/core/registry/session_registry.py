"""Session-level registry integration.

Bridges the session store (SQLite persistence) with the in-memory
state registry, creating node records for sessions and messages.
"""

from src.core.registry.state_registry import StateRegistry
from src.core.runtime.runtime_logger import get_logger

log = get_logger("session_registry")


def register_session(registry: StateRegistry, session_id: str,
                     title: str, model: str = "") -> str:
    """Register a session as a node in the state registry."""
    node = registry.create_node(
        node_type="session",
        label=title,
        metadata={"session_id": session_id, "model": model},
    )
    log.debug("Session registered: %s -> %s", session_id, node.node_id)
    return node.node_id


def register_message(registry: StateRegistry, session_node_id: str,
                     role: str, content_preview: str = "") -> str:
    """Register a message as a child node of a session."""
    node = registry.create_node(
        node_type="message",
        label=f"{role}: {content_preview[:50]}",
        parent_id=session_node_id,
        metadata={"role": role},
    )
    return node.node_id
