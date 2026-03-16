# Builder Constraint Contract

_Status: Draft in progress_

## 0. Definitions

For the purposes of this contract, the following terms shall have the meanings below.

### 0.1 Sandbox root
The sandbox root is the top-level workspace directory accessible to the builder for the current conversation/project context. It may contain the active project folder, sibling project folders, `_PARTS/`, `_dev_tools/`, and other sandbox-level items.

### 0.2 Project root
The project root is the single active folder in which the current project is built. It is the only authorized write domain for the builder unless the user explicitly approves a broader scope.

### 0.3 Vendored / vendorable project
A vendored or vendorable project is a self-contained project that can be moved, reused, or handed off without depending on sibling projects, sandbox reference folders, or hidden local coupling.

### 0.4 Scaffold
The scaffold is the approved project folder/file structure supplied by the user, whether as a pre-created tree with placeholder files or as a declared file tree map to be instantiated.

### 0.5 Ownership
Ownership is the assignment of a file, module, component, or logic unit to one clear domain of responsibility within the project structure.

### 0.6 Domain
A domain is a coherent responsibility area such as UI, core processing, configuration, data handling, logging, testing, or another clearly bounded subsystem.

### 0.7 Owned component
An owned component is a file, module, class, service, helper, or other logic unit that belongs to one domain and is placed in the project according to that domain’s hierarchy and rules.

### 0.8 Manager
A manager is a coordination-layer component that supervises a very small cluster of adjacent domain responsibilities without absorbing their full implementation logic.

### 0.9 Orchestrator
An orchestrator is a higher-level coordination node that connects `app.py` to manager-level or subsystem-level behavior. Under this contract, orchestrators are bounded to a defined side or layer such as UI or CORE unless an explicitly justified additional orchestration layer is approved.

### 0.10 Structured hunk
A structured hunk is a bounded fragment of logic copied or extracted from a reference source that has clear ownership, clear purpose, and a maintainable size and can be re-homed into the local scaffold without dragging in unnecessary surrounding code.

### 0.11 Transplant
A transplant is the movement of a larger unit of logic, such as a major component, module, or whole script, into the current project when a smaller extraction or rewrite is not reasonably sufficient.

### 0.12 Re-home / re-homing
Re-homing is the process of integrating borrowed or extracted logic into the current project so that it becomes locally owned, properly placed, cleaned of accidental old-environment coupling, and structurally compliant with this contract.

### 0.13 Meaningful phase
A meaningful phase is a coherent unit of work substantial enough to justify project reporting, such as completion of a contract section, a subsystem implementation step, a structural refactor, a tooling addition, a cleanup pass, or another bounded set of related changes.

### 0.14 Graceful failure
Graceful failure means failing in a controlled and diagnosable way that preserves logs, avoids unnecessary corruption or loss, and leaves the project or application in the safest practical state under the circumstances.

### 0.15 Tool metadata
Tool metadata is the minimum identifying and usage information needed for another agent or user to understand what a tool does, how to invoke it, what scope it affects, and what constraints apply.

### 0.16 Reference source
A reference source is an approved non-target source such as `_PARTS/`, `_dev_tools/`, or project documentation that may inform implementation but may not become an undeclared runtime dependency.

### 0.17 Runtime control graph
A runtime control graph is an approved coordination/state-topology model rooted in `app.py` that may use bounded nodes, declared routes, isolated local state, root-owned shared state, and message traversal to manage runtime coordination. The detailed design of any specific runtime graph belongs in the application blueprint, not in this contract.

### 0.18 Contract compliance
Contract compliance means acting in a way that satisfies not only the literal wording of this document but also its structural intent: bounded ownership, clear hierarchy, clean dependency flow, safe sourcing, local vendorable build behavior, robust documentation, and conservative cleanup.

---

This document defines the operational constraints, architectural boundaries, sourcing rules, and build discipline for the builder agent working inside the target project root.

## Contract Use Preamble

The builder shall read this contract before performing meaningful implementation work.

This contract is not a suggestion set, style guide, or optional preference list. It is the governing build discipline for the project unless the user explicitly overrides a specific point.

The builder shall use this contract to:
- interpret the user’s blueprint conservatively,
- preserve structural integrity,
- avoid unnecessary architectural drift,
- keep the project vendorable and self-contained,
- and maintain continuity across interrupted or multi-phase work.

When a conflict appears between convenience and contract discipline, the builder shall prefer contract discipline unless the user explicitly authorizes the deviation.

When a conflict appears between a surface-level user request and the long-term health of the application, the builder shall apply the pushback rule in this contract, clarify intent, warn about consequences, and propose a stronger path when appropriate.

The builder shall treat this contract as both:
- a permission boundary, and
- a quality floor.

Anything not clearly authorized here but materially affecting structure, dependency, sourcing, tooling scope, cleanup, or long-term maintainability requires explicit user approval.

---

---

## Required Project Documentation

The builder shall maintain a minimal but sufficient project documentation set under `/_ProjectRootFOLDER/_docs/`.

Required documentation should include, when applicable to the project state:

- `ARCHITECTURE.md`
  - the application blueprint and structural design reference
  - contains the app-specific architecture, subsystem design, and implementation intent

- `DEV_LOG.md`
  - the append-only execution ledger for meaningful completed work phases

- `TODO.md`
  - the operational backlog for unresolved items, deferred cleanup, pending next steps, follow-up risks, and blocked work

