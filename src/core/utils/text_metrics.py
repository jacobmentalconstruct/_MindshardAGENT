"""Lightweight token estimation and text metrics.

Uses a rough heuristic by default. A pluggable adapter can replace this
with model-specific tokenizer counts when available.
"""

import re

_WORD_RE = re.compile(r"\S+")


def estimate_tokens(text: str) -> int:
    """Estimate token count using the ~4-chars-per-token heuristic.

    This is intentionally approximate. Display as 'Approx tokens: N'.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


def word_count(text: str) -> int:
    """Count whitespace-delimited words."""
    return len(_WORD_RE.findall(text))


def char_count(text: str) -> int:
    return len(text)
