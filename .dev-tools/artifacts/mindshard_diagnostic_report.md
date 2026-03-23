# MindshardAGENT Diagnostic Report
Generated: 2026-03-22 | Tools: python_risk_scan, tk_ui_thread_audit, tk_ui_layout_audit, tk_ui_event_map, tk_ui_map, workspace_audit

---

## Executive Summary

| Scan | Files | Findings |
|---|---|---|
| python_risk_scan | 99 | 16 blocking calls |
| tk_ui_thread_audit | 99 | 29 findings (2 blocking in UI callbacks, 27 thread→UI) |
| tk_ui_layout_audit | 99 | 10 findings + 70 fixed-dimension widgets |
| tk_ui_event_map | 99 | 149 event edges, 49 anonymous lambdas |
| tk_ui_map | 99 | 20 Tkinter files, 95 Frames, 256 pack calls |

---

## SECTION 1 — Blocking Calls (python_risk_scan)

All 16 findings are `subprocess.run()`. None are `eval`, `exec`, or `bare_except` — the codebase is clean on those.

### Already Fixed / Correctly Threaded
| File | Line | Status |
|---|---|---|
| `core/runtime/resource_monitor.py` | 68 | Fixed — GPU probe runs in daemon thread, cached |
| `core/sandbox/cli_runner.py` | 112 | OK — intentional blocking sandbox CLI, called from agent worker thread |
| `core/sandbox/python_runner.py` | 167 | OK — intentional blocking, called from agent worker thread |

### Needs Attention
| File | Lines | Issue |
|---|---|---|
| `core/sandbox/docker_manager.py` | 63, 74, 101, 124, 173, 195, 209, 245 | 8 subprocess.run() calls — all fine IF only called from bg threads. Docker polling now gated behind `docker_enabled` flag. Watch for direct calls from main thread (e.g. `on_docker_toggle` calls `_refresh_docker_status()` directly). |
| `core/agent/prompt_tuning_store.py` | 706 | `subprocess.run(["git", ...])` — called during prompt snapshots. If triggered from main thread, blocks UI. Verify all callers are on bg threads. |
| `core/vcs/git_client.py` | 55, 131, 211, 230 | 4 git subprocess calls — same concern. VCS panel calls these in bg threads (good). Any synchronous call from main thread (e.g. during `engine.set_sandbox()`) would freeze UI. |

### Action Items
- [ ] Audit all callers of `docker_manager.get_info/is_docker_available/image_exists/container_status` — ensure none are on main thread when docker is enabled
- [ ] Audit all callers of `prompt_tuning_store._run_git()` — wrap in bg thread if called synchronously
- [ ] Audit `engine.set_sandbox()` VCS attach path — `vcs.attach()` runs git init/snapshot synchronously on first attach; consider deferring to bg thread

---

## SECTION 2 — Thread Safety (tk_ui_thread_audit)

### 2a. Blocking calls inside UI callbacks (HIGH PRIORITY)

| File | Line | Callback | Issue |
|---|---|---|---|
| `app.py` | 484 | `_flush_stream` (scheduled via `after`) | Contains `.join()` call — this is a thread join INSIDE a scheduled UI callback. If the worker thread hasn't finished, this blocks the main thread. |

**Fix:** Remove or replace the `.join()` inside `_flush_stream`. The streaming architecture should never need to join from the UI side — use the `_on_complete` callback pattern already in place.

### 2b. Worker threads calling UI methods (INFORMATIONAL)

The audit flags 27 instances of threads calling `self.after()` or `root.after()`. These are the **correct pattern** for Tkinter thread safety — they are all marshaling results back to the main thread via `after(0, ...)`, not touching widgets directly. No action required on these.

Confirmed safe patterns:
- `_background_work` → `root.after(0, _ui_work)` ✓
- `_bg` → `root.after(0, _apply)` ✓
- `VCSPanel._load` → `self.after(0, ...)` ✓
- `VCSPanel._run` → `self.after(0, ...)` ✓