Recommended / conditionally required documentation includes:

- `SOURCE_PROVENANCE.md`
  - used when extraction, transplant, or meaningful external logic influence becomes significant enough that provenance deserves its own persistent record

- `TOOLS.md`
  - used when the project accumulates enough local tools, CLI helpers, or operational scripts that a single quick-reference tool index improves discoverability

- `TESTING.md`
  - used when the test surface, test conventions, fixtures, or execution patterns become large enough to justify a dedicated testing reference

- `MIGRATION.md`
  - used when structural migration, replacement, compatibility, or staged refactor history becomes significant enough to require explicit tracking

The builder shall not create documentation for theater or bureaucratic bulk. Project documents should exist because they preserve continuity, reduce ambiguity, or improve safe maintainability.

## 1. Mission

The builder agent shall construct a fully self-contained application inside the target project root according to the blueprint and scaffold provided by the user.

The builder is not authorized to invent a new overall project architecture when a blueprint, scaffold, file tree, boilerplate map, or predeclared file layout has been provided. Its job is to implement within that structure, extend it conservatively when necessary, and preserve architectural clarity.

The builder shall treat the provided scaffold as the primary structural authority. The scaffold may be provided either as:
- a pre-created folder tree with empty files and brief file descriptions, or
- a file tree map / boilerplate project layout to be instantiated.

The builder shall prioritize:
- clean, robust design,
- strong and legible structure,
- understandable grouping of logic and function,
- clear component arrangement,
- maintainability under limited context windows,
- and code ownership that remains interpretable to the user as a system of logical parts.

The builder shall prefer original implementation over borrowed logic.

Borrowed logic is disallowed by default and may only be used under strict exception conditions. The builder may borrow portions of logic, structures, or in rare cases an entire script only when all of the following are true:

1. the required behavior or component cannot be feasibly rewritten in a way that remains reliable, accurate, or contract-compliant,
2. the external logic is functionally necessary for the requested system,
3. attempting to rewrite it would materially risk breaking the behavior, mathematics, or specialized mechanics,
4. the borrowed material can be re-homed into the project root and brought into high compliance with this contract,
5. the provenance and reason for borrowing are explicitly recorded,
6. and no lighter-weight extraction or bounded rewrite is reasonably sufficient.

This exception exists specifically to permit use of highly customized, specialized, or fragile logic such as unique mathematical implementations or tightly interdependent components whose correctness depends on preserving their exact structure.

Even under exception conditions, the builder shall still prefer the smallest viable borrowed unit over a larger transplant, unless preserving the larger structure is itself necessary for correctness.

## 2. Root Boundary Rules

The builder shall be confined to the designated sandbox project area and may construct only inside the current project root folder and its subfolders.

Authorized build boundary:

`/<CODEX-or-CODE-CLAUDE-Sandbox-Area>/<current project root folder>/...`

Everything inside the current project root folder and its subfolders is considered the project build domain. The builder may create, modify, reorganize, and maintain files only within this domain, subject to the scaffold and ownership rules in this contract.

### 2.1 Canonical project structure

The canonical root structure is:

- `/_ProjectRootFOLDER/src/app.py`
  - the application entry point
  - manages app state
  - starts and monitors the orchestration layer

- `/_ProjectRootFOLDER/src/ui/`
  - contains `gui_main.py`
  - may contain subfolders for UI helpers, UI components, UI adapters, and other UI-only supporting libraries

- `/_ProjectRootFOLDER/src/core/`
  - contains `engine.py`
  - may contain subfolders for core helpers, internal libraries, managers, services, orchestration helpers, and other core-only supporting modules

- `/_ProjectRootFOLDER/README.md`
- `/_ProjectRootFOLDER/LICENSE.md`
- `/_ProjectRootFOLDER/requirements.txt`
- `/_ProjectRootFOLDER/setup_env.bat`
  - creates and configures the local `.venv` isolated environment
- `/_ProjectRootFOLDER/run.bat`
  - activates or uses the environment and runs `src.app`

- `/_ProjectRootFOLDER/_docs/`
  - contains all project documents other than `README.md` and `LICENSE.md`
  - includes manifests, contracts, TODOs, DEV_LOG, design docs, plans, notes, and related project documentation

### 2.2 Documentation boundary

All project documents other than `README.md` and `LICENSE.md` shall live under:

`/<project_root>/_docs/`

The builder shall treat the contents of these documents as part of the active project reference surface when such documents define design intent, constraints, manifests, contracts, TODOs, or development history.

The builder shall not place junk, scratch debris, throwaway files, or undocumented clutter into the `_docs/` folder.

### 2.3 DEV_LOG rules

The builder shall maintain `DEV_LOG.md` as an append-only development record.

After each meaningful set of updates, section completion, or project phase, the builder shall append a new entry to `DEV_LOG.md` describing what changed, why it changed, and any notable implementation or design decisions.

The builder shall not delete prior log entries.

The builder may overwrite or rewrite an existing log entry only when the user explicitly instructs it to do so, including cases where intentional redaction, correction, or privacy-related replacement is required.

### 2.4 External boundary restrictions

The project shall be treated as a self-contained package intended to be vendored and operated independently.

The builder shall not architect the application so that it requires runtime connection to sibling apps, external project folders, adjacent repositories, or other local tools outside the current project root.

The builder shall not create runtime imports, symlinks, file-path dependencies, or hidden operational coupling to code outside the current project root.

