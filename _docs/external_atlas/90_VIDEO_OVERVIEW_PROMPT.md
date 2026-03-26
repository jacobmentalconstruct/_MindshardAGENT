# 90 Video Overview Prompt

Use the following prompt to generate a forensic deep-dive video overview of MindshardAGENT.

```text
Create a forensic deep-dive video overview of MindshardAGENT for a technically serious audience.

Perspective summary:
MindshardAGENT is not a chatbot shell. It is a local agent workbench for real project-building, with a visible desktop interface, a loop-based runtime, controlled tool execution, project-local sidecar state, prompt inspection, persistent session memory, and a separate Prompt Lab subsystem for prompt/execution design. Explain it as a machine made of cooperating subsystems, state transitions, and boundaries. Favor mechanistic clarity over hype: what starts where, what owns what, what data moves where, what gets persisted, what is allowed to affect runtime, and why those distinctions matter. Treat the audience as smart but unfamiliar with the project’s internal language. Translate jargon as you go. Emphasize both how the app works and what that workflow unlocks for a serious builder.

- Open by reframing the app completely: this is not “chat with an AI,” it is a project-attached agent workstation. Show the UI as a control room for live building, inspection, and orchestration.

- Establish the main promise to the user early: instead of bouncing between a terminal, docs, scratch notes, prompt files, and disconnected agent sessions, the user gets one local operating environment where project context, prompt state, runtime behavior, and tooling can stay coherent over time.

- Show the top-level architecture early: main app shell, engine runtime, UI layer, sandbox/tool system, project lifecycle system, session/knowledge layer, Prompt Workbench, Prompt Lab, MCP/server surfaces, and storage layers. Make it clear the app is large because it integrates many real capabilities, not because it is unfocused.

- Walk through startup as a real system boot sequence: `app.py` -> `app_bootstrap.py` -> config, logging, engine, session/knowledge stores, window, UI facade, bridge, Prompt Workbench summary, then Tk mainloop. Highlight that startup and shutdown were deliberately decomposed into owned lifecycle flows.

- Explain project attachment as one of the central ideas in the app. Show how the system “locks onto” a workspace: sandbox root, project metadata, session store, knowledge store, prompt state, and Prompt Lab summary all rebind to the attached project. Portray this as the point where the agent stops being abstract and starts becoming project-specific.

- Show the user workflow in practical terms: attach a project, inspect project state, start a session, submit work through the chat surface, watch the runtime log, inspect prompt state, use tools, branch or save sessions, and stay inside one coherent operating environment instead of restarting context every time.

- Walk through a live prompt submission mechanistically: UI submit -> app streaming layer -> engine -> loop manager -> selected loop -> tool routing if needed -> structured result -> session/history update -> UI refresh. The viewer should understand the flow as an execution pipeline, not just “the model answered.”

- Showcase the loop system as a core innovation in workflow. Explain that the app is not locked to one response style: direct chat, planner-only, thought-chain, review, and recovery are structured execution paths. Emphasize how this gives the user different ways to work with the agent depending on task shape and risk.

- Explain how this changes the user/agent relationship: the user is not merely asking questions; they are directing an attached runtime that can plan, inspect, recover, review, and act inside a project boundary. Show that the workflow can support iterative building rather than isolated one-off responses.

- Highlight tool use carefully and honestly. Portray the system like a power-tool bench: deeply useful, deeply capable, and potentially project-affecting. Explain command policy, path guards, tool discovery, and local execution boundaries. This should feel serious and mature, not fear-based.

- Show the Prompt Workbench inside the main app as the live inspection bridge: compiled prompt, source stack, prompt-related diagnostics, and Prompt Lab summary. Explain that this gives the user visibility into what the model is actually seeing, which is rare and extremely valuable in agent systems.

- Then pivot to Prompt Lab as the major conceptual expansion. Explain that instead of cramming a full prompt-engineering suite into the main app shell, the system created a separate Prompt Lab workbench. Frame this as a design decision that preserves clarity, isolation, and long-term scalability.

- Explain Prompt Lab in terms of user workflow potential: prompt profiles, execution plans, bindings, validation, promotion, evaluation, and packages. Show that the user is moving from “editing prompts” to “designing agent behavior” with explicit control over both language and process.

- Make the prompt/process split extremely clear. Prompt wording and execution structure are separate things. Bindings connect them explicitly. This is one of the deepest ideas in the system and should be presented as a major unlock for serious agent engineering.

- Explain the active/published/draft model as a protection against chaos. The user can experiment in Prompt Lab without automatically destabilizing live runtime behavior. This unlocks safer iteration, rollback, comparison, and disciplined experimentation.

- Spend time on the storage/truth model because it unlocks reliability. Show the separation between builder memory in the app journal, project-local runtime state in `.mindshard`, Prompt Lab design state in `.mindshard/prompt_lab`, and active published Prompt Lab runtime state. Explain that this makes the system more inspectable, more debuggable, and more evolvable.

- Highlight the app journal briefly as part of the larger workflow paradigm. The system is not only persisting runtime data; it is also persisting development continuity, doctrine, TODOs, work logs, and onboarding knowledge. Show how this lets the builder and future agents retain architectural continuity across long-running work.

- Cover the integration seams as the load-bearing joints of the machine: app layer to engine, project lifecycle to runtime state, Prompt Workbench bridge to Prompt Lab, runtime loader to active published state, and transcript/tool-call separation. Explain that these seams are where reliability is won or lost.

- Include what this unlocks for advanced users. The app makes it possible to build with an agent in a way that is session-aware, project-aware, tool-aware, prompt-aware, and increasingly workflow-aware. It supports a style of work where the agent can become a sustained build partner instead of a disposable answer engine.

- Explain what it unlocks for future agents too. Because the system has explicit records, structured storage, subsystem docs, Prompt Lab state, and journal memory, a future agent can reason over slices of the system instead of needing the whole raw codebase at once. This is a major scalability advantage.

- Show why the system feels different from most agent products: it is unusually inspectable, unusually local, unusually explicit about state, and unusually honest about the difference between experimentation and runtime truth. Those qualities should be highlighted as strengths.

- End on the current frontier. The infrastructure is now real: runtime, Prompt Lab, bridges, storage, and inspection surfaces exist. The next evolution is authoring real prompt/execution packages and using the system to intentionally shape behavior, compare outcomes, and teach the runtime how to work better over time.

- Add a visual systems map section that portrays the app as a layered graph: UI shell at the top, app-layer orchestration beneath it, engine and core subsystems below that, and storage/truth layers at the bottom. Use arrows and grouping to make the architecture legible at a glance.

- Add a data-flow segment showing one user request as a traced path through the machine. Visualize the request entering the UI, becoming a loop request, touching prompt build state, possibly invoking tool routing, updating history/session state, and then returning to the UI as a rendered result.

- Add a state-transition segment focused on project attachment and detachment. Show before/after diagrams of what changes when a project is attached: sandbox root, metadata, sessions, knowledge store, prompt state, Prompt Lab summary, and runtime focus.

- Add a truth-model visualization using separate colored lanes or boxes for builder memory, project runtime sidecar state, Prompt Lab design state, and active published runtime state. The goal is to show that the system remains sane because these truths are separated, not blended.

- Add a Prompt Lab package visualization that shows prompt profiles, execution plans, bindings, validation state, publication, and activation as related records rather than vague settings. This should feel like a small operating graph or package graph, not a form screen.

- Add a seam-analysis segment that explicitly highlights where old and new structures meet. Use edge or bridge visuals to show why these join points are the most important places to audit, harden, and understand.

- Add a workflow-potential segment that shows how the app supports compounding work over time: a user attaches a project, runs sessions, accumulates history, inspects prompts, iterates in Prompt Lab, publishes a package, re-enters the main app, and continues building from a better operational baseline.

- Add a future-evolution segment with tasteful graph/manifold-style visuals that hint at where the system can grow next: richer authored packages, deeper evaluation, more explicit behavioral shaping, and future graph-capable execution design. Present this as an emerging structured design space, not as marketing fantasy.

Style notes:
Use mechanistic explanation, layered system thinking, and precise causal language.
Prefer “this subsystem owns...”, “this transition rebinds...”, “the runtime consumes only...”, “this seam prevents...”, “this workflow unlocks...” over vague product language.
Do not oversimplify.
Do not use internal shorthand without translating it.
When possible, connect visible UI moments to underlying ownership, state transitions, and user/agent workflow consequences.
Encourage granular detail and concrete explanations of logic.
```