### Action Items
- [ ] Investigate `_flush_stream` at `app.py:484` — find and remove/guard the `.join()` call inside the scheduled callback

---

## SECTION 3 — Layout Audit (tk_ui_layout_audit)

### 3a. Critical Layout Issues

| File | Line | Rule | Detail |
|---|---|---|---|
| `ui/gui_main.py` | 71 | `hardcoded_window_size` | `minsize(1180, 720)` — brittle on high-DPI displays |
| `ui/gui_main.py` | 78, 200 | `geometry_propagation_disabled` | `pack_propagate(False)` — prevents child widgets from resizing parent; can cause layout artifacts |
| `ui/gui_main.py` | 257 | `manual_sash_placement` | `sash_place()` — brittle across DPI/window resize |
| `ui/panes/control_pane.py` | 1362, 1363, 1368 | `manual_sash_placement` | 3 more `sash_place()` calls — already has `_apply_default_layout` to manage these but can still glitch |

### 3b. Mixed Geometry Managers (can cause TclError crashes)

| File | Class | Managers Used |
|---|---|---|
| `ui/dialogs/settings_dialog.py` | `SettingsDialog` | `grid` + `pack` |
| `ui/widgets/faux_button_panel.py` | `FauxButtonPanel` | `grid` + `pack` |
| `ui/widgets/vcs_panel.py` | `VCSPanel` | `pack` + `place` |

**Note:** Mixing `pack` and `grid` in the same container will raise a `TclError` at runtime. These need to be audited — if they're mixing managers within the same parent frame, it will crash. If they're in separate frames it's fine.

### 3c. Fixed Dimensions (70 instances)

Pervasive use of hardcoded `width`, `height`, `wraplength`, `padx`, `pady` values. Most are padding constants (low risk). Key ones to watch:
- `ui/widgets/faux_button_panel.py:30` — `Button(width=8, height=1)` character-unit sizing
- `ui/panes/input_pane.py:21` — `Text(height=5)` fixed height
- `ui/panes/cli_pane.py:27` — `Text(height=8)` fixed height
- `ui/widgets/session_panel.py:50` — `Listbox(height=6)` fixed height
- `ui/widgets/vcs_panel.py:60` — `Listbox(height=5)` fixed height

### Action Items
- [ ] Audit the three mixed-geometry-manager classes — ensure mixing is between separate container frames, not the same parent
- [ ] Consider replacing `minsize(1180, 720)` with DPI-scaled values using the existing `dpi_scale` value from `enable_dpi_awareness()`
- [ ] Review `pack_propagate(False)` in gui_main.py — document why it's disabled or remove if not needed

---

## SECTION 4 — Event Map (tk_ui_event_map)

### 4a. Lambda overuse

**49 out of 149 event edges (33%) use anonymous lambdas as callbacks.** This makes debugging very hard — stack traces show `<lambda>` with no context. Heavy use in:
- `<Enter>`/`<Leave>` hover effects (acceptable — very simple)
- Inline command callbacks in control_pane (should be named methods)

### 4b. Schedule method breakdown
| Method | Count |
|---|---|
| `after` | 26 |
| `after_cancel` | 7 |
| `after_idle` | 2 |

26 `after()` calls is high. Most are legitimate (polling, deferred layout). The 2 `after_idle` calls in `control_pane.py` are part of the layout initialization loop — already analyzed as safe.

### 4c. Thread starts (22 total)
All thread starts appear intentional. Top targets: `_worker` (agent loops), `_bg` (polling), `VCSPanel._load/_run`, `_probe_gpu_async`, `_background_work`.

### 4d. bind_all usage
`bind_all("<MouseWheel>")` was previously flagged and **already fixed** in this session. Current scan shows 3 `<MouseWheel>` binds — all now correctly scoped to canvas/inner/card.

