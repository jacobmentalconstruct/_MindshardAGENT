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
from src.core.agent.model_roles import PLANNER_ROLE, resolve_model_for_role
from src.core.config.app_config import AppConfig
from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.runtime_logger import get_logger

log = get_logger("thought_chain")

DEFAULT_DEPTH = 3
MAX_DEPTH = 5

# ── System prompts for each spiral round ─────────────────

_SYSTEM_ROUND_1 = """You are a planning assistant for a software engineering workspace. The user has a goal.
Your job in THIS round: brainstorm the approach.

Rules:
- Assume this is a software/codebase planning task unless the user explicitly says it is about a physical system.
- List the major components or steps needed
- Identify what you don't know yet or need to figure out
- Think about dependencies — what must happen first?
- Be concise. Bullet points preferred.
- Do NOT write any code. Just plan."""

_SYSTEM_ROUND_MID = """You are a planning assistant refining a software project plan.
Below is your previous analysis. Your job in THIS round: GET MORE SPECIFIC.

Rules:
- Stay grounded in the attached software/codebase context unless the user explicitly says otherwise
- You MUST be more concrete than your previous output
- You MUST NOT repeat what was already said — only ADD new detail
- Break vague items into exact sub-steps
- Name specific files, functions, classes, or patterns where possible
- Estimate relative complexity (trivial / small / medium) per item
- Do NOT write any code. Just plan."""

_SYSTEM_ROUND_FINAL = """You are a planning assistant producing a FINAL software task list.
Below is your refined analysis. Your job: produce a numbered task list.

Rules:
- Stay grounded in the attached software/codebase context unless the user explicitly says otherwise
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
        self._stop_requested = False
        self._worker_thread: threading.Thread | None = None

    def run(
        self,
        goal: str,
        goal_context: str = "",
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
        self._stop_requested = False

        def _worker():
            try:
                self._run_sync(goal, goal_context, depth, on_round, on_complete, on_error)
            except Exception as e:
                log.exception("Thought chain error")
                if on_error:
                    on_error(str(e))

        thread = threading.Thread(target=_worker, daemon=True, name="thought-chain")
        self._worker_thread = thread
        thread.start()

    def join(self, timeout: float = 3.0) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)

    def request_stop(self) -> None:
        self._stop_requested = True

    def _run_sync(self, goal, goal_context, depth, on_round, on_complete, on_error):
        model = resolve_model_for_role(self._config, PLANNER_ROLE)
        if not model:
            if on_error:
                on_error("No planner model selected")
            return

        self._activity.info("ctc", f"Starting thought chain: {depth} rounds with planner {model}")
        rounds_output: list[str] = []
        round_stats: list[dict[str, Any]] = []
        stopped = False
        stopped_reason = ""
        planning_num_ctx = min(self._config.max_context_tokens, 4096)

        for round_num in range(1, depth + 1):
            if self._stop_requested:
                stopped = True
                stopped_reason = "stopped"
                break
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
                context_bits = []
                if goal_context:
                    context_bits.append(goal_context.strip())
                context_bits.append(f"Goal: {goal}")
                messages.append({
                    "role": "user",
                    "content": "\n\n".join(bit for bit in context_bits if bit),
                })
            else:
                # Feed previous round's output as context
                prev = rounds_output[-1]
                messages.append({
                    "role": "user",
                    "content": (
                        f"Original goal: {goal}\n\n"
                        f"Software project context:\n{goal_context.strip() or '(no extra context provided)'}\n\n"
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
                should_stop=lambda: self._stop_requested,
                temperature=self._config.temperature,
                num_ctx=planning_num_ctx,
                timeout=max(30, int(self._config.planning_round_timeout_sec or 150)),
                read_idle_timeout=max(1.0, float(self._config.planning_stream_idle_timeout_sec or 5.0)),
                heartbeat_sec=max(1.0, float(self._config.planning_heartbeat_sec or 10.0)),
                first_token_warn_sec=max(1.0, float(self._config.planning_first_token_warn_sec or 20.0)),
                max_output_chars=max(400, int(self._config.planning_max_output_chars or 2200)),
                progress_label=f"ctc_round_{round_num}_of_{depth}",
            )

            text = result.get("content", "")
            rounds_output.append(text)
            round_stats.append(
                {
                    "round_num": round_num,
                    "wall_ms": float(result.get("wall_ms", 0.0) or 0.0),
                    "chars": len(text),
                    "tokens_out": int(result.get("eval_count", 0) or 0),
                    "tokens_in": int(result.get("prompt_eval_count", 0) or 0),
                    "first_token_ms": float(result.get("first_token_ms", 0.0) or 0.0),
                    "done_reason": str(result.get("done_reason", "") or ""),
                    "stopped": bool(result.get("stopped", False)),
                    "timed_out": bool(result.get("timed_out", False)),
                    "output_capped": bool(result.get("output_capped", False)),
                }
            )

            if result.get("stopped"):
                stopped = True
                stopped_reason = str(result.get("done_reason", "") or "stopped")
                self._activity.info("ctc", f"Thought chain stopped during round {round_num}/{depth}")
                break

            self._activity.info("ctc",
                f"Round {round_num}/{depth} complete ({len(text)} chars)")

            if on_round:
                on_round(round_num, text)

        # Parse tasks from the final round
        final_text = rounds_output[-1] if rounds_output else ""
        tasks = parse_task_list(final_text) if final_text and not stopped else []

        self._activity.info("ctc",
            f"Thought chain complete: {len(tasks)} tasks extracted")

        if on_complete:
            on_complete({
                "goal": goal,
                "rounds": rounds_output,
                "tasks": tasks,
                "final_text": final_text,
                "depth": depth,
                "model": model,
                "stopped": stopped,
                "stopped_reason": stopped_reason,
                "completed_rounds": len(rounds_output),
                "round_stats": round_stats,
                "tokens_out_total": sum(stat["tokens_out"] for stat in round_stats),
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
