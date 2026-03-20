"""Model chain — sequential pipeline where Model A output feeds Model B input.

Inspired by _TheCELL's artifact-centric downstream task flow. Each step
produces an artifact that feeds forward into the next step. One direction
only — no backflow, no restart from earlier cells.

Usage:
    chain = ModelChain(base_url="http://localhost:11434")
    chain.add_step("qwen2.5-coder:3b", system="You are a code reviewer.", user="Review this: {input}")
    chain.add_step("qwen3.5:2b", system="You are a summarizer.", user="Summarize: {input}")
    results = chain.run("def hello(): print('hi')", on_step=callback)
"""

import json
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from src.core.runtime.runtime_logger import get_logger

log = get_logger("model_chain")


@dataclass
class ChainStep:
    """A single step in a model chain."""
    model: str
    system_prompt: str = ""
    user_template: str = "{input}"  # {input} gets replaced with previous output
    temperature: float = 0.7
    num_ctx: int = 8192
    label: str = ""  # optional human-readable label


@dataclass
class ChainArtifact:
    """Output from a single chain step — flows downstream."""
    step_index: int
    model: str
    label: str
    input_text: str
    output_text: str
    token_count: int
    duration_ms: float
    metadata: dict[str, Any] = field(default_factory=dict)


class ModelChain:
    """Sequential model pipeline — output flows forward, step by step."""

    def __init__(self, base_url: str = "http://localhost:11434"):
        self._base_url = base_url
        self._steps: list[ChainStep] = []

    def add_step(
        self,
        model: str,
        system: str = "",
        user: str = "{input}",
        temperature: float = 0.7,
        num_ctx: int = 8192,
        label: str = "",
    ) -> "ModelChain":
        """Add a step to the chain. Returns self for fluent chaining."""
        step = ChainStep(
            model=model,
            system_prompt=system,
            user_template=user,
            temperature=temperature,
            num_ctx=num_ctx,
            label=label or f"Step {len(self._steps) + 1}",
        )
        self._steps.append(step)
        return self

    def run(
        self,
        initial_input: str,
        on_step_start: Callable[[int, ChainStep], None] | None = None,
        on_step_complete: Callable[[ChainArtifact], None] | None = None,
        on_token: Callable[[int, str], None] | None = None,
    ) -> list[ChainArtifact]:
        """Execute the chain sequentially.

        Args:
            initial_input: The seed text for the first step.
            on_step_start: Called when each step begins (step_index, step).
            on_step_complete: Called when each step finishes (artifact).
            on_token: Called with (step_index, token) for streaming.

        Returns:
            List of ChainArtifact objects, one per step.
        """
        if not self._steps:
            log.warning("Empty chain, nothing to run")
            return []

        artifacts: list[ChainArtifact] = []
        current_input = initial_input

        for i, step in enumerate(self._steps):
            if on_step_start:
                on_step_start(i, step)

            log.info("Chain step %d/%d: model=%s, label=%s",
                     i + 1, len(self._steps), step.model, step.label)

            # Build the user prompt from template
            user_text = step.user_template.replace("{input}", current_input)

            # Run inference
            artifact = self._run_step(i, step, user_text, on_token)
            artifacts.append(artifact)

            if on_step_complete:
                on_step_complete(artifact)

            # Forward output to next step
            current_input = artifact.output_text

        log.info("Chain complete: %d steps, %d total tokens",
                 len(artifacts), sum(a.token_count for a in artifacts))
        return artifacts

    def _run_step(
        self,
        index: int,
        step: ChainStep,
        user_text: str,
        on_token: Callable[[int, str], None] | None = None,
    ) -> ChainArtifact:
        """Execute a single chain step via Ollama."""
        messages = []
        if step.system_prompt:
            messages.append({"role": "system", "content": step.system_prompt})
        messages.append({"role": "user", "content": user_text})

        url = f"{self._base_url}/api/chat"
        payload = json.dumps({
            "model": step.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": step.temperature,
                "num_ctx": step.num_ctx,
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            url, data=payload, method="POST",
            headers={"Content-Type": "application/json"},
        )

        tokens: list[str] = []
        eval_count = 0
        duration_ms = 0.0

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8").strip()
                    if not line:
                        continue
                    chunk = json.loads(line)
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        tokens.append(token)
                        if on_token:
                            on_token(index, token)
                    if chunk.get("done"):
                        eval_count = chunk.get("eval_count", 0)
                        duration_ms = chunk.get("total_duration", 0) / 1_000_000
        except Exception as e:
            log.error("Chain step %d failed: %s", index, e)
            return ChainArtifact(
                step_index=index, model=step.model, label=step.label,
                input_text=user_text, output_text=f"[ERROR: {e}]",
                token_count=0, duration_ms=0,
                metadata={"error": str(e)},
            )

        output = "".join(tokens)
        return ChainArtifact(
            step_index=index,
            model=step.model,
            label=step.label,
            input_text=user_text,
            output_text=output,
            token_count=eval_count,
            duration_ms=round(duration_ms, 1),
        )

    def to_config(self) -> list[dict[str, Any]]:
        """Export chain as a serializable config (for saving/loading)."""
        return [
            {
                "model": s.model,
                "system": s.system_prompt,
                "user_template": s.user_template,
                "temperature": s.temperature,
                "num_ctx": s.num_ctx,
                "label": s.label,
            }
            for s in self._steps
        ]

    @classmethod
    def from_config(cls, config: list[dict], base_url: str = "http://localhost:11434") -> "ModelChain":
        """Load a chain from a saved config."""
        chain = cls(base_url=base_url)
        for step_cfg in config:
            chain.add_step(
                model=step_cfg["model"],
                system=step_cfg.get("system", ""),
                user=step_cfg.get("user_template", "{input}"),
                temperature=step_cfg.get("temperature", 0.7),
                num_ctx=step_cfg.get("num_ctx", 8192),
                label=step_cfg.get("label", ""),
            )
        return chain
