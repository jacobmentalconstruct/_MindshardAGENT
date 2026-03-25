# Prompt Engineering System — Audit & Integration Strategy

**Date:** 2026-03-25
**Purpose:** Map the current prompt system in full, identify gaps, and define strategies for integrating a proper prompt management and monitoring UI.

---

## 1. How the Current System Works

### 1.1 Source Layer (Files on Disk)

All editable prompt behaviour lives in Markdown files in two locations:

| Location | Role |
|----------|------|
| `_docs/agent_prompt/*.md` | Global prompt docs — ship with the repo, apply to every session |
| `<sandbox_root>/.mindshard/state/prompt_overrides/*.md` | Project-level overrides — same filenames shadow the global docs for a specific project |

Files are loaded in **filename sort order** (alphabetically by number prefix). The current global doc set:

| File | Covers |
|------|--------|
| `00_identity.md` | Who the agent is |
| `10_workspace_semantics.md` | How to interpret workspace state |
| `20_intent_interpretation.md` | How to read user intent |
| `30_file_listing_rules.md` | File exploration protocol |
| `40_response_style.md` | Tone and format rules |
| `50_tool_usage_preferences.md` | Tool selection and call format rules |
| `55_self_architecture.md` | Self-awareness (loaded only when `self_awareness_enabled = True`) |
| `60_project_tidiness.md` | Folder structure and naming conventions |
| `62_sandbox_tool_authoring.md` | How to write and register sandbox tools |
| `90_local_notes.md` | Free-form personal overrides / scratchpad |

Override resolution: if a project override file has the same name as a global doc, it replaces it. Extra override files (names not present globally) are appended after the standard ordered set.

**`PromptSection`** is the atomic unit: `name`, `layer` (`global_doc` or `project_override`), `content`, `source_path`.

---

### 1.2 Builder Layer (Runtime Assembly)

`prompt_builder.py` takes the source sections and **appends runtime-generated blocks** that cannot be stored as files because they depend on live state:

| Section Name | Layer | What It Contains |
|---|---|---|
| `environment` | runtime | Sandbox root, session title, model name, OS, sandbox rules |
| `project_focus` | runtime | Active project root, explore hint |
| `project_brief` | project_meta | Loaded from `.mindshard/state/project_meta.json` |
| `os_knowledge` | runtime | Command allowlist and teaching (from `os_knowledge.py`) |
| `available_tools` | runtime | Full tool catalog with descriptions and parameters |
| `tool_rules` | runtime | The tool selection rules table |
| `tool_creation` | runtime | Sandbox tool authoring instructions |
| `tool_call_examples` | runtime | Worked examples of every tool call type |
| `journal` | runtime | Last 10 workspace events from the action journal |
| `vcs` | runtime | Last 5 git snapshots from `.mindshard/vcs/` |
| `rag` | runtime | Semantically retrieved chunks from current session knowledge store |

**Two build modes exist** selected by model size heuristic (`_is_small_model`):

| Mode | Token Budget | What Gets Dropped |
|------|-------------|-------------------|
| Full (`> 7B`) | ~5,500 tokens | Nothing dropped |
| Compact (`≤ 7B`) | ~1,500 tokens | `os_knowledge`, `tool_creation`, `tool_call_examples`, `journal`, `vcs` — replaced with a single compact block |

The final assembled object is a **`PromptBuildResult`** carrying:
- `prompt` — the complete string sent to the model
- `sections` — ordered tuple of every `PromptSection` that went in
- `source_fingerprint` — SHA-256 of source docs only
- `prompt_fingerprint` — SHA-256 of the final assembled prompt
- `warnings` — any load failures

---

### 1.3 Turn Pipeline Injection

Beyond the system prompt, `turn_pipeline.py` injects **additional messages mid-turn** as the stages run. These are not part of the system prompt — they appear as `{"role": "system"}` messages in the message list at call time:

