# Engineering Notes — MindshardAGENT

Hard-won lessons, design rationale, and gotchas for anyone working on this codebase.
Updated as discoveries are made. Treat this as the "why" companion to ARCHITECTURE.md.

---

## 1. Small Model Prompt Engineering

### 1.1 The Fundamental Problem

Models in the 2B-4B parameter range follow instructions inconsistently. They are
heavily biased toward patterns they saw most frequently in training data. If a
system prompt teaches echo-based file creation alongside a write_file tool, the
model will reach for echo almost every time — because echo appears in millions of
training examples and write_file appears in zero.

### 1.2 What Works

**Repetition at multiple levels.** The same directive must appear in:
1. The tool selection table (structured decision aid)
2. Explicit NEVER/ALWAYS rules (capitalized, unambiguous)
3. Every example (few-shot demonstrations)
4. The OS knowledge module (reinforcing at the "teaching" level)

A single mention of "prefer write_file" is invisible to a 4B model. Four
redundant mentions across different sections creates a signal strong enough to
override training priors.

**Decision tables over prose.** Small models parse structured tables more
reliably than paragraphs. The tool selection table in prompt_builder.py uses:
```
| Task                | Correct Tool     | WRONG (never do this)       |
|---------------------|------------------|-----------------------------|
| Create/write a file | write_file       | ~~echo ... > file~~         |
| Read a file         | read_file        | ~~type file~~ ~~cat file~~  |
```
This format gives the model a lookup structure instead of requiring it to infer
intent from natural language.

**Anti-patterns with strikethrough.** Showing `~~echo ... > file~~` as "wrong"
leverages the model's understanding of markdown strikethrough as negation. More
effective than "do not use echo" in prose.

**Few-shot examples that match real use cases.** The write_file example in the
system prompt creates a tkinter app — because that's a common first task users
request. When the model sees a user ask for a tkinter app and finds a write_file
example creating a tkinter app in its system prompt, it mirrors the pattern.

**Short, imperative sentences.** "NEVER use echo to create files." beats
"It is recommended to avoid using echo commands for file creation purposes."

### 1.3 What Fails

