# Loop Contract

This document defines the execution contract for all loop modules under
`src/core/agent/`.

## Purpose

Loops are alternate execution modes selected by the loop manager. They may vary
in internal strategy, but they must present a common external contract so the
app, engine, bridge, benchmarks, and history persistence do not need
loop-specific logic.

## Request Contract

Every loop accepts a `LoopRequest` with:

- `user_text`: the current user turn text
- `chat_history`: prior persisted chat messages
- `on_token`: optional token streaming callback
- `on_complete`: required completion callback for successful or stopped runs
- `on_error`: callback for unrecoverable loop failure
- `on_tool_start`: optional callback for tool-call display
- `on_tool_result`: optional callback for rendered tool results
- `mode_hint`: optional explicit loop override

Loops may read only what they need from the request. They must not mutate the
request in place.

## Completion Contract

Successful completion, partial completion, and user-requested stop all report
through `on_complete(result)`. The result payload must contain:

- `content`: assistant-visible final text for the turn
- `metadata`: dict containing, at minimum:
  - `loop_mode`
  - `stopped`
  - `rounds`
- `history_addition`: the persisted history rows for this turn

Optional fields such as `prompt_build` may be included when the loop owns them.

## History Ownership

Loops own their `history_addition` payload. Wrappers that change visible output
must also update `history_addition` to match the final content. Wrappers that do
not change visible output may preserve the wrapped history and only override
metadata such as `loop_mode`.

## Stop Semantics

- `request_stop()` must be idempotent.
- A user stop is not an error.
- When a loop stops after beginning work, it should still complete via
  `on_complete(...)` with `metadata.stopped = True`.
- `on_error(...)` is reserved for actual failure, not cancellation.

## Join Semantics

Loops that spawn or delegate to background work should expose `join(timeout)`
so shutdown can drain cleanly. Wrapper loops that delegate to another joinable
loop should forward `join(timeout)` to the wrapped loop.

## Allowed Side Effects

Loops may:

- emit activity-stream messages
- stream tokens via `on_token`
- trigger tool callbacks when they truly own tool execution
- include loop-specific metadata

Loops may not:

- directly persist session history outside the completion payload
- mutate global selection policy
- silently change another loop's contract