| Injected When | Content |
|---|---|
| Planner stage completes | `Planner guidance for this turn: <GOAL/FIRST_STEPS/RISKS/DONE_WHEN>` |
| Context gather stage completes | `Pre-gathered workspace context: <file tree + key file snippets>` |
| Recovery pattern detected | `[RECOVERY HINT — <pattern>] <suggested action>` |
| Probe stage completes | Probe findings injected into stage context |

These injections are **invisible to the current UI**. The Prompt Workbench shows the system prompt only — it has no view into mid-turn injections.

---

### 1.4 Prompt Versioning Store

`prompt_tuning_store.py` maintains:
- A local **Git repo** at `<workspace>/.prompt-versioning/` — snapshots of the prompt docs after each edit
- A **SQLite DB** at `.prompt-versioning/prompt_eval.db` — links each version to benchmark probe results
- Accessible from the diagnostic lab for version diff and rollback

This is a history store, not a strategy library. It tracks what changed and what score followed — it does not know about named strategies or configurations.

---

### 1.5 Current UI — Prompt Workbench (Right Panel)

The right panel is a `ttk.Notebook` with five tabs:

#### Prompt tab
- **COMPILED PROMPT** card: line count, char count, fingerprint, ready/building state
- **SOURCE LAYERS** card: active layer count, warning count, source fingerprint
- **LAST PROMPT** preview: scrollable raw text of the most recently sent prompt (truncated to 4,000 chars)
- **LAST RESPONSE** preview: scrollable raw text of the last model response
- **Reload Docs** button

#### Sources tab
- List of currently loaded source files with layer badge (`global_doc` / `project_override`)
- Source editor: click a file → content appears in editor → edit inline → Save / Save As
- Can load an external file into the editor
- No section enable/disable toggle — presence in the folder = active

#### Inspect tab (nested notebook)
- **System**: full system prompt raw text (scrollable)
- **Last Prompt**: full message list sent to the model last turn (scrollable)
- **Last Response**: full raw response last turn
- **Sources**: concatenated source doc text

#### Tools tab
- Tool catalog display (names, descriptions, source)

#### Bag tab
- Evidence bag summary display with Refresh button

---

## 2. What's Missing for Full Prompt Management

### 2.1 No Per-Section Visibility During a Turn

The current UI shows the assembled prompt as a flat blob. There is no way to see:
- Which sections are contributing what tokens
- Which section is the largest
- Which runtime sections were included (planner guidance, recovery hints) for a specific turn
- What the RAG retrieved and which chunks matched

**Gap:** Section breakdown is available in `PromptBuildResult.sections` but never exposed in the UI as individual cards.

### 2.2 No Live Step Monitor

The turn pipeline has discrete stages (planner → context gather → probe → assembler → tool loop → evidence pass) but there is no live panel that shows which stage is currently running and what it injected. The runtime log has this information but it's buried in the Runtime strip at the bottom.

**Gap:** No "turn stage viewer" that lights up as each stage fires and shows what it produced.

### 2.3 No Prompt Strategy Library

There is no concept of a named prompt "strategy" or "profile." You can edit the files, but there is no way to:
- Save a named configuration (e.g. "Scaffolding Mode", "Debug Mode", "Minimal Mode")
- Switch between configurations in one click
- Share or export a configuration as a unit

**Gap:** No strategy store, no switcher, no import/export.

### 2.4 No Section Enable/Disable Toggle

The only way to disable a prompt section is to delete or rename the file. There is no per-section on/off switch that leaves the file intact.

**Gap:** No section toggle UI.

### 2.5 No Turn-Level Prompt History

The versioning store tracks prompt doc changes. But there is no way to look at a specific past turn in the chat history and ask "what was in the prompt when that turn ran?" The `PromptBuildResult` is built per turn and discarded after delivery to the Inspect tab.

**Gap:** No turn-indexed prompt archive.

### 2.6 No Token Budget Visualisation Per Section

The budget guard operates at the assembled prompt level. There is no view showing how many tokens each section consumes and what gets trimmed when over budget.