The builder shall not create helper files, support files, generated assets, or sidecar state outside the current project root.

Any approved external logic brought into the project under the borrowing rules must be fully re-homed into the project root and integrated under the ownership, provenance, and dependency rules of this contract.

### 2.5 Environmental dependency rule

The project may assume only normal environmental prerequisites reasonably required to run a Python application on a local computer, including Python itself, the local operating system, and explicitly declared package dependencies.

Beyond such normal environmental constraints, the builder shall avoid introducing unnecessary external dependencies, environmental coupling, or assumptions that make the project dependent on other apps or tools for its basic operation.

## 3. Required Project Layout

The builder shall treat the core project scaffold as mandatory.

Required core structure:

- `src/app.py`
- `src/ui/`
- `src/core/`

This core structure exists to ensure that the application clusters around a clear and stable system model:
- entry and application state,
- user interface,
- backend / engine / orchestration / internal processing,
- and root-level operational files such as installation, environment setup, startup, licensing, and primary project reference files.

The builder shall organize the project so that responsibilities naturally group around these core areas rather than being scattered arbitrarily.

### 3.1 Intent of the scaffold

The scaffold is intended to provide enough structure that the builder can place code into understandable logical groupings without having to invent a new project geometry.

The builder shall use this structure to preserve:
- clarity of arrangement,
- strong grouping of related logic,
- easy human inspection,
- and stable future extension.

### 3.2 Approved top-level folders

Top-level folders beyond the required core structure are permitted when necessary.

Pre-approved examples include, but are not limited to:
- `tests/`
- `assets/`
- `logs/`
- `data/`
- `scripts/`
- `config/`

Approval of these examples does not mean they should always be created. The builder shall create only the folders that are actually warranted by the project’s real needs.

### 3.3 Creation of new top-level folders

The builder may create additional top-level folders when necessary.

However, creation of a new top-level folder shall be treated as a structural decision, not a casual convenience. A new top-level folder is justified only when:
- the responsibility does not cleanly fit under the existing root structure,
- placing it inside an existing approved area would reduce clarity or create mixed ownership,
- and the new folder provides a stable, understandable domain boundary.

The builder shall prefer using the existing scaffold whenever it can cleanly contain the responsibility.

### 3.4 Build in place preference

When the user has already created the scaffold, placeholder files, or project tree in place, the builder shall build directly into that structure.

When the user has provided the scaffold as a declared tree map rather than a pre-created folder tree, the builder may instantiate that scaffold in place before building.

The builder shall not treat scaffold instantiation as license to redesign the project layout beyond what is necessary to realize the declared structure.

### 3.5 Expansion rule

The builder may extend the scaffold conservatively as project needs become concrete.

All expansion shall preserve the original structural intent:
- entry remains entry,
- UI remains UI,
- core remains core,
- root operational files remain root operational files,
- documents remain under `_docs/`,
- and any new structural areas must remain legible as logical systems rather than ad hoc accumulation.

## 4. Ownership Rules

The builder shall enforce strong ownership boundaries across the entire project.

### 4.1 Single-domain rule for logic components

Components of logic shall be single-domain by default.

This includes, but is not limited to:
- micro-services,
- reference libraries,
- modules,
- external classes,
- helpers,
- utilities,
- services,
- and extracted or borrowed logic units.

A logic component shall own one clear domain of responsibility. It shall not mix unrelated concerns or silently absorb neighboring domains for convenience.

Examples of prohibited mixed ownership include:
- UI + business logic in the same owned component,
- storage + rendering in the same owned component,
- orchestration + deep domain implementation in the same owned component,
- or any other arrangement where the component’s true domain cannot be stated cleanly.

### 4.2 Ownership clarity requirement

If the builder cannot clearly state the domain owner of a component, the component is not yet correctly placed.

Unclear ownership shall trigger one of the following actions:
- split the component into smaller owned units,
- relocate it to the proper domain,
- or defer the move until a later phase when ownership can be resolved cleanly.

The builder shall not hide unresolved ownership inside catch-all files, convenience modules, or vaguely named containers.

### 4.3 Manager layer rule

Managers may bridge multiple domains only in a constrained coordination capacity.

A manager may bridge:
- normally no more than 2 domains,
- and at the fringe no more than 3 domains when the clustering is logically tight and clearly justified.

Managers exist to coordinate neighboring responsibilities, not to become mixed-domain implementation sinks.

A manager shall not absorb the full internal logic of the domains it coordinates. It may delegate, supervise, sequence, route, monitor, normalize, or compose behavior, but the owned implementation logic shall remain in the domain components themselves.

If a manager begins accumulating broad implementation behavior from multiple domains, the builder shall split that behavior back into properly owned components.

### 4.4 Orchestrator rule

Orchestrators are strictly bound to either the UI side or the CORE side.

An orchestrator shall not operate as an unbounded project-wide authority spanning arbitrary domains.

Permitted orchestrator alignment:
- UI orchestrators coordinate UI-side systems, UI events, UI state flow, and UI-side delegation
- CORE orchestrators coordinate backend, engine, processing, runtime, and core-side delegation

The builder shall not create free-floating orchestrators that mix UI and CORE ownership into one uncontrolled control surface.

### 4.5 File and module placement rule

The builder shall place files and modules according to ownership and hierarchy rather than convenience.

The physical location of a file shall reflect its position in the system hierarchy. Files shall be placed in the part of the project tree that matches their architectural role.

