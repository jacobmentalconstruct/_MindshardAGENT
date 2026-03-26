# Control Pane Split Plan

`src/ui/panes/control_pane.py` remains deferred for this tranche. This document
records the intended split seams so nearby changes do not keep growing the file
indefinitely.

## Goal

Break the current workstation shell into smaller UI-local owners without moving
workflow logic out of the existing app/core seams.

This is a future UI decomposition task, not part of the current alignment pass.

## Target Seams

### 1. Workspace Rail

Owns the left-side session/sandbox/git shell:

- current session summary
- model picker block
- session list / branch / rename / delete controls
- sandbox actions and Docker controls
- VCS status panel
- resource/status block

Candidate destination modules:

- `src/ui/panes/workspace_rail.py`
- `src/ui/widgets/workspace_status_block.py`

### 2. Interaction Center

Owns the center chat and compose area:

- `ChatPane`
- compose/input dock
- CLI dock
- loop mode selector / send / stop interactions

Most of this already delegates well; future work should keep it as a shallow
layout shell around existing pane/widget owners.

Candidate destination modules:

- `src/ui/panes/interaction_shell.py`
- `src/ui/panes/compose_dock.py`

### 3. Prompt Workbench

Owns the right-side prompt and inspection region:

- compiled prompt display
- source layers
- inspect tab
- tools tab
- bag/evidence tab

This is the most likely region to grow alongside prompt-lab, evidence-bag, and
inspection work, so it should eventually have a dedicated workbench owner.

Candidate destination modules:

- `src/ui/panes/prompt_workbench.py`
- `src/ui/widgets/prompt_summary_panel.py`
- `src/ui/widgets/inspect_panel.py`

### 4. Sources / Evidence Surface

Owns the source list, source editing affordances, and evidence-bag browsing
surfaces. This should remain aligned with the prompt/evidence north-star work
instead of being flattened into generic layout helpers.

Candidate destination modules:

- `src/ui/panes/sources_panel.py`
- `src/ui/panes/evidence_panel.py`

## Split Rules

- Keep this split UI-local.
- Do not move app/core workflow logic into UI modules.
- Preserve `UIFacade` as the intent seam; the UI split should not bypass it.
- Preserve prompt/evidence future-facing seams; do not “simplify away” those
  surfaces during the breakup.
- Favor extraction by owned visual region, not by random helper methods.

## Not In Scope For This Tranche

- redesigning layout behavior
- changing callback contracts
- moving prompt-building logic into UI
- moving session/project workflows into UI
