# 50 Glossary

## Purpose

This glossary translates project-specific vocabulary into externally understandable terms.

## Main App

The primary desktop interface where live agent interaction happens.

## Prompt Workbench

The prompt-facing inspection area inside the main app.
It shows prompt-related summaries and inspection surfaces.
It is not the same thing as Prompt Lab.

## Prompt Lab

A separate subsystem and dedicated workbench for prompt/execution design and related inspection.
It is intentionally separated from the main app shell.

## Sandbox Root

The currently attached project/workspace root the app is operating against.

## Sidecar

The `.mindshard/` directory inside a project.
It holds project-local agent state, logs, sessions, and related support data.

## Evidence Bag

A structured memory/evidence layer used to preserve useful context beyond immediate chat turns.

## Loop

A runtime execution mode for the agent.
Examples include direct chat, planner-only, thought chain, review judge, and recovery agent.

## Loop Contract

The shared shape that loops are expected to obey for:
- inputs
- outputs
- history ownership
- metadata
- stop semantics

## Tool Round

One cycle of tool selection/execution inside an agent turn.

## Prompt Source

A file-backed input used to build the effective prompt.

## Prompt Profile

A structured prompt configuration that points at prompt sources and is intended for a specific role or execution context.

## Execution Plan

The structured description of a multi-step execution shape in Prompt Lab.
Phase 1/2 currently treat it as an ordered plan, even though the long-term concept is graph-capable.

## Binding

An explicit mapping from an execution node to a prompt profile.

## Build Artifact

A compiled prompt result with provenance, fingerprints, and related metadata.

## Draft / Published / Active

Prompt Lab state has three important modes:
- **Draft**: work in progress
- **Published**: a stable package candidate
- **Active**: the package the runtime is allowed to consume

The runtime should consume only active published state, not drafts.

## App Journal

The SQLite-backed builder/project memory store under `_docs/_journalDB/app_journal.sqlite3`.
It stores dev logs, TODOs, doctrine, and similar continuity records.

## Builder Contract

The formal prescriptive rules that guide builder behavior and architectural discipline.

## Builder Doctrine

Reflective or descriptive documents explaining how the builder workflow actually behaves.
These are not the same as the contract.