- Polite suggestions ("PREFERRED", "consider using")
- Long paragraphs of rules (buried signal)
- Teaching a pattern then banning it (the OS knowledge module originally showed
  `echo content > file` as a task pattern, then the tool section said "don't
  use echo" — the model followed the demonstrated pattern, not the prohibition)
- Expecting the model to read a table of tools and infer which to use without
  explicit routing rules

### 1.4 The Self-Contradicting Prompt Bug

The most insidious bug found so far: `os_knowledge.py` contained example
patterns like:

```
**Create a new file with content:**
echo Hello, this is my file content > newfile.txt

**Write a Python script and run it:**
echo print("Hello from Python!") > hello.py
python hello.py
```

While `prompt_builder.py` simultaneously said "Use write_file to create files."

The model saw both signals, but the OS knowledge section came first in the prompt
and contained concrete executable examples. The tool section came later with an
abstract directive. The model followed the concrete examples every time.

**Fix:** OS knowledge now references tools by name ("Use the write_file tool")
instead of showing shell-based file creation patterns. The teaching and the
tooling must agree on the same approach.

### 1.5 Prompt Token Budget

The full system prompt with OS knowledge, tool definitions, command reference,
and examples runs ~1500-2000 tokens. On an 8K context window, that leaves ~6K
for conversation history and model output. This is tight but workable.

If the system prompt grows beyond ~2500 tokens, consider:
- Trimming the command reference to only frequently-used commands
- Making the OS knowledge section conditional (skip for larger models that
  already know this)
- Moving examples to a separate "examples" message at position 2 in the
  conversation

---

## 2. Tool Architecture

### 2.1 Tool Dispatch Pattern

All tools follow the same lifecycle:
```
Model output → ToolRouter.extract_tool_calls() → ToolRouter.execute()
    → Handler (CLIRunner / FileWriter / future tools)
    → Result dict → TranscriptFormatter → Re-injection as "user" message
```

Adding a new tool requires exactly four changes:
1. Define a `ToolEntry` in `tool_catalog.py`
2. Register it in `ToolCatalog.__init__()`
3. Add an `if tool_name == "xyz":` block in `tool_router.py`
4. Add formatting in `transcript_formatter.py` (optional — defaults to CLI format)

The handler itself can be a new module or an existing one (FileWriter handles
both `write_file` and `read_file`).

### 2.2 Result Shape Convention

All tool handlers return a dict, but the shape varies by tool type:

**CLI tools:** `{command, cwd, stdout, stderr, exit_code, started_at, finished_at}`
**File tools:** `{path, success, bytes_written/content/size, error}`

The transcript formatter dispatches on `tool_name` to format each shape
appropriately. New tools should document their result shape and add a formatter
branch.

### 2.3 The write_file Newline Encoding

When the model emits a write_file tool call in JSON, newlines in content must
be encoded as literal `\n` in the JSON string. The JSON parser converts these
to real newlines. The file_writer then writes with `newline="\n"` to prevent
Windows from doubling line endings (\r\n\r\n).

This is the key insight: the model only needs to produce valid JSON with `\n`
escape sequences. No shell quoting, no echo piping, no heredocs. JSON handles
the encoding; Python handles the decoding; file_writer handles the writing.

### 2.4 Security Layers for File Tools

FileWriter enforces:
- **PathGuard containment** — same sandbox boundary as CLI
- **Extension blocklist** — .exe, .bat, .cmd, .ps1, .vbs, .wsf, .msi, .scr, .com
- **Size limits** — 512KB write, 1MB read
- **Audit logging** — every operation recorded in audit.jsonl
- **Auto-mkdir** — parent directories created automatically (within sandbox)

These are defense-in-depth. Even in a Docker container, these limits prevent the
model from doing something expensive (writing a 500MB file) or confusing (creating
a .bat that gets auto-executed by Windows).

---

## 3. Windows-Specific Gotchas

### 3.1 cmd.exe Quoting is Hostile

Windows cmd.exe does not support:
- Single-quoted strings (`echo 'hello'` outputs the quotes literally)
- Multi-line echo without `^` continuation (fragile, model never gets it right)
- Heredocs of any kind
- `cat` (not a command — use `type` instead)
- `python3` (Windows uses `python` or `py`)

The solution is to avoid cmd.exe for file creation entirely. The write_file tool
was created specifically because small models cannot reliably construct
Windows-compatible multi-line file creation commands.

### 3.2 Path Separators

Windows uses `\` but Python's pathlib handles `/` transparently. The sandbox
code uses pathlib throughout, so path separators are not a practical issue
internally. However, the model may emit either `\` or `/` in paths — PathGuard
resolves both correctly.

### 3.3 Subprocess Environment

`cli_runner.py` uses `subprocess.run(shell=True)` which invokes cmd.exe on
Windows. The `env=None` parameter inherits the parent process environment.
This means the model has access to the same Python installation as the host.

In Docker, this is fine (contained). On bare metal, the command policy
allowlist is the primary defense. The allowlist permits `python` and `py` but
blocks `pip`, `npm`, `curl`, `wget`, and other package/network tools.

### 3.4 python vs python3

The command policy allowlist includes `python` and `py` but NOT `python3`.
On Windows, `python3` is not a standard command. Models trained on Linux
examples frequently try `python3` — this gets blocked. The OS knowledge module
explicitly teaches `python myscript.py` as the correct invocation.

---

## 4. RAG System

### 4.1 Architecture

Session-scoped retrieval-augmented generation using Ollama's all-minilm model:
```
User query → embed_text() → 384-dim vector
  → KnowledgeStore.query() → cosine similarity over session chunks
  → Top-K results → injected into system prompt as "## Relevant Context"
```

After each exchange, both user and assistant messages are chunked and embedded
into the knowledge store for future retrieval.

### 4.2 Embedding Storage

Embeddings are stored as compact binary BLOBs in SQLite using struct.pack
(float32 × 384 = 1536 bytes per vector). This is ~10x more space-efficient than
storing as JSON arrays and enables fast bulk retrieval.

### 4.3 Retrieval is Brute-Force

Current implementation loads all session vectors and computes cosine similarity
in Python. This is fine for sessions with hundreds of chunks. For sessions with
thousands of chunks, consider adding an approximate nearest neighbor index
(faiss-cpu is a natural fit but adds a dependency).

### 4.4 Chunk Splitting

`chunk_text()` splits at sentence boundaries with configurable overlap.
Default: max 512 chars per chunk with 64-char overlap. This ensures semantic
units aren't split mid-sentence while keeping chunks small enough for accurate
embedding.

### 4.5 Embedding Model Availability

The system checks for `all-minilm:latest` availability on startup (background
thread, 1.5s delay). If the model isn't pulled, RAG is silently disabled. The
activity stream shows "Embedding model not available — RAG disabled" so the
user knows.

To enable: `ollama pull all-minilm`

---

## 5. Response Loop Mechanics

### 5.1 Multi-Round Tool Execution

The response loop supports up to MAX_TOOL_ROUNDS (5) consecutive tool calls per
user turn. Each round:
1. Model generates response (streaming)
2. Router checks for `\`\`\`tool_call` blocks
3. If found: execute, format result, append to messages as `[Tool Results]`
4. Loop back to step 1
5. If no tool calls: break, return final response

Tool results are injected as "user" messages with `[Tool Results]` prefix. This
is a pragmatic choice — Ollama's API only supports "system", "user", and
"assistant" roles. A dedicated "tool" role would be cleaner but isn't available.

### 5.2 Streaming Token Delivery

Tokens stream from Ollama → background thread → on_token callback → UI update.
The UI uses `root.after()` for thread-safe Tkinter updates. The
`ChatMessageCard.update_streaming_content()` method replaces the card text and
recalculates height on each update.

### 5.3 History Management

The engine maintains `_chat_history` as a flat list of role/content dicts. After
the response loop completes, it appends the user message and final assistant
response. Tool round-trip intermediate messages (assistant tool calls + tool
results) are NOT stored in history — only the final response is.

This means if the model took 3 tool rounds, the history only shows the final
assistant response. The intermediate steps are visible in the activity stream
and audit log but don't consume history context.

---

## 6. Testing Strategy

### 6.1 Headless Test Suite

`tests/test_tool_roundtrip.py` runs without Ollama or a GUI. It tests:
- Tool call parsing (valid, malformed, multiple, unknown)
- CLI execution (echo, dir, blocked commands)
- File operations (write, read, append, path escape, blocked extensions, nested dirs)
- Router dispatch for all tool types
- Transcript formatting for all result shapes
- Prompt builder output verification

Run with: `python -m tests.test_tool_roundtrip`

### 6.2 Live Model Tests

With `--live` flag, the test suite sends an actual prompt to a running Ollama
model and verifies the full round-trip: prompt → model → tool call → execution →
result formatting. Default model: qwen3.5:2b (smallest capable model).

Run with: `python -m tests.test_tool_roundtrip --live`

### 6.3 What To Test After Changes

- **Changed prompt_builder.py?** Run test 4 + test 8.
- **Changed tool_router.py?** Run tests 1, 5, 7.
- **Changed file_writer.py?** Run test 6.
- **Changed transcript_formatter.py?** Run test 3 + test 7.
- **Changed os_knowledge.py?** Grep the output of test 4 for contradictions.
- **Any change?** Run the full suite: `python -m tests.test_tool_roundtrip`

---

## 7. Model Capability Observations

### 7.1 qwen3.5:2b
- Can follow tool call JSON format reliably
- Struggles with complex multi-step reasoning
- Good for simple file creation + run tasks
- Tends to use `echo` if not aggressively steered away

### 7.2 qwen3.5:4b
- Better reasoning than 2b but still follows training priors over system prompt
- Tries creative workarounds when a command fails (python -c, cat) — but the
  workarounds are often wrong for Windows
- Needs the same aggressive tool steering as 2b
- Occasionally hallucinates methods that don't exist (e.g., `root.center()` in tkinter)

### 7.3 General Observations for Small Models
- They do NOT reliably read decision tables on first attempt — repetition helps
- They echo back system prompt instructions in their "thinking" text, which wastes
  tokens but confirms they're processing the instructions
- They are better at structured JSON output than free-form tool invocation
- Temperature 0.3 gives more predictable tool use than default 0.7
- The model frequently wraps tool calls in ```python fences before the actual
  ```tool_call fence — this is harmless (the regex only matches tool_call) but
  worth knowing

---

## 8. Containment Architecture

### 8.1 Current (v1): Allowlist + PathGuard

```
User prompt → Model → Tool call → CommandPolicy (allowlist) → PathGuard → subprocess
                                    ↓ blocked              ↓ escape
                                    Error returned         Error returned
```

Defense layers:
1. **CommandPolicy** — 36 allowlisted commands, blocklist, escape pattern detection
2. **PathGuard** — all paths must resolve within sandbox root
3. **FileWriter** — extension blocklist, size limits
4. **AuditLog** — every operation recorded

### 8.2 Future (v2): Docker Container

Docker containerization eliminates the need for fine-grained allowlists. The
container IS the sandbox:
- Open up command allowlist (pip, curl, npm become safe)
- No path escape possible (container filesystem is the boundary)
- Network policy at container level (instead of blocking curl)
- Resource limits via Docker (CPU, memory, disk)
- Disposable — nuke and recreate per session if needed

Docker setup notes:
- Mount the sandbox directory as a volume
- Use a Python base image with common packages pre-installed
- Expose Ollama via network (host.docker.internal or network bridge)
- Consider GPU passthrough if the model runs inside the container (unlikely —
  Ollama runs on host)

### 8.3 Audit Trail

`_sandbox/_logs/audit.jsonl` records every operation:
```json
{"ts": "2026-03-17T...", "command": "write_file hello.py", "cwd": "...",
 "outcome": "executed", "exit_code": 0, "duration_ms": 2.1}
```

Outcomes: "executed", "blocked", "cancelled", "error", "timeout"

Both CLI commands and file operations are audited through the same log.
The audit log is append-only and should never be truncated during a session.

---

## 9. Common Failure Modes

### 9.1 Model Uses Wrong Tool
**Symptom:** Model uses `echo` or `type` instead of write_file/read_file.
**Cause:** System prompt steering insufficient, or OS knowledge contradicts tool instructions.
**Fix:** Check os_knowledge.py for echo/type examples. Verify prompt_builder.py has the decision table and NEVER/ALWAYS rules.

### 9.2 File Created But Content is Garbled
**Symptom:** File contains literal `\n` strings instead of newlines.
**Cause:** Model emitted `\\n` (escaped backslash + n) instead of `\n` in JSON.
**Fix:** This is a model quality issue. The JSON parser handles `\n` → newline automatically, but `\\n` → literal backslash-n. The system prompt teaches `\\n` for the JSON context which is correct.

### 9.3 Tool Call Not Detected
**Symptom:** Model output contains what looks like a tool call but the router doesn't pick it up.
**Cause:** The regex expects exactly `\`\`\`tool_call\n...\n\`\`\`` with newlines. If the model puts extra whitespace, uses a different fence name, or doesn't close the block, the regex won't match.
**Fix:** Check the raw model output. Common issues: model writes `\`\`\`json` instead of `\`\`\`tool_call`, or doesn't close the code fence.

### 9.4 Path Escape False Positive
**Symptom:** PathGuard blocks a path that should be inside the sandbox.
**Cause:** Symlinks or junction points resolving outside sandbox root.
**Fix:** PathGuard uses `.resolve()` which follows symlinks. If the sandbox root itself is a symlink, the guard compares against the resolved root. Both must be on the same real path.

### 9.5 Command Blocked Unexpectedly
**Symptom:** A command the model should be able to run gets blocked.
**Cause:** CommandPolicy extracts the first word as the "command" and checks the allowlist. Complex commands with paths or arguments sometimes confuse the extraction.
**Fix:** Check `command_policy.py`'s `_extract_command()` method. It strips quotes and takes the basename of the first token.

---

## 10. Performance Notes

### 10.1 Tokenizer Accuracy
The adaptive tokenizer learns per-model chars-per-token ratios from actual
Ollama response metadata using exponential moving average. Default heuristic
is 4.0 chars/token until enough samples arrive. The ratio varies significantly:
code-heavy output ~3.5, natural language ~4.2, JSON ~3.0.

### 10.2 Streaming Resize Cost
`update_streaming_content()` recalculates card height on every token. For long
responses (1000+ tokens), this can cause UI lag. If this becomes an issue,
consider updating height only every N tokens or on a timer.

### 10.3 RAG Embedding Latency
Each chat turn triggers 2-4 embedding calls (query embedding + storage of user +
assistant chunks). Each call takes ~50-200ms with all-minilm. Total RAG overhead
per turn: ~200-800ms. Not noticeable with model inference times of 5-30 seconds.

---

## 11. Dependency Notes

### 11.1 Stdlib-Only Core
The core engine, sandbox, and agent modules use only Python stdlib. This is
intentional — minimizes supply chain risk and keeps the install simple.

- `urllib` for Ollama HTTP calls
- `sqlite3` for session/knowledge persistence
- `subprocess` for CLI execution
- `struct` for embedding binary packing
- `json` for config persistence and tool call parsing
- `threading` for background work
- `tkinter` for GUI

### 11.2 Optional Dependencies
- `psutil` — resource monitor (CPU/RAM). Falls back gracefully if missing.
- `nvidia-smi` — GPU VRAM stats (called via subprocess, not a Python package).

### 11.3 External Requirements
- **Ollama** running at localhost:11434 with at least one chat model pulled
- **all-minilm:latest** pulled in Ollama for RAG (optional, degrades gracefully)
- **Python 3.10+** (uses match/case, union types, dataclass features)
- **Windows 10/11** (path handling and cmd.exe assumptions are Windows-specific)
