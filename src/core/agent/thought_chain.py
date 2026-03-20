"""Cannibalistic Thought Chain (CTC) — self-talk spiral to task decomposition.

The agent receives a high-level goal, then talks to itself in a loop.
Each response feeds back as input, spiraling from vague intent into
concrete, actionable task steps.

Flow:
  1. User provides a goal (e.g., "build a calculator app")
  2. Round 1: Agent brainstorms approach, identifies unknowns
  3. Round 2: Agent consumes round 1 output, gets more specific
  4. Round 3: Agent consumes round 2, produces concrete steps
  5. Final: Parser extracts structured task list from last output

The key constraint for small models: each round's prompt DEMANDS
more specificity than the previous round. No repetition allowed.
"""

import threading
from typing import Any, Callable

from src.core.ollama.ollama_client import chat_stream
from src.core.config.app_config import AppConfig
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.runtime_logger import get_logger

log = get_logger("thought_chain")

DEFAULT_DEPTH = 3
MAX_DEPTH = 5

# ── System prompts for each spiral round ─────────────────

_SYSTEM_ROUND_1 = """You are a planning assistant. The user has a goal.
Your job in THIS round: brainstorm the approach.

Rules:
- List the major components or steps needed
- Identify what you don't know yet or need to figure out
- Think about dependencies — what must happen first?
- Be concise. Bullet points preferred.
- Do NOT write any code. Just plan."""

_SYSTEM_ROUND_MID = """You are a planning assistant refining a plan.
Below is your previous analysis. Your job in THIS round: GET MORE SPECIFIC.

Rules:
- You MUST be more concrete than your previous output
- You MUST NOT repeat what was already said — only ADD new detail
- Break vague items into exact sub-steps
- Name specific files, functions, classes, or patterns where possible
- Estimate relative complexity (trivial / small / medium) per item
- Do NOT write any code. Just plan."""

_SYSTEM_ROUND_FINAL = """You are a planning assistant producing a FINAL task list.
Below is your refined analysis. Your job: produce a numbered task list.

Rules:
- Output a NUMBERED list of concrete, actionable tasks
- Each task must be completable in one sitting
- Each task must start with a verb (Create, Add, Wire, Fix, Test, etc.)
- Include file paths where relevant
- Order tasks by dependency — first things first
- Mark each task's complexity: [trivial] [small] [medium]
- Format: "1. [small] Create src/utils/parser.py with parse_input() function"
- Do NOT write any code. Just list the tasks."""


class ThoughtChain:
    """Runs a CTC spiral: self-talk loop that decomposes a goal into tasks."""

    def __init__(self, config: AppConfig, activity: ActivityStream):
        self._config = config
        self._activity = activity

    def run(
        self,
        goal: str,
        depth: int = DEFAULT_DEPTH,
        on_round: Callable[[int, str], None] | None = None,
        on_complete: Callable[[dict[str, Any]], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        """Run a thought chain in a background thread.

        Args:
            goal: The high-level goal to decompose
            depth: Number of spiral rounds (2-5, default 3)
            on_round: Called after each round with (round_num, text)
            on_complete: Called with final result dict
            on_error: Called on failure
        """
        depth = max(2, min(depth, MAX_DEPTH))

        def _worker():
            try:
                self._run_sync(goal, depth, on_round, on_complete, on_error)
            except Exception as e:
                log.exception("Thought chain error")
                if on_error:
                    on_error(str(e))

        threading.Thread(target=_worker, daemon=True, name="thought-chain").start()

    def _run_sync(self, goal, depth, on_round, on_complete, on_error):
        model = self._config.selected_model
        if not model:
            if on_error:
                on_error("No model selected")
            return

        self._activity.info("ctc", f"Starting thought chain: {depth} rounds")
        rounds_output: list[str] = []

        for round_num in range(1, depth + 1):
            # Pick the right system prompt for this round
            if round_num == 1:
                system = _SYSTEM_ROUND_1
            elif round_num == depth:
                system = _SYSTEM_ROUND_FINAL
            else:
                system = _SYSTEM_ROUND_MID

            # Build messages — each round consumes previous output
            messages = [{"role": "system", "content": system}]

            if round_num == 1:
                messages.append({
                    "role": "user",
                    "content": f"Goal: {goal}",
                })
            else:
                # Feed previous round's output as context
                prev = rounds_output[-1]
                messages.append({
                    "role": "user",
                    "content": (
                        f"Original goal: {goal}\n\n"
                        f"Your previous analysis (round {round_num - 1}):\n"
                        f"{prev}\n\n"
                        f"Now go deeper. Be MORE specific than above."
                    ),
                })

            self._activity.info("ctc", f"Round {round_num}/{depth}: thinking...")

            result = chat_stream(
                base_url=self._config.ollama_base_url,
                model=model,
                messages=messages,
                temperature=self._config.temperature,
                num_ctx=self._config.max_context_tokens,
            )

            text = result.get("content", "")
            rounds_output.append(text)

            self._activity.info("ctc",
                f"Round {round_num}/{depth} complete ({len(text)} chars)")

            if on_round:
                on_round(round_num, text)

        # Parse tasks from the final round
        final_text = rounds_output[-1]
        tasks = parse_task_list(final_text)

        self._activity.info("ctc",
            f"Thought chain complete: {len(tasks)} tasks extracted")

        if on_complete:
            on_complete({
                "goal": goal,
                "rounds": rounds_output,
                "tasks": tasks,
                "final_text": final_text,
                "depth": depth,
            })


def parse_task_list(text: str) -> list[dict[str, str]]:
    """Extract numbered tasks from the final CTC round output.

    Looks for lines starting with a number followed by a period or paren.
    Extracts optional complexity tags like [small], [medium], [trivial].

    Returns:
        List of dicts: {"number": "1", "text": "...", "complexity": "small"}
    """
    import re
    tasks = []
    for line in text.split("\n"):
        line = line.strip()
        # Match: "1. [small] Create the thing" or "1) Create the thing"
        m = re.match(r'^(\d+)[.)]\s*(.*)', line)
        if not m:
            continue
        num = m.group(1)
        rest = m.group(2).strip()

        # Extract complexity tag
        complexity = ""
        cm = re.match(r'^\[(\w+)\]\s*(.*)', rest)
        if cm:
            complexity = cm.group(1).lower()
            rest = cm.group(2).strip()

        if rest:
            tasks.append({
                "number": num,
                "text": rest,
                "complexity": complexity,
            })
    return tasks