**Gap:** No token breakdown chart or table.

### 2.7 Mid-Turn Injection Blindspot

Planner guidance, recovery hints, context gather results, and probe findings all get injected as mid-turn system messages — they are **never shown in the Prompt Workbench**. The only way to see them is to read the raw message list in the Inspect → Last Prompt tab.

**Gap:** Mid-turn injections are untracked in any structured UI.

---

## 3. Integration Architecture for a Full Management System

### Layer 1 — Section Breakdown View (Low Effort, High Value)

**Where to add it:** New sub-tab under Inspect, or expand the Prompt tab's COMPILED PROMPT card into a collapsible section list.

**What it shows:**
- Each `PromptSection` as a card: name, layer badge, token count, first 2 lines of content
- Click to expand full content
- Token budget bar per section (proportional to total)
- Visual flag on sections that were trimmed by the budget guard

**What it requires:**
- Token count per section (use the existing `chars / chars_per_token` ratio from `context_budget.py`)
- Pass `PromptBuildResult.sections` to the UI — this already happens via `set_prompt_inspector()` in `app_prompt.py`
- No pipeline changes needed

---

### Layer 2 — Live Stage Monitor (Medium Effort)

**Where to add it:** New tab in the Prompt Workbench, or a collapsible strip below the chat pane that is visible only during a turn.

**What it shows:**
- Stage pipeline visualised as a horizontal step indicator: `Planner → Context → Probe → Assemble → Tool Loop → Evidence`
- Each stage lights up when active, goes green when complete, shows a one-line summary of what it produced
- Injection log: lists every mid-turn system message in order with its source label (planner, context_gatherer, recovery, probe)

**What it requires:**
- Stage events emitted to the `ActivityStream` — this already happens informally via `activity.info("planner", ...)`, `activity.info("context", ...)` etc.
- A structured stage event type in `ActivityStream` with a `stage` field
- UI subscribes to stage events and updates the monitor
- No changes to turn logic — just formalize what the activity stream already logs

---

### Layer 3 — Prompt Strategy Library (Medium Effort)

**Where to add it:** New "Strategy" tab in the Prompt Workbench, or a strategy picker in the Settings dialog.

**Design:**

A strategy is a JSON manifest file stored in `_docs/prompt_strategies/<name>.json`:

```json
{
  "name": "Scaffolding Mode",
  "description": "Lean prompt for fast file scaffolding tasks.",
  "sections": {
    "00_identity.md": { "enabled": true },
    "10_workspace_semantics.md": { "enabled": true },
    "60_project_tidiness.md": { "enabled": true },
    "40_response_style.md": { "enabled": false },
    "55_self_architecture.md": { "enabled": false }
  },
  "runtime_overrides": {
    "build_mode": "compact",
    "max_tool_rounds": 20
  }
}
```

The strategy loader reads the manifest, passes enabled section names as a filter to `load_prompt_sources()` (which already has a `skip_prefixes` param), and applies runtime overrides to a config snapshot for the turn.

**UI:**
- Strategy list with name, description, section count
- Active strategy badge in the header bar
- New / Clone / Delete / Export buttons
- One-click switch (confirmation if a turn is in progress)

---

### Layer 4 — Turn-Level Prompt Archive (Low Effort)

**Where to add it:** Extend the existing `PromptTuningStore` SQLite schema with a `turn_prompts` table.

**Schema addition:**

```sql
CREATE TABLE turn_prompts (
  id INTEGER PRIMARY KEY,
  session_id TEXT,
  turn_index INTEGER,
  created_at TEXT,
  model TEXT,
  prompt_fingerprint TEXT,
  source_fingerprint TEXT,
  sections_json TEXT,      -- JSON array of {name, layer, token_count}
  injections_json TEXT,    -- JSON array of {stage, content}
  total_tokens INTEGER
);
```

**What it enables:**
- Browse past turns and inspect exactly what prompt was used
- Diff two turn prompts (which sections changed, what was added/removed)
- Correlate prompt composition with response quality over time

