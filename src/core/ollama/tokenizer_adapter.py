"""Pluggable tokenizer adapter for token estimation.

Strategy:
  1. Adaptive ratio from actual Ollama response metadata (chars/token)
  2. Fallback heuristic (~4 chars per token)

The adapter learns per-model ratios from real inference results,
giving increasingly accurate estimates over time.
"""

from src.core.utils.text_metrics import estimate_tokens as _heuristic
from src.core.runtime.runtime_logger import get_logger

log = get_logger("tokenizer")


class TokenizerAdapter:
    """Token count estimator with adaptive learning from Ollama responses."""

    def __init__(self, model_name: str = ""):
        self.model_name = model_name
        # Per-model learned ratio: chars per token
        self._ratios: dict[str, float] = {}
        self._sample_counts: dict[str, int] = {}

    def count(self, text: str) -> int:
        """Estimate token count for the given text."""
        model = self.model_name
        if model and model in self._ratios:
            ratio = self._ratios[model]
            return max(1, round(len(text) / ratio))
        return _heuristic(text)

    def learn_from_response(self, model: str, char_count: int, token_count: int) -> None:
        """Update the per-model chars-per-token ratio from actual inference data.

        Called after each Ollama response with the actual token counts.

        Args:
            model: Model name.
            char_count: Number of characters in the text.
            token_count: Actual token count from Ollama.
        """
        if token_count <= 0 or char_count <= 0:
            return

        new_ratio = char_count / token_count

        if model in self._ratios:
            # Exponential moving average — recent responses weighted more
            n = min(self._sample_counts.get(model, 0), 20)
            alpha = 2 / (n + 2)
            self._ratios[model] = (1 - alpha) * self._ratios[model] + alpha * new_ratio
            self._sample_counts[model] = n + 1
        else:
            self._ratios[model] = new_ratio
            self._sample_counts[model] = 1

        log.debug("Tokenizer ratio for %s: %.2f chars/token (%d samples)",
                  model, self._ratios[model], self._sample_counts.get(model, 0))

    def set_model(self, model_name: str) -> None:
        """Switch the active model for estimates."""
        self.model_name = model_name

    def label(self) -> str:
        """Return the estimation method label for UI display."""
        model = self.model_name
        if model and model in self._ratios:
            ratio = self._ratios[model]
            n = self._sample_counts.get(model, 0)
            return f"adaptive (~{ratio:.1f} chars/tok, {n} samples)"
        return "heuristic (~4 chars/token)"

    def get_ratio(self, model: str | None = None) -> float:
        """Get the current chars-per-token ratio for a model."""
        m = model or self.model_name
        return self._ratios.get(m, 4.0)