Examples:
- UI-owned files shall live under UI locations such as `src/ui/` and its approved subfolders
- CORE-owned files shall live under CORE locations such as `src/core/` and its approved subfolders
- root operational files shall remain at the project root
- project documents shall remain under `_docs/`

The builder shall not place a component in one area while conceptually treating it as belonging to another area. Directory placement, ownership, and architectural role should agree unless an explicitly justified bridge or transition layer is being used.

A file may contain multiple tightly related elements only when they clearly belong to the same domain and improve legibility as one coherent unit.

A file shall not become a dumping ground for loosely related helpers or mixed concerns merely because they are small.

### 4.6 Adapters and bridges

Adapters, bridges, and compatibility layers do not become permanent ownership excuses.

If a temporary bridge is required, it shall remain narrow and explicitly transitional in purpose. The builder shall not use adapters to disguise unresolved ownership or to permanently warehouse mixed-domain logic.

### 4.7 General ownership principle

The ownership test is simple:
- a logic component should be explainable as belonging to one domain,
- a manager may coordinate a very small cluster of adjacent domains,
- and an orchestrator must remain bounded to either UI or CORE.

Anything broader than that shall be treated as a structural warning and refactored toward clearer ownership.

## 5. Dependency Rules

The builder shall structure dependency flow around a bounded runtime control graph rooted at `src/app.py` when such a graph is part of the application blueprint.

This contract approves the architectural use of a bounded runtime control graph and constrains how it may support dependency flow, logging discipline, state handling, and clean coordination. The detailed graph design for a given app belongs in that app’s `ARCHITECTURE.md` or equivalent blueprint document.

### 5.1 Composition root rule

`src/app.py` is the application composition root and canonical app-state authority.

It is responsible for:
- maintaining the application state authority,
- bootstrapping the runtime graph,
- registering orchestrators and other approved runtime nodes,
- starting and monitoring the orchestration layer,
- and coordinating root lifecycle behavior.

The builder shall not create competing top-level state authorities outside the app root without explicit user approval.

### 5.2 Runtime control graph model

The application may use a lean runtime graph as an active coordination and state-topology spine.

This runtime graph is approved as a valid architectural substrate when kept bounded and legible.

Its intended role is to provide:
- declared node identity,
- bounded routing,
- controlled message traversal,
- isolated local node state,
- root-owned global state,
- and append-only event logging.

This runtime graph shall be treated as a control graph / state-aware coordination graph, not as an excuse for uncontrolled shared mutation.

### 5.3 Approved prototype graph structure

When the application blueprint calls for a runtime graph, a lean prototype graph architecture is approved in principle with the following structure:

- `Message`
  - the strictly typed data payload vehicle for graph traversal
  - contains sender, target, action, timestamp, and a serializable payload

- `GraphNode`
  - abstract base for isolated application components
  - owns narrow local state
  - communicates outward only through the engine

- `GraphEngine`
  - central routing authority
  - holds root/global state
  - registers nodes
  - defines allowed routes / edges
  - dispatches messages
  - coordinates event logging

- `SQLiteLogger`
  - append-only local event ledger
  - records successfully dispatched messages to local SQLite storage

This prototype is accepted as a lean and structurally valid foundation for the runtime coordination layer.

### 5.4 Graph state rule

The graph may maintain:
- node identity,
- node type,
- edge topology,
- bounded local node state,
- root-owned shared state,
- routing permissions,
- subscriptions or dispatch metadata,
- and event history references.

However, the builder shall not treat the graph as an unbounded dumping ground for arbitrary mutable data.

The preferred state model is:
- canonical app/global state remains rooted under the app authority,
- nodes hold only narrow local operational state,
- shared state is explicitly owned,
- and data objects move between nodes through declared routes.

### 5.5 Message traversal rule

Messages are the approved vehicle for moving intent and serializable data payloads across the runtime graph.

The builder shall prefer explicit message traversal over arbitrary node-to-node mutation or hidden side-channel coupling.

A message route must be declared or permitted by the graph authority before traversal.

The builder shall not allow broad uncontrolled cross-calls that bypass the declared routing structure.

### 5.6 Event ledger rule

A local SQLite-backed append-only event ledger is approved as a lightweight persistence and trace mechanism for successful runtime dispatches.

This event log is valid as:
- a dispatch history,
- a local trace ledger,
- a debugging and inspection aid,
- and a future foundation for stronger event-sourcing behavior.

However, the builder shall not falsely represent append-only event logging as full event sourcing unless replay, reconstruction, snapshotting, reducer semantics, schema evolution, and related state-rebuild mechanics are actually implemented.

### 5.7 Layered routing rule

Dependency and coordination flow should follow the logical hierarchy:
- `app.py` connects to orchestrators,
- orchestrators connect to managers,
- managers connect to owned lower-level parts,
- and lower-level parts do not arbitrarily reach upward or sideways outside approved routes.

The builder shall prefer routing through the declared hierarchy rather than allowing broad peer-to-peer dependency sprawl.

### 5.8 Boundaries and future extension

Additional orchestration layers beyond UI and CORE may be introduced only when a real app need justifies them and their placement remains clear in both hierarchy and file layout.

Any added orchestration layer must remain bounded, named, and structurally legible.

### 5.9 Practical prototype caveat

The approved runtime graph prototype is accepted as a lean but partial state architecture.

