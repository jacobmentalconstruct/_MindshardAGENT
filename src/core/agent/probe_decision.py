"""Probe stage decision heuristics — pure logic, no I/O.

Determines whether probes should run and which probe types to select
based on the user's request and gathered workspace context.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.agent.context_gatherer import GatheredContext
    from src.core.config.app_config import AppConfig

# Probe type constants
INTENT_PROBE = "intent"
RELEVANCE_PROBE = "relevance"
LANGUAGE_PROBE = "language"
SUMMARY_PROBE = "summary"

# System prompt for all probes — kept tiny (~80 tokens)
PROBE_SYSTEM = (
    "You are a fast analysis assistant. "
    "Answer concisely in 1-3 sentences. "
    "No code blocks, no tool calls, no markdown headers. "
    "Just answer the question directly."
)

# Probe templates: {question_template, max_tokens}
PROBE_SPECS = {
    INTENT_PROBE: {
        "question": "Classify this user request into exactly one category: CREATE (new files/project), MODIFY (change existing code), UNDERSTAND (explain/explore), or DEBUG (fix a problem). Request: \"{user_text}\"\nAnswer with just the category and a one-sentence reason.",
        "max_tokens": 60,
    },
    RELEVANCE_PROBE: {
        "question": "Given this file listing:\n{file_tree}\n\nWhich 3-5 files are most relevant to this request: \"{user_text}\"?\nList just the file paths, one per line.",
        "max_tokens": 120,
    },
    LANGUAGE_PROBE: {
        "question": "Given this file listing:\n{file_tree}\n\nWhat is the primary programming language and framework (if any) for this project? Answer in one line.",
        "max_tokens": 40,
    },
    SUMMARY_PROBE: {
        "question": "Given this file listing and any available context:\n{file_tree}\n\nIn one sentence, what does this project do?",
        "max_tokens": 60,
    },
}


def should_probe(
    config: AppConfig,
    user_text: str,
    gathered: GatheredContext | None,
) -> bool:
    """Decide whether to run the probe stage.

    Returns False when probing would add no value:
    - Probing is disabled in config
    - FAST_PROBE model is the same as PRIMARY_CHAT (no speed benefit)
    - Request is trivial (greeting, very short)
    - No workspace context was gathered (nothing to probe against)
    """
    if not getattr(config, "probe_enabled", True):
        return False

    # No distinct fast model configured — probing adds latency with no benefit
    fast_model = getattr(config, "fast_probe_model", "") or ""
    primary_model = config.primary_chat_model or ""
    if not fast_model or fast_model == primary_model:
        return False

    text = (user_text or "").strip()

    # Too short to be a real request
    if len(text) < 15:
        return False

    # No workspace context to probe against
    if gathered is None or not gathered.file_tree:
        return False

    return True


def select_probes(
    user_text: str,
    gathered: GatheredContext | None,
    max_probes: int = 3,
) -> list[dict]:
    """Select which probes to run based on the request and context.

    Returns a list of probe specs: [{type, question, max_tokens}]
    """
    probes: list[dict] = []
    text = (user_text or "").strip()
    has_tree = gathered is not None and bool(gathered.file_tree)
    has_brief = gathered is not None and bool(gathered.project_brief)

    # Always run intent classification — it's cheap and universally useful
    probes.append(_make_probe(INTENT_PROBE, text, gathered))

    # Run relevance probe if we have a file tree and the request involves files
    if has_tree and len(probes) < max_probes:
        probes.append(_make_probe(RELEVANCE_PROBE, text, gathered))

    # Run language probe if we have a tree but no project brief
    if has_tree and not has_brief and len(probes) < max_probes:
        probes.append(_make_probe(LANGUAGE_PROBE, text, gathered))

    # Run summary probe only if no project brief exists
    if has_tree and not has_brief and len(probes) < max_probes:
        probes.append(_make_probe(SUMMARY_PROBE, text, gathered))

    return probes[:max_probes]


def _make_probe(
    probe_type: str,
    user_text: str,
    gathered: GatheredContext | None,
) -> dict:
    """Build a concrete probe spec from a template."""
    spec = PROBE_SPECS[probe_type]
    file_tree = gathered.file_tree if gathered else "(no file listing available)"

    question = spec["question"].format(
        user_text=user_text,
        file_tree=file_tree,
    )

    return {
        "type": probe_type,
        "question": question,
        "max_tokens": spec["max_tokens"],
    }
