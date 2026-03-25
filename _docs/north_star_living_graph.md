# North Star: Living Graph as the Main Brain

_Version 1.0 — recorded 2026-03-23. Do not build until the TODO list is complete._

---

## Core Insight

**Graph = persistent typed cognition. Model = bounded fast operator on subgraphs.**

4–9B models cannot hold a full project in context. But they can reason sharply over
a bounded, well-typed subgraph. The navigation policy decides which subgraph to hand
to the model next.

This is the difference between:
- A model that re-reads everything each turn (wasteful, context-limited)
- A model that navigates a persistent graph (efficient, composable, scalable)

---

## Node Types

| Type | Description | Example |
|------|-------------|---------|
| `Task` | Something to do, has status (pending/active/done/blocked) | "Refactor session store" |
| `Hypothesis` | Belief about the system that may need validation | "The bug is in PromptBuilder line 80" |
| `Decision` | A choice that was made with its rationale | "Use SQLite over JSON for session store" |
| `Evidence` | A fact gathered from the workspace or user | "sessions.db exists at .mindshard/sessions/" |
| `Plan` | Ordered list of tasks with dependencies | "Phase 1: extract, Phase 2: wire, Phase 3: verify" |

Nodes have:
- `id` (UUID or semantic slug)
- `type` (from enum above)
- `content` (text)
- `status` (type-specific: pending/done/blocked for Task, confirmed/refuted for Hypothesis)
- `created_at`, `updated_at`
- `edges` (list of typed relationships to other nodes)

Edge types:
- `depends_on` (Task → Task)
- `supports` (Evidence → Hypothesis)
- `refutes` (Evidence → Hypothesis)
- `produced_by` (Evidence → Task that gathered it)
- `sub_task_of` (Task → Plan)
- `decided_by` (Decision → Hypothesis or Task)

---

## Navigation Policy

The navigation policy answers: **which subgraph does the model see next?**

### Rules (priority order)

1. **Active task first** — show the current active `Task` node, its evidence,
   its blocking dependencies, and its parent plan context
2. **Unresolved hypotheses** — if the active task has linked hypotheses that are
   `pending`, surface them for validation
3. **Recent decisions** — last 3 decisions in the current plan branch, for coherence
4. **Relevant evidence** — top-K evidence nodes by semantic similarity to the active task
5. **Fallback: full plan skeleton** — if no active task, show all Task nodes at
   "pending" status (status map only, not full content)

The subgraph handed to the model is bounded to ~2000 tokens by default. If the
navigation policy selects more, trim by priority (rule 1 is untrimmed).

---

## Graph-Based Thought-Chain Loop Design

This is the `thought_chain` loop mode, which replaces the flat `thought_chain`
placeholder with a structured graph operator.

### Turn Sequence

```
User prompt
    │
    ▼
[graph_navigator] ──→ selects relevant subgraph (active task + evidence + decisions)
    │
    ▼
[model] ──→ receives subgraph + user prompt, produces one of:
              (a) NEW_TASK {content, parent_plan}
              (b) UPDATE_TASK {id, status}
              (c) ADD_EVIDENCE {content, task_id}
              (d) FORM_HYPOTHESIS {content, task_id}
              (e) RESOLVE_HYPOTHESIS {id, verdict, evidence_ids}
              (f) MAKE_DECISION {content, rationale, task_id}
              (g) FINAL_ANSWER {content}
    │
    ▼
[graph_writer] ──→ applies the model's operation to the graph, persists
    │
    ▼
[if not FINAL_ANSWER] ──→ loop back to graph_navigator
[if FINAL_ANSWER] ──→ return to user
```

The model never sees the full graph. It only sees the subgraph the navigator selects.

### Merge-Back

When two plan branches are running (e.g. two sub-tasks in parallel):
1. Both branches gather evidence into their own subgraph
2. A `merge_node` is created that is `depends_on` both branches
3. The navigator switches to the merge context: shows both branches' decisions
4. The model produces a `MAKE_DECISION` that reconciles them
5. The merged decision is added as evidence to the parent plan

This is how the graph handles parallel exploration without a quadratic context cost.

---

## Why This Works for 4–9B Models

| Problem | Without graph | With graph |
|---------|--------------|------------|
| Context overflow | Must trim aggressively | Navigator bounds subgraph |
| Lost reasoning | Reasoning disappears from STM | Persisted as graph nodes |
| Plan drift | No persistent plan, rediscovers each turn | Task nodes track status |
| Parallel branches | Context mixes, model gets confused | Separate subgraphs, merge node |
| Evidence retrieval | RAG hits raw text, no structure | Evidence nodes are typed, graph-linked |
| Hypothesis validation | Model has to re-ask | Hypothesis nodes track verdict |

---

## Implementation Path (When Ready to Build)

### Phase G1: Graph Schema + Navigator (no model yet)
- `src/core/graph/graph_store.py` — SQLite-backed graph (nodes + edges)
- `src/core/graph/node_types.py` — Task, Hypothesis, Decision, Evidence, Plan
- `src/core/graph/navigator.py` — subgraph selection algorithm
- Tests: can create nodes, add edges, select subgraph given active_task_id

### Phase G2: Model Output Parser
- `src/core/graph/graph_op_parser.py` — parses model's structured output into
  one of the 7 operation types
- The model needs a prompt section that teaches it the output format
- `_docs/agent_prompt/70_graph_operations.md` — teaches op format

