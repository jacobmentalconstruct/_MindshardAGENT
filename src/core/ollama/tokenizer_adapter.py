"""Pluggable tokenizer adapter for token estimation.

Strategy (preferred order):
  1. Exact model tokenizer if cheaply available
  2. Fallback heuristic (~4 chars per token)

Version 1 uses the heuristic only. The adapter interface exists
so model-specific tokenizers can be plugged in later.
"""

from src.core.utils.text_metrics import estimate_tokens as _heuristic


class TokenizerAdapter:
    """Token count estimator with pluggable backend."""

    def __init__(self, model_name: str = ""):
        self.model_name = model_name

    def count(self, text: str) -> int:
        """Estimate token count for the given text."""
        return _heuristic(text)

    def label(self) -> str:
        """Return the estimation method label for UI display."""
        return "heuristic (~4 chars/token)"
