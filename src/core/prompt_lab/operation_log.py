"""Operation logging for Prompt Lab admin and runtime-facing actions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.core.utils.clock import utc_iso


class PromptLabOperationLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        channel: str,
        action: str,
        status: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "timestamp": utc_iso(),
            "channel": channel,
            "action": action,
            "status": status,
            "details": details or {},
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
        return event

    def tail(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        events: list[dict[str, Any]] = []
        for line in lines[-max(1, int(limit)):]:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events