### Action Items
- [ ] Gradually replace anonymous lambdas in command callbacks with named methods for debuggability (low urgency, high quality-of-life)

---

## SECTION 5 — UI Structure (tk_ui_map)

### Overview
- **20 Tkinter files** across the project
- **95 Frames** — very Frame-heavy architecture (expected for a complex panel layout)
- **256 pack calls, 3 grid, 2 place** — predominantly `pack`-based (good consistency)
- **20 UI subclasses** — well-componentized

### Widget counts
| Widget | Count |
|---|---|
| Frame | 95 |
| Label | 88 |
| Button | 28 |
| Text | 8 |
| Scrollbar | 8 |
| ttk.Notebook | 5 |
| PanedWindow | 4 |
| Canvas | 2 |

### Observations
- 8 `tk.Text` widgets — each is non-trivial for layout and render performance
- `PanedWindow` with manual `sash_place()` — see layout audit
- `ttk.Notebook` used in 5 places — mixing `ttk` and `tk` widgets is fine but theme consistency should be verified

---

## SECTION 6 — Workspace Overview

- **451 total files, 177 dirs**
- **198 Python files**
- `src/app.py` is the largest source file at **66KB** — strong candidate for decomposition
- `src/ui/panes/control_pane.py` at **56KB** — second largest, contains a huge amount of UI logic

### Large files to watch
| File | Size | Note |
|---|---|---|
| `src/app.py` | 66KB | Monolithic composition root — all callbacks, timers, session logic |
| `src/ui/panes/control_pane.py` | 56KB | All three panel columns + all workbench tabs |
| `_logs/app.log` | 256KB | Growing log — has rotation? |
| `_sandbox/_sessions/sessions.db` | 684KB | SQLite session store — healthy size |

### Sandbox artifacts
There's a `_sandbox/project/_MindshardAGENT.zip` (803KB) — a previous version snapshot. The sandbox also contains `_tools/builder_widget/` with large symbol/relation JSON files (~400KB each × 8 files = ~3MB). These are agent-generated artifacts from prior sessions.

---

## SECTION 7 — Priority Fix List

### P0 — Stability (fix before testing)
1. **`_flush_stream` join** (`app.py:484`) — blocking join inside scheduled UI callback
2. **Verify mixed geometry managers** — `SettingsDialog`, `FauxButtonPanel`, `VCSPanel` — if managers mix in same parent, will crash

### P1 — Performance (current session focus)
3. **`prompt_tuning_store._run_git()`** — verify all callers are threaded; if called from main thread during prompt snapshots, blocks UI
4. **`engine.set_sandbox()` VCS first-attach** — runs git init + full snapshot synchronously; defer to bg thread for first-time sandbox setup
5. **`on_docker_toggle` direct call** — calls `_refresh_docker_status()` synchronously from main thread; should thread this too

### P2 — Robustness
6. **Mixed geometry manager audit** — go through `SettingsDialog`, `FauxButtonPanel`, `VCSPanel` and confirm or fix
7. **Lambda→named-method refactor** — improve debuggability of 49 anonymous callbacks
8. **DPI-aware minsize** — scale `minsize(1180, 720)` using `dpi_scale`

### P3 — Architecture / Future
9. **Decompose `app.py`** — 66KB monolith; extract session management, timer management, and action callbacks into separate modules
10. **Decompose `control_pane.py`** — 56KB; split left rail, center area, right workbench into separate files
11. **MCP layer** — expose engine capabilities (submit_prompt, run_cli, session ops) via MCP server for agent-to-agent use

---

## Notes on False Positives

- `thread_target_touches_ui` findings for `_bg`, `_background_work`, `VCSPanel._load/_run` — all using `self.after(0, ...)` correctly; flagged by the tool as a conservative warning but these are the correct Tkinter threading pattern
- `blocking_call` in `cli_runner.py` and `python_runner.py` — intentional; these are the sandbox execution engines, always called from worker threads