It is sufficient as a real foundation for a prototype or first implementation phase, but it does not by itself constitute a complete final state architecture.

If the builder evolves it further, the builder shall later define, as needed:
- mutation authority rules,
- state-slice ownership,
- replay semantics,
- snapshotting,
- sync vs async dispatch boundaries,
- error semantics,
- and schema/version discipline for persisted event payloads.

## 6. Safe Sourcing / Extraction Rules

The builder shall distinguish clearly between the sandbox workspace and the active project build domain.

### 6.1 Sandbox workspace model

The active project folder is a child of the agent-accessible sandbox root.

The sandbox root may contain:
- the current project folder,
- other project folders,
- a `_PARTS/` folder,
- a `_dev_tools/` folder,
- and other sandbox-level files or folders.

The current project folder is the only authorized write domain for the defined project.

The builder may inspect approved reference locations in the sandbox, but it shall write only inside its own current project folder.

Sibling project folders, unrelated root files, and other non-target folders in the sandbox are off limits as build targets for the current project.

### 6.2 Approved reference sources

The builder may use the following sandbox sources for reference, analysis, and bounded extraction subject to this contract:

- `_PARTS/`
  - a curated reservoir of prior projects and logic fragments
  - intended as a reference source for reusable logic, patterns, structures, and specialized implementations

- `_dev_tools/`
  - local development tools already approved for consultation or bounded incorporation according to this contract and related project rules

- approved documents inside the current project's `_docs/` folder
  - these are part of the active project reference surface and may define design manifests, contracts, TODOs, DEV_LOG history, and other project-specific constraints

The builder shall treat these as reference sources, not as implicit runtime dependencies.

### 6.3 Project document location rule

All project documents other than `README.md` and `LICENSE.md` shall live inside:

`/_ProjectRootFOLDER/_docs/`

Examples include but are not limited to:
- `ARCHITECTURE.md`
- `CONTRACT.md`
- `TODO.md`
- `DEV_LOG.md`
- manifests
- design notes
- implementation plans
- migration notes
- source provenance records

The builder shall not scatter project documents outside this location.

### 6.4 Reference-only rule for external sandbox sources

The builder may read from `_PARTS/`, `_dev_tools/`, or other approved sandbox reference sources, but it shall not make the current project depend on them at runtime.

The builder shall not:
- import from them at runtime,
- link to them by path,
- symlink to them,
- treat them as live shared libraries,
- or create hidden coupling that requires them to remain present after the project is vendored.

Any approved logic drawn from these sources must be re-homed into the current project folder.

### 6.5 Preferred sourcing order

When implementing required behavior, the builder shall prefer the following order:

1. original implementation inside the current project
2. bounded rewrite informed by reference material
3. narrow structured extraction of the smallest viable hunk
4. larger transplant only under explicit contract-compliant exception conditions

The builder shall not skip directly to broad copying when a cleaner local implementation or smaller bounded extraction is reasonably feasible.

### 6.6 Bounded extraction rule

When reference logic is needed, the builder shall prefer copying only structured hunks when necessary and only according to the ownership and extraction rules of this contract.

A structured hunk must:
- have clear ownership,
- serve a necessary purpose,
- be bounded enough to understand and maintain,
- and be capable of being re-homed into the current scaffold.

The builder shall avoid pulling in excess surrounding code, unrelated helpers, or broad dependency chains merely because one useful fragment exists nearby.

### 6.7 Full-component or full-script exception

The builder may copy parts of or whole scripts only under strict exception conditions already established in this contract.

This exception exists for cases such as:
- highly customized mathematics,
- specialized logic whose correctness depends on preserving exact structure,
- tightly interdependent components that cannot be safely rewritten without material risk,
- or other rare cases where bounded extraction would damage correctness.

Even under exception conditions, the builder shall still prefer the smallest viable borrowed unit unless preserving the larger structure is itself necessary for correctness.

### 6.8 Re-homing and cleanup rule

Any borrowed or extracted logic incorporated into the current project shall be:
- re-homed into the local project tree,
- placed according to ownership and hierarchy,
- renamed or reorganized when needed to fit the local scaffold,
- cleaned of unrelated debris,
- stripped of accidental dependency on its old environment,
- and brought into high compliance with this contract.

The builder shall not copy external code verbatim into the project and leave it structurally foreign, dangling, or dependent on its original surroundings unless exact preservation is itself the justified condition for correctness.

### 6.9 Provenance recording rule

When logic is extracted, transplanted, or materially informed by sandbox reference sources, the builder shall record provenance in project documentation under `/_ProjectRootFOLDER/_docs/` and shall append an implementation note to `DEV_LOG.md` when the change is meaningful.

The provenance record should identify, as appropriate:
- source location,
- borrowed unit or component,
- destination owner,
- reason borrowing was necessary,
- whether the logic was rewritten, extracted, or transplanted,
- and any cleanup or compliance adjustments performed.

### 6.10 Off-limits write rule

The builder shall not modify `_PARTS/`, `_dev_tools/`, sibling project folders, or any other non-target sandbox contents as part of building the current project.

The builder’s write authority for the defined project is confined to its own project folder only.

## 7. Dev Tool Reference Rules

The builder may use `_dev_tools/` as both a reference reservoir and a practical development-assistance reservoir, subject to the constraints of this contract.

For clarity, `_dev_tools/` exists at the sandbox-root level, not inside the current project root. It is a shared sandbox tooling area and remains outside the active project’s write boundary except when the tool-legacy/shared-utility rule explicitly justifies placing or improving shared tools there.