**What it requires:**
- After each turn, `turn_pipeline.py` emits the `PromptBuildResult` + the injection log to the store
- The Inspect tab gets a "History" sub-tab with a turn selector and diff view

---

### Layer 5 — Section Toggle UI (Low Effort)

**Where to add it:** The Sources tab already lists sections. Add a checkbox per row.

**Design:**
- Each section row in the Sources list gains an enable/disable checkbox
- Disabled sections are stored in a `_docs/agent_prompt/.disabled` file (list of filenames)
- `load_prompt_sources()` checks this file and skips listed filenames
- Changes take effect immediately on next Reload Docs

**What it requires:**
- Add `.disabled` file read/write in `prompt_sources.py`
- Checkbox in the Sources tab list
- No changes to the builder or pipeline

---

## 4. Recommended Build Order

| Priority | Feature | Effort | Value |
|---|---|---|---|
| 1 | Section breakdown view (Layer 1) | Low | Immediate visibility into what's in the prompt |
| 2 | Section toggle UI (Layer 5) | Low | Control without file management |
| 3 | Mid-turn injection log (part of Layer 2) | Low-Medium | Closes the biggest blindspot (planner/recovery/context injections invisible) |
| 4 | Turn-level prompt archive (Layer 4) | Medium | Enables retrospective analysis |
| 5 | Live stage monitor (full Layer 2) | Medium | Watching the agent think in real time |
| 6 | Prompt strategy library (Layer 3) | Medium | Power user workflow — named configurations |

---

## 5. Files That Need to Change Per Layer

### Layer 1 (Section Breakdown)
- `src/ui/panes/control_pane.py` — add section card list to Inspect tab
- `src/app_prompt.py` — pass full sections tuple to UI, not just the flat prompt string
- No pipeline changes

### Layer 2 (Stage Monitor)
- `src/core/runtime/activity_stream.py` — add `stage()` event type
- `src/core/agent/turn_pipeline.py` — emit structured stage events
- `src/ui/panes/control_pane.py` — add stage monitor widget
- `src/ui/ui_facade.py` — add `update_stage()` method

### Layer 3 (Strategy Library)
- `src/core/agent/prompt_sources.py` — add strategy manifest loader
- `src/core/agent/prompt_builder.py` — accept strategy override param
- `src/ui/panes/control_pane.py` — add Strategy tab
- `src/core/config/app_config.py` — add `active_strategy` field

### Layer 4 (Turn Archive)
- `src/core/agent/prompt_tuning_store.py` — add `turn_prompts` table and write method
- `src/core/agent/turn_pipeline.py` — call store after each turn
- `src/ui/panes/control_pane.py` — add History sub-tab in Inspect

### Layer 5 (Section Toggle)
- `src/core/agent/prompt_sources.py` — read `.disabled` file
- `src/ui/panes/control_pane.py` — add checkbox to source list rows

---

## 6. Key Design Decisions to Discuss

1. **Strategy vs. Override**: Should a "strategy" fully replace the section list, or should it be a delta on top of the global defaults? Delta is more maintainable; replacement is more predictable.

2. **Where does the stage monitor live?**: In the Prompt Workbench (right panel) it's always visible but takes space. As a collapsible strip below chat it's more contextual. As a popout it's non-intrusive.

3. **Per-project vs. global strategies**: Should strategies be stored globally (`_docs/prompt_strategies/`) or per-project (`.mindshard/strategies/`)? Both with merge is the cleanest but adds complexity.

4. **Section order control**: Currently defined by filename sort. Strategy manifests could define explicit ordering — but this breaks the simple glob-and-sort model. Worth deciding before building.

5. **Injection visibility in Sources tab**: Should mid-turn injections (planner, recovery, context) appear as read-only virtual sections in the section breakdown? They are not files but they do contribute tokens. Treating them as first-class sections with a `runtime_injection` layer badge would give a complete picture.
