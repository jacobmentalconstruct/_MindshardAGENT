"""Probe stage — runs micro-questions via FAST_PROBE model.

Each probe is a single text-in/text-out inference call. No tool calling
required — the small model just answers a focused question given
pre-gathered workspace context.
"""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from src.core.agent.model_roles import FAST_PROBE_ROLE, resolve_model_for_role
from src.core.agent.probe_decision import PROBE_SYSTEM, select_probes, should_probe
from src.core.config.app_config import AppConfig
from src.core.agent.context_gatherer import GatheredContext
from src.core.ollama.ollama_client import chat_stream
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.runtime_logger import get_logger

log = get_logger("probe_stage")


@dataclass(frozen=True)
class ProbeResult:
    """Result of a single probe question."""

    probe_type: str
    question: str
    answer: str
    model: str
    tokens_out: int
    wall_ms: float


@dataclass(frozen=True)
class ProbeStageResult:
    """Combined result of all probes in a stage."""

    probes: list[ProbeResult] = field(default_factory=list)
    total_wall_ms: float = 0.0


def run_probe_stage(
    config: AppConfig,
    activity: ActivityStream,
    user_text: str,
    gathered: GatheredContext | None,
) -> ProbeStageResult | None:
    """Run the probe stage if conditions are met.

    Returns None if probing is skipped or fails entirely.
    Individual probe failures are silently dropped.
    """
    if not should_probe(config, user_text, gathered):
        return None

    max_probes = getattr(config, "probe_max_questions", 3)
    probe_specs = select_probes(user_text, gathered, max_probes=max_probes)

    if not probe_specs:
        return None

    model_name = resolve_model_for_role(config, FAST_PROBE_ROLE)
    if not model_name:
        return None

    activity.info("probe", f"Probe stage: {len(probe_specs)} probes with {model_name}")
    t0 = time.perf_counter()

    results: list[ProbeResult] = []

    # Run probes in parallel (Ollama handles concurrent requests)
    with ThreadPoolExecutor(max_workers=min(len(probe_specs), 3), thread_name_prefix="probe") as pool:
        futures = {
            pool.submit(_run_single_probe, config, model_name, spec): spec
            for spec in probe_specs
        }
        for future in as_completed(futures):
            spec = futures[future]
            try:
                result = future.result()
                if result is not None:
                    results.append(result)
            except Exception as exc:
                log.warning("Probe '%s' failed: %s", spec.get("type", "?"), exc)

    total_ms = (time.perf_counter() - t0) * 1000

    activity.info(
        "probe",
        f"Probe stage complete: {len(results)}/{len(probe_specs)} probes, "
        f"{total_ms:.0f}ms total"
    )

    return ProbeStageResult(probes=results, total_wall_ms=round(total_ms, 1))


def _run_single_probe(
    config: AppConfig,
    model_name: str,
    spec: dict,
) -> ProbeResult | None:
    """Run a single probe question against the FAST_PROBE model."""
    question = spec["question"]
    probe_type = spec.get("type", "unknown")

    # Build minimal messages — system + user question
    messages = [
        {"role": "system", "content": PROBE_SYSTEM},
        {"role": "user", "content": question},
    ]

    try:
        result = chat_stream(
            base_url=config.ollama_base_url,
            model=model_name,
            messages=messages,
            temperature=0.1,  # Low temp for factual probes
            num_ctx=min(getattr(config, "max_context_tokens", 4096), 2048),
        )

        answer = _sanitize_probe_answer(result.get("content", ""))
        tokens_out = int(result.get("eval_count", 0) or 0)
        wall_ms = float(result.get("wall_ms", 0.0) or 0.0)

        log.info(
            "Probe '%s': %d tokens, %.0fms, answer=%s",
            probe_type, tokens_out, wall_ms, answer[:80],
        )

        return ProbeResult(
            probe_type=probe_type,
            question=_short_question(question),
            answer=answer,
            model=model_name,
            tokens_out=tokens_out,
            wall_ms=round(wall_ms, 1),
        )

    except Exception as exc:
        log.warning("Probe '%s' inference failed: %s", probe_type, exc)
        return None


def _sanitize_probe_answer(text: str) -> str:
    """Clean up probe model output."""
    cleaned = (text or "").strip()
    # Strip thinking tags (qwen, deepseek)
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL | re.IGNORECASE).strip()
    if "</think>" in cleaned:
        cleaned = cleaned.split("</think>")[-1].strip()
    # Cap length — probes should be short
    if len(cleaned) > 500:
        cleaned = cleaned[:500].rsplit(" ", 1)[0] + "..."
    return cleaned


def _short_question(question: str) -> str:
    """Produce a short label from the full probe question."""
    # Take just the first line, capped
    first_line = question.split("\n")[0].strip()
    if len(first_line) > 80:
        return first_line[:77] + "..."
    return first_line