### 7.1 Approved use of `_dev_tools/`

The builder may:
- inspect dev tools for reference,
- use dev tools during development when they save time or tokens,
- copy dev-tool logic in part or in whole when the copied structure complies with the established ownership, dependency, sourcing, and boundary rules,
- and derive new local tools inspired by patterns found there.

The builder shall not treat `_dev_tools/` as a permanent runtime dependency for the finished vendorable project.

### 7.2 Copy / transplant rule for dev tools

Logic from `_dev_tools/` may be copied in part or in whole only when the copied structure complies with the established project rules.

Any such copied or transplanted logic must:
- be re-homed into the current project,
- fit the local scaffold,
- obey ownership and hierarchy rules,
- avoid hidden dependency on the original tool environment,
- and remain bounded to the current project’s allowed operational domain.

### 7.3 Tool-building encouragement rule

The builder is explicitly encouraged to create new local tools when doing so improves token efficiency, reduces repeated manual work, or makes recurring project operations more reliable.

Awareness of token efficiency should be a primary driver in deciding whether to create a new helper tool.

The builder should prefer creating a local reusable tool over repeatedly spending large amounts of context or tokens on the same mechanical task.

### 7.4 CLI accessibility rule

Any newly created tool intended to handle repeated tasks shall provide command-line access so that any agent working within the project can invoke it consistently.

CLI accessibility is required for reusable project tools unless the user explicitly approves another interface pattern.

### 7.5 Project-local effect rule

Any tool used or created for the project shall have effects confined to the current project folder unless the user explicitly authorizes a wider scope.

The builder shall not create tools that modify, scan, patch, or otherwise affect files outside the current project folder as part of the normal project workflow.

### 7.6 Local helper model rule

The builder may create or use local agentic helper tooling, including tooling that invokes local Ollama models or similar local inference helpers, when doing so supports repeated task execution, token efficiency, or bounded automation.

Such helper usage is encouraged when it remains fully compliant with this contract.

### 7.7 Hardware and inference budget rule

The builder shall respect the user’s system limits when using or creating local helper-model workflows.

Preferred limits:
- no local helper models above approximately the 4B parameter threshold,
- no more than approximately 4k tokens per inference cycle for agentic helpers,
- and no workflows that materially exceed the user’s practical system capabilities.

The builder shall not design helper workflows that assume unrealistic compute, context, memory, or model size relative to the user’s system.

### 7.8 Documentation rule for project tools

When the builder creates or materially incorporates a development tool for the project, it shall document the tool under the project documentation area and append a meaningful entry to `DEV_LOG.md`.

This documentation should identify:
- the tool’s purpose,
- its scope of effect,
- its CLI entry pattern,
- any model or runtime assumptions,
- and any important operational constraints.

### 7.9 Tool legacy / shared utility rule

This rule is an explicit narrow exception to the normal project-root-only write boundary.

If the builder creates or improves a development tool that is useful beyond the immediate local project step, it may place or update that tool in the sandbox `_dev_tools/` area for future agents to use, provided doing so remains bounded, intentional, and clearly documented.

The builder shall not use this exception as an excuse for unrelated edits, broad sandbox changes, or uncontrolled write activity outside the current project.

If the builder creates a development tool that is useful beyond the immediate local step, it should leave that tool behind in the sandbox `_dev_tools/` area for future agents to use, provided doing so is appropriate and does not violate project boundaries or user intent.

Such tools must be clearly marked up with enough instructions and tool metadata that another agent can discover what the tool is, how to invoke it, what scope it operates on, and what constraints apply.

If the tool is multifile, the builder shall place it in an appropriate isolating subfolder under `_dev_tools/` so the tool remains self-contained and legible. More robust instruction `.md` files may be created there when warranted.

Entry points and usage of tools must always be clear.

If existing tools in `_dev_tools/` are not clearly marked, the builder should, when appropriate, improve tool metadata, usage discoverability, or instructions. If immediate rectification is not appropriate, the builder should record the issue in a `TODO.md` inside `_dev_tools/`.

### 7.10 Same-core-rules principle

This documentation should identify:
- the tool’s purpose,
- its scope of effect,
- its CLI entry pattern,
- any model or runtime assumptions,
- and any important operational constraints.

### 7.9 Same-core-rules principle

`_dev_tools/` is a privileged and useful source, but it is not exempt from the project’s core architectural rules.

All logic derived from `_dev_tools/` remains subject to:
- root boundary rules,
- ownership rules,
- dependency rules,
- safe sourcing rules,
- code quality rules,
- and prohibited behavior rules.

## 8. Support File Proposal Rules

The builder may create new files and folders as needed when doing so is in accordance with the established rules of this contract.

New file creation is expected to occur when it is the cleanest way to preserve ownership, reduce fragility, and maintain legible structure.

### 8.1 General creation rule

The builder may add support files or support folders whenever they serve a real structural need and align with the ownership, hierarchy, dependency, and boundary rules already established.

The builder shall not avoid creating a needed file merely to appear minimal if doing so would create mixed ownership, hidden complexity, or fragile code.

### 8.2 Balance rule

All files should aim for a balance of:
- minimality,
- non-fragility,
- cleanliness,
- efficiency,
- and clarity to other agents.

The builder shall not pursue extreme minimalism when it causes brittleness, nor excessive decomposition when it creates needless sprawl.

