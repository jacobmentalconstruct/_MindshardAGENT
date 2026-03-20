Yes. Here is a **Tkinter layout tree** for the redesigned workstation so you can see the structure clearly before wiring code.

---

# Implementation Status (2026-03-20)

This layout has now been implemented as the active shell in:

- `src/ui/gui_main.py`
- `src/ui/panes/control_pane.py`

What is currently landed:

- top status bar
- main vertical split
- left workspace rail with `Session`, `Sandbox`, `Git`
- center interaction area with chat plus `Compose` / `Sandbox CLI`
- right prompt workbench with `Prompt`, `Sources`, `Inspect`, `Tools`
- runtime log strip
- startup sash stabilization with minimum pane widths

Current polish-level additions beyond the original tree:

- live summary cards for session/project state in the left rail
- structured source-layer cards in the `Sources` tab
- inline source editor and prompt-doc file actions in the `Sources` tab
- mirrored prompt/response views between summary and inspect tabs
- tools-tab loop controls for max tool rounds and stop guidance

What is still intentionally deferred:

- source diff view
- persistent remembered sash widths
- tab breakout/pop-out behavior in the new notebook shell

This doc should now be treated as the architectural reference for the current shell, not just a proposal.

---

# Visual layout map

```text
ROOT: Tk()
└── app_shell : ttk.Frame
    ├── top_status_bar : ttk.Frame
    │   ├── brand_label                 "AGENTIC TOOLBOX"
    │   ├── model_status_label          "model: ..."
    │   ├── session_status_label        "session: ..."
    │   ├── source_status_label         "source: ..."
    │   └── working_path_label          "working: ..."
    │
    ├── main_vertical_split : ttk.PanedWindow (VERTICAL)
    │   ├── main_horizontal_work_area : ttk.PanedWindow (HORIZONTAL)
    │   │   ├── left_workspace_rail : ttk.Frame
    │   │   │   └── left_notebook : ttk.Notebook
    │   │   │       ├── session_tab : ttk.Frame
    │   │   │       │   ├── session_summary_card
    │   │   │       │   ├── session_list / tree
    │   │   │       │   ├── new_session_btn
    │   │   │       │   ├── load_session_btn
    │   │   │       │   ├── rename_session_btn
    │   │   │       │   └── session_meta_panel
    │   │   │       │
    │   │   │       ├── sandbox_tab : ttk.Frame
    │   │   │       │   ├── sandbox_summary_card
    │   │   │       │   ├── source_project_path_row
    │   │   │       │   ├── sandbox_project_path_row
    │   │   │       │   ├── attach_project_btn
    │   │   │       │   ├── clone_to_sandbox_btn
    │   │   │       │   ├── sync_to_source_btn
    │   │   │       │   ├── detach_btn
    │   │   │       │   └── sandbox_mode/status_panel
    │   │   │       │
    │   │   │       └── git_tab : ttk.Frame
    │   │   │           ├── git_summary_card
    │   │   │           ├── branch_row
    │   │   │           ├── status_tree
    │   │   │           ├── commit_entry
    │   │   │           ├── commit_btn
    │   │   │           ├── snapshot_btn
    │   │   │           ├── diff_btn
    │   │   │           └── history_list
    │   │   │
    │   │   ├── center_interaction_area : ttk.Frame
    │   │   │   ├── chat_container : ttk.Frame
    │   │   │   │   ├── chat_header_row
    │   │   │   │   │   ├── chat_title_label
    │   │   │   │   │   ├── active_model_chip
    │   │   │   │   │   ├── token_count_chip
    │   │   │   │   │   └── inference_status_chip
    │   │   │   │   └── chat_history_view
    │   │   │   │       ├── transcript_canvas/text
    │   │   │   │       └── transcript_scrollbar
    │   │   │   │
    │   │   │   └── bottom_interaction_dock : ttk.Notebook
    │   │   │       ├── compose_tab : ttk.Frame
    │   │   │       │   ├── compose_status_row
    │   │   │       │   │   ├── source_count_label
    │   │   │       │   │   ├── ref_count_label
    │   │   │       │   │   ├── approx_tokens_label
    │   │   │       │   │   └── rebuild_state_label
    │   │   │       │   ├── prompt_input_text
    │   │   │       │   └── compose_action_row
    │   │   │       │       ├── attach_ref_btn
    │   │   │       │       ├── add_parts_btn
    │   │   │       │       ├── clear_prompt_btn
    │   │   │       │       └── send_btn
    │   │   │       │
    │   │   │       └── sandbox_cli_tab : ttk.Frame
    │   │   │           ├── cli_output_view
    │   │   │           └── cli_action_row
    │   │   │               ├── cli_prompt_label "$"
    │   │   │               ├── cli_input_entry/text
    │   │   │               ├── run_btn
    │   │   │               └── stop_btn
    │   │   │
    │   │   └── right_prompt_workbench : ttk.Frame
    │   │       └── right_notebook : ttk.Notebook
    │   │           ├── prompt_tab : ttk.Frame
    │   │           │   ├── compiled_prompt_summary_card
    │   │           │   ├── system_prompt_summary_card
    │   │           │   ├── last_prompt_preview_card
    │   │           │   ├── last_response_preview_card
    │   │           │   └── prompt_action_row
    │   │           │       ├── rebuild_prompt_btn
    │   │           │       ├── copy_prompt_btn
    │   │           │       └── save_snapshot_btn
    │   │           │
    │   │           ├── sources_tab : ttk.Frame
    │   │           │   ├── sources_toolbar
    │   │           │   │   ├── refresh_sources_btn
    │   │           │   │   ├── auto_rebuild_toggle
    │   │           │   │   └── filter_entry
    │   │           │   └── source_layers_stack
    │   │           │       ├── source_layer_card(runtime)
    │   │           │       ├── source_layer_card(journal)
    │   │           │       ├── source_layer_card(vcs)
    │   │           │       ├── source_layer_card(ref_1)
    │   │           │       └── ...
    │   │           │
    │   │           ├── inspect_tab : ttk.Frame
    │   │           │   └── inspect_notebook : ttk.Notebook
    │   │           │       ├── compiled_view_tab
    │   │           │       │   └── compiled_prompt_text
    │   │           │       ├── system_view_tab
    │   │           │       │   └── system_prompt_text
    │   │           │       ├── last_prompt_tab
    │   │           │       │   └── last_prompt_text
    │   │           │       ├── last_response_tab
    │   │           │       │   └── last_response_text
    │   │           │       └── diff_tab
    │   │           │           └── diff_text
    │   │           │
    │   │           └── tools_tab : ttk.Frame
    │   │               ├── tools_toolbar
    │   │               │   ├── reload_tools_btn
    │   │               │   └── open_tools_dir_btn
    │   │               └── tools_list / tool_cards
    │   │
    │   └── runtime_log_strip : ttk.Frame
    │       ├── runtime_header_row
    │       │   ├── runtime_title_label
    │       │   ├── log_level_filter
    │       │   ├── clear_log_btn
    │       │   └── pause_log_btn
    │       └── runtime_log_view
    │           ├── runtime_text
    │           └── runtime_scrollbar
    │
    └── bottom_status_bar : ttk.Frame
        ├── app_status_label
        ├── engine_status_label
        ├── sandbox_status_label
        ├── git_status_label
        └── transient_message_label
```