### Phase G3: Loop Integration
- `src/core/agent/loops/graph_thought_chain_loop.py` — the new loop
- Register it in `loop_registry.py` as `"thought_chain"` (replaces placeholder)
- Wire navigator → model → parser → graph_writer → loop

### Phase G4: UI Explorer (optional)
- Visualize the active graph in a tab: node list, edge map, status badges
- This is Phase 4 territory — build the loop first, then visualize

---

## Phase G3+ Design Note: The 4th Vertex — FFN Routing Layer

_Concept surfaced 2026-03-23. Do not build until G1–G3 are live and producing retrieval data._

### The Idea

The current hypernode has three faces (vertices):
- **CIS** — structural/relational representation
- **DAG** — causal/dependency edges
- **Vector** — semantic embedding

The 4th vertex is a small feed-forward network (FFN) trained to answer:
**"Given this query context, which of my three faces should I present?"**

The FFN routes to: structural layer (CIS), verbatim layer (exact text), or semantic layer (Vector).

### What This Does to the Hypergraph

**1. New edge class — routing edges.**
The hypergraph currently has content edges (DAG relationships) and similarity edges (vector
proximity). The FFN vertex introduces a third class: *presentation edges* — intra-node edges
from the FFN to each of its three faces. These are not relational edges between nodes;
they are access-policy edges *within* a node. The hypergraph becomes heterogeneous in a new dimension.

**2. The graph acquires distributed parameters.**
Every hypernode now contains trainable weights. The hypergraph is no longer a pure symbolic
structure — it is a hybrid knowledge-model structure. Each node becomes a micro-expert.
This is Mixture-of-Experts at the retrieval layer: the nodes are the experts, the FFN router
is the gating network — but unlike standard MoE, the gate lives at the node level rather than
the model level.

**3. Query propagation changes character.**
In the G1–G3 design, traversal walks the graph and accumulates content from whichever faces
the retrieval system requests. With per-node FFN routers, traversal becomes a series of
query-conditioned negotiations: each visited node decides independently what to surface.
The path through the graph produces a *learned projection* of the graph's content, not a
fixed structural slice of it.

**4. The payoff for 4–9B models.**
Small models are poor at meta-reasoning about retrieval:
"Should I ask for the structural relationship here or the verbatim text?"
That question costs tokens and the model often answers wrong.
The FFN router externalizes that decision into the graph itself. The model receives
pre-routed content — the node has already decided which face is most relevant for this
query context. The model's context window gets higher-quality signal with less wasted inference.

**5. The routing decision moves inside the node.**
The architectural inflection: the graph stops being passive. Each node becomes an active
participant in deciding how it is accessed. The hypergraph develops a learned presentation
layer that is separate from — and adaptive relative to — its underlying content structure.

### Training Signal (Unsolved)

The FFN needs a signal to learn from. Three candidates:

| Signal | Mechanism | Notes |
|--------|-----------|-------|
| Retrieval outcome | When face X retrieval → correct answer, label that routing positively | Requires feedback loop from answer quality → node weights |
| Self-supervised layer prediction | FFN learns which face is most compressed representation for a query type | Information-theoretic, no external feedback needed |
| Contrastive | Query pairs that should route to different faces; FFN learns the boundary | Needs labeled query pairs by retrieval intent |

The RL/outcome-based signal is cleanest architecturally but requires a non-trivial
feedback loop from model answer quality back to node FFN weights.
The self-supervised approach is buildable without that loop — a reasonable starting point.

### Implementation Order

Do not add this until:
1. G1–G3 are live (graph is storing nodes, navigator is selecting subgraphs, model is operating on graph)
2. Retrieval logs show consistent patterns of which face is most useful per query type
3. Those patterns justify the FFN training overhead over a rule-based routing heuristic

The FFN vertex is Phase G4+ work. A rule-based routing heuristic (semantic query → vector,
structural query → CIS/DAG, exact-match query → verbatim) may be sufficient for G3.
Collect data before committing to learned routing.

---

## Relationship to Existing Evidence Bag

The evidence bag (manifold NodeStore) is the **session-scoped retrieval layer**.
The living graph is the **turn-scoped reasoning layer**.

They coexist:
- Evidence nodes in the graph reference documents in the evidence bag by node_id
- When the navigator selects evidence nodes, it can hydrate their content from the bag
- The bag is the filing cabinet; the graph is the whiteboard

This means: graph nodes can be small (IDs + metadata), bag stores full text.
The navigator decides how much to hydrate.

---

## What Makes This Different from Just Using STM

STM is a sliding window of turns — it's temporal, not structural. The model sees
the last N exchanges but has no concept of whether something was resolved, decided,
or is pending.

The graph is structural — it knows which tasks are done, which hypotheses were
confirmed, which decisions were made. The navigator can skip resolved nodes
entirely and focus the model on what's still open.

Combined:
- STM provides temporal coherence (what happened recently)
- Graph provides structural coherence (what's the state of the plan)
- Evidence bag provides semantic retrieval (what did we learn that's relevant)

---

## North Star Summary

> The agent navigates a typed graph of tasks, evidence, decisions, and hypotheses.
> Each turn, the navigation policy selects a bounded subgraph. The model reads the
> subgraph, produces a typed operation, the graph is updated, and the cycle repeats.
> The model never needs to re-read history — the graph IS the persistent reasoning.
>
> For 4–9B models, this is the path to non-trivial multi-session work that doesn't
> degrade with scale.
