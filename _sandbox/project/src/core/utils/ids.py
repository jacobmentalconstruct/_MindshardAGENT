"""Stable ID generation for registry records and runtime objects."""

import uuid
from datetime import datetime, timezone


def make_id(prefix: str = "") -> str:
    """Generate a stable unique ID with optional prefix.

    Format: {prefix}_{timestamp_hex}_{uuid4_short}
    Example: sess_018f3a2b_7c4d
    """
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    ts_hex = format(now, "x")[-8:]
    uid = uuid.uuid4().hex[:4]
    if prefix:
        return f"{prefix}_{ts_hex}_{uid}"
    return f"{ts_hex}_{uid}"


def make_session_id() -> str:
    return make_id("sess")


def make_message_id() -> str:
    return make_id("msg")


def make_tool_run_id() -> str:
    return make_id("trun")


def make_node_id(node_type: str = "node") -> str:
    return make_id(node_type)