### 8.3 Purpose and placement rule

When the builder creates a new file or folder, its purpose and placement must be clear.

A new file or folder should exist because:
- it owns a real responsibility,
- it preserves domain clarity,
- it keeps the hierarchy legible,
- or it cleanly isolates a tool, subsystem, data area, asset area, or support concern.

### 8.4 Markup and metadata rule

Files should communicate clearly to other agents what they are and how they fit into the project.

The builder should use light but meaningful markup, headers, metadata, docstrings, or other in-file cues where appropriate so that purpose, ownership, and usage are understandable.

However, the builder shall not over-bloat scripts with excessive metadata, repetitive headers, or documentation volume that materially complicates the code.

The goal is enough clarity to orient future agents without turning code into documentation-heavy clutter.

### 8.5 Temporary and dead-file cleanup rule

The builder has an active duty to clean up temporary files, unused dead files, obsolete scratch artifacts, and similar debris when such cleanup can be performed safely.

Cleanup must be performed conservatively.

The builder shall not prune files casually or aggressively when there is material uncertainty about whether they are still needed.

The builder should prefer safe identification of removable items through:
- clear naming,
- known temporary status,
- explicit replacement history,
- lack of active references,
- or documented obsolescence.

When uncertainty remains, the builder should preserve the file, relocate it to a clearly marked holding area if appropriate, or record the cleanup candidate in project documentation rather than risk erroneous deletion.

### 8.6 No-error-prune rule

Nothing should be pruned by accident.

Before deleting or pruning a file or folder, the builder should have a reasonable basis to conclude that:
- the item is temporary, obsolete, unused, replaced, or intentionally disposable,
- removing it will not break the project,
- and the deletion aligns with the user’s intent and project history.

If that basis does not exist, the builder shall not delete the item.

### 8.7 Cleanup documentation rule

Meaningful cleanup actions, especially pruning of unused files or structural reorganization, should be recorded in `DEV_LOG.md` and, when warranted, in supporting project documentation under `_docs/`.

This is especially important when files were superseded, intentionally removed, or replaced by new structure.

## 9. Code Quality Rules

The builder shall produce code that is clean, inspectable, robust under interruption, and compatible with the runtime state/control graph architecture.

### 9.1 Logging instead of print rule

There is no general excuse for `print()`-based debugging or operational output in the application.

The builder shall use proper logging infrastructure rather than ad hoc print statements.

This requirement is strengthened by the presence of the runtime graph, central app authority, and structured event/state mechanisms, all of which make proper logging more practical and more valuable.

`print()` may be used only in narrowly justified one-off tooling or explicitly throwaway contexts when the user has not required logging discipline there. It shall not be used as a substitute for real application logging.

### 9.2 Full logging rule

The builder shall implement full logging appropriate to the project scope.

Logging should support:
- startup and shutdown visibility,
- major lifecycle transitions,
- orchestration actions,
- manager-level coordination events,
- errors and warnings,
- meaningful state changes where appropriate,
- tool execution when relevant,
- and cleanup / migration / structural actions when significant.

Logging should be structured and useful rather than noisy spam.

### 9.3 Graceful failure rule

Failures shall happen gracefully.

The builder shall prefer controlled failure handling, clear error reporting, and safe degradation over abrupt unexplained crashes.

Graceful failure includes, where appropriate:
- clear exception handling at suitable boundaries,
- meaningful logs,
- preservation of useful diagnostics,
- safe shutdown paths,
- and avoiding corruption of state, files, or active workflows.

### 9.4 Testing and task-checklist rule

The builder shall use robust testing and temporary task checklists to support reliable execution.

Tests should be used to verify meaningful logic, especially new or changed behavior.

Task checklists should be used to track work that may be interrupted so that progress can be resumed cleanly by reading the recorded checklist state.

This is especially important in agentic or token-limited workflows where interruptions, context loss, or partial completion are realistic risks.

### 9.5 Central configuration rule

Configuration should be centralized.

The builder shall prefer a clear central configuration model over scattered ad hoc settings.

The runtime graph and state registry should be used to make configuration handling clearer rather than more diffuse.

Configuration values should be discoverable, intentionally owned, and easy to inspect or update.

### 9.6 Hidden globals and magic constants rule

The builder shall avoid hidden globals and unexplained magic constants.

Shared state, mutable operational settings, and important cross-cutting values should not be smuggled into the codebase through accidental module globals or hard-coded values with unclear meaning.

Constants should be named, owned, and placed where their role is legible.

If a constant materially affects behavior, routing, thresholds, limits, timing, paths, or protocol expectations, the builder should make it explicit and understandable.

### 9.7 Type and schema discipline rule

The builder shall prefer typed structures where they materially improve clarity, safety, and maintainability.

Typed configuration objects, typed message payload envelopes, typed state slices, dataclasses, or similarly clear structured models are encouraged when they help define stable contracts between parts of the system.

The builder should not introduce heavy type ceremony for its own sake, but it should use typing deliberately where structure matters.

### 9.8 Documentation and metadata balance rule

The builder should include enough docstrings, inline guidance, headers, or metadata to clarify the purpose and usage of meaningful public-facing or structurally important code.

However, the builder shall avoid over-documenting trivial internal details in ways that bloat and clutter the code.

The objective is operational clarity, not documentation theater.

### 9.9 Structural quality principle

Code quality is not only syntax quality.

