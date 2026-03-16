"""Timestamp and timing helpers."""

from datetime import datetime, timezone
import time


def utc_now() -> datetime:
    """Current UTC datetime."""
    return datetime.now(timezone.utc)


def utc_iso() -> str:
    """Current UTC as ISO-8601 string."""
    return utc_now().isoformat()


def epoch_ms() -> int:
    """Current UTC as milliseconds since epoch."""
    return int(time.time() * 1000)


class Stopwatch:
    """Simple elapsed-time measurement."""

    def __init__(self):
        self._start = time.perf_counter()

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000

    def elapsed_s(self) -> float:
        return time.perf_counter() - self._start