---

# Human-readable visual composition

Think of it like this:

```text
┌───────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ TOP STATUS BAR                                                                                            │
│ AGENTIC TOOLBOX | model | session | source | working path                                                 │
├───────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ┌──────────────────────┬───────────────────────────────────────────────┬────────────────────────────────┐ │
│ │ LEFT WORKSPACE RAIL  │ CENTER INTERACTION AREA                       │ RIGHT PROMPT WORKBENCH         │ │
│ │                      │                                               │                                │ │
│ │ [Session]            │ ┌───────────────────────────────────────────┐ │ [Prompt] [Sources] [Inspect]   │ │
│ │ [Sandbox]            │ │               CHAT HISTORY                │ │ [Tools]                        │ │
│ │ [Git]                │ │                                           │ │                                │ │
│ │                      │ │                                           │ │ compiled prompt summary        │ │
│ │                      │ │                                           │ │ source layers                  │ │
│ │                      │ │                                           │ │ raw prompt inspection          │ │
│ │                      │ └───────────────────────────────────────────┘ │ tool registry                  │ │
│ │                      │ ┌───────────────────────────────────────────┐ │                                │ │
│ │                      │ │ [Compose] [Sandbox CLI]                   │ │                                │ │
│ │                      │ │                                           │ │                                │ │
│ │                      │ │ prompt input / send                       │ │                                │ │
│ │                      │ │ or sandbox terminal                       │ │                                │ │
│ │                      │ └───────────────────────────────────────────┘ │                                │ │
│ └──────────────────────┴───────────────────────────────────────────────┴────────────────────────────────┘ │
├───────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ RUNTIME LOG STRIP                                                                                         │
├───────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ BOTTOM STATUS BAR                                                                                         │
└───────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

# Region responsibilities

This is the part that keeps the layout from drifting back into clutter.

## 1. Left workspace rail

This rail answers:

**“Where am I working?”**

It owns:

* session selection and session metadata
* sandbox attachment / cloning / sync
* git status / snapshots / commits / history

It should **not** own:

* prompt raw text
* chat input
* last response dumps

---

## 2. Center interaction area

This area answers:

**“What am I doing right now?”**

It owns:

* chat transcript
* prompt writing
* send/submit
* sandbox CLI execution

This is the primary work lane.

---

## 3. Right prompt workbench

This area answers:

**“What context is the agent seeing?”**

It owns:

* compiled prompt summary
* source layers
* raw system prompt
* last prompt / last response inspection
* custom tools registry

This is not the same thing as environment management.

---

## 4. Runtime log strip

This answers:

**“What is the app doing under the hood?”**

It should stay thin and low-drama.
Useful, but not dominant.

---

# Geometry intent

This is the proportion logic I would use.

## Horizontal split

```text
left rail      = 0.20
center area    = 0.55
right workbench= 0.25
```

So approximately:

* **20% left**
* **55% center**
* **25% right**

That keeps chat as the main experience.

---

## Vertical split inside center

```text
chat history         = 0.72
bottom interaction   = 0.28
```

That gives the prompt box real room without crushing the transcript.

---

## Main vertical split for runtime strip

```text
main work area   = 0.84
runtime strip    = 0.16
```

The runtime panel stays present but does not dominate.

---

# Tkinter container strategy

This is the clean parent/child architecture I would use.

## Core containers

* `root`
* `app_shell`
* `top_status_bar`
* `main_vertical_split`
* `main_horizontal_work_area`
* `runtime_log_strip`
* `bottom_status_bar`

## Inside the horizontal split

* `left_workspace_rail`
* `center_interaction_area`
* `right_prompt_workbench`

## Internal tabbing

Use `ttk.Notebook` in exactly three places:

1. `left_notebook`
2. `bottom_interaction_dock`
3. `right_notebook`

And a fourth nested notebook only for raw inspection:

4. `inspect_notebook`

That gives clean separation without exploding the layout into too many floating panes.

---

# Recommended widget styles by region

## Left rail

Compact management widgets:

* summary cards
* list/tree widgets
* short command rows
* state labels

## Center chat

Larger readable widgets:

* transcript text/canvas
* multiline prompt input
* wider action row

## Right workbench

Mixed density:

* compact summaries in `Prompt`
* cards/toggles in `Sources`
* full text viewers only in `Inspect`

## Runtime strip

Plain log viewer:

* monospaced text
* level filter
* clear/pause controls

---

# Prompt source layer card concept

In `sources_tab`, do not use a dead listbox if you can avoid it.

Each source should be a little structured row/card like:

```text
[✓] Runtime Core          tokens: 214   state: active   [Inspect] [Disable]
[✓] Journal               tokens: 488   state: fresh    [Inspect] [Disable]
[✓] VCS                   tokens: 302   state: active   [Inspect] [Disable]
[ ] Ref: bag_of_evidence  tokens: 901   state: idle     [Inspect] [Enable]
```

That visually teaches:

* inclusion state
* name
* weight/cost
* inspectability
* control

That is far better than a plain source list.

---

# Minimal implementation order

If you want to rebuild without chaos, this is the correct order.

## Phase 1: shell restructure

Create the new parent containers only:

* top bar
* left rail
* center
* right
* runtime strip
* bottom status bar

No fancy behavior yet.

## Phase 2: move existing widgets into correct parents

Relocate:

* session/sandbox/version controls → left
* chat + input → center
* prompt/source/inspect → right
* runtime log → bottom strip

## Phase 3: convert overloaded stacks into notebooks

Add:

* left notebook
* bottom dock notebook
* right notebook
* inspect nested notebook

## Phase 4: clean individual tabs

Replace passive boxes with:

* summary cards
* source rows/cards
* preview panes
* on-demand raw views

That sequence prevents layout thrash.

---

# Concise symbolic tree

If you want the short form only:

```text
Tk
└── AppShell
    ├── TopStatusBar
    ├── MainVerticalPaned
    │   ├── MainHorizontalPaned
    │   │   ├── LeftWorkspaceRail
    │   │   │   └── Notebook(Session, Sandbox, Git)
    │   │   ├── CenterInteractionArea
    │   │   │   ├── ChatContainer
    │   │   │   └── Notebook(Compose, SandboxCLI)
    │   │   └── RightPromptWorkbench
    │   │       └── Notebook(Prompt, Sources, Inspect, Tools)
    │   └── RuntimeLogStrip
    └── BottomStatusBar
```

---

# Direct verdict

This layout is structurally sound because it separates the app into four clear domains:

* **environment**
* **interaction**
* **context assembly**
* **runtime observation**

That is the underlying correction your screenshots were asking for.

If you want, next I can turn this into an actual **Tkinter frame construction skeleton** with parent names, `PanedWindow` orientation, `grid()` placement rules, and notebook/tab creation order.