The builder shall treat the following as part of code quality:
- ownership clarity,
- stable file placement,
- clean routing,
- explicit state handling,
- safe cleanup,
- testability,
- recoverability after interruption,
- and legibility to future agents and the user.

## 10. Reporting / Phase Output Rules

The builder shall maintain clear phase-level reporting through project documentation, primarily using `DEV_LOG.md` and `TODO.md` under the project `_docs/` folder.

### 10.1 DEV_LOG format rule

`DEV_LOG.md` shall function as the append-only execution ledger for meaningful work phases.

Each new entry should be:
- date stamped,
- time stamped,
- and include a meaningful entry identifier.

Each entry shall record:
- the files changed,
- a short but complete summary of what changed,
- and any materially relevant implementation note.

Summaries must remain concise, but they shall not use cut-off shorthand such as `...` in place of omitted meaning.

### 10.2 File-change recording rule

The builder shall record all files changed for a meaningful work phase.

This should include created, modified, relocated, or deleted files when such changes are part of the phase.

The goal is for another agent or the user to reconstruct what was touched without ambiguity.

### 10.3 Testing report rule

The builder shall record meaningful testing activity at the phase level, but it does not need to list every individual test name or every passing result in the dev log.

Normal successful test activity may be summarized compactly.

If failures are persistent, significant, blocking, or diagnostically important, the builder should record more detail.

### 10.4 Tool-usage metrics rule

The builder should track tool usage metrics when meaningful.

This includes, as appropriate:
- tools used,
- tools created,
- repeated-task automation employed,
- or other significant efficiency-relevant tooling activity.

Tool usage should be recorded compactly but clearly enough to understand how work was performed.

### 10.5 TODO ownership rule

Unresolved issues, deferred work, next steps, and deferred cleanup items belong in `TODO.md`.

`TODO.md` is the operational backlog / continuation surface.

The builder should place into `TODO.md`, as appropriate:
- unresolved issues,
- blocked items,
- deferred cleanup,
- follow-up steps,
- risks to revisit,
- and pending structural corrections.

### 10.6 Cleanup reporting rule

If cleanup was performed and is materially relevant, the builder should note it in `DEV_LOG.md`.

If cleanup remains needed and was not performed, that deferred cleanup should be recorded in `TODO.md`.

### 10.7 Reporting principle

The reporting system should preserve:
- continuity across interrupted work,
- clear traceability of changes,
- concise but non-truncated summaries,
- and a clean separation between completed history (`DEV_LOG.md`) and pending work (`TODO.md`).

## 10.8 Decision Priority and Pushback Rule

The builder’s job is not mere compliance theater and not blind obedience to every user impulse.

The builder’s job is to produce the strongest, cleanest, most maintainable application reasonably achievable within the project goals, blueprint, and contract.

Accordingly, decision priority shall be:

1. preserve correctness, structural integrity, and long-term maintainability,
2. preserve contract compliance and bounded architecture,
3. preserve the real intent of the user’s goal,
4. prefer the cleanest effective implementation,
5. prefer token-efficient and repeatable workflows,
6. satisfy surface-level preferences only when they do not materially damage the system.

If the user requests something that appears structurally unsound, unnecessary, contradictory, maladaptive, overly fragile, or likely to damage the quality of the application, the builder should not simply comply.

Instead, the builder should:
- push back clearly,
- verify the underlying intent,
- warn about likely consequences,
- explain the tradeoff or structural cost,
- and when appropriate propose a stronger alternative.

The builder should treat magnitude seriously. The worse the likely consequence of a proposed user decision, the more explicitly the builder should surface the risk.

However, pushback should remain grounded, technical, and aimed at making the best application possible rather than resisting for its own sake.

## 11. Prohibited Behaviors

This section summarizes prohibition logic, but prohibitions are distributed throughout the entire contract. The builder shall not interpret this section as limiting prohibitions only to the examples listed here.

Prohibited behaviors are established throughout this contract by the rules already stated.

Any action explicitly disallowed by the sections of this document is prohibited.

### 11.1 Contract-first prohibition rule

The builder shall treat the constraints in this document as the primary authority for what is forbidden.

If a behavior violates the mission, root boundary rules, ownership rules, dependency rules, sourcing rules, tooling rules, support-file rules, code-quality rules, or reporting rules, that behavior is prohibited.

### 11.2 Non-listed behavior rule

If a behavior is not explicitly authorized by this contract, it shall be treated as a possibility requiring user approval before the builder proceeds.

Silence in the contract is not blanket permission for structural deviation, risky behavior, boundary crossing, or architecture changes.

### 11.3 Approval gate rule

When the builder encounters an action that is not clearly covered by the contract and that could materially affect structure, boundaries, dependency, sourcing, tooling scope, cleanup, or long-term maintainability, it should pause that action, surface it clearly, and seek user approval.

### 11.4 General prohibited examples

Without limiting the broader rules already established, prohibited behavior includes examples such as:
- writing outside the current project folder when not explicitly authorized,
- creating runtime dependency on `_PARTS/`, `_dev_tools/`, or sibling projects,
- hiding mixed ownership inside convenience files,
- using print statements in place of proper application logging,
- deleting files recklessly or without sufficient basis,
- leaving copied logic structurally foreign and unowned,
- introducing hidden globals or unexplained magic constants,
- creating unclear tool entry points,
- or silently bypassing the declared hierarchy and routing model.

These examples do not replace the contract; they illustrate it.

