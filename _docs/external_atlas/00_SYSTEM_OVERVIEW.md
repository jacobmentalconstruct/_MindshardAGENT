# 00 System Overview

## What MindshardAGENT Is

MindshardAGENT is a local desktop agent workbench for advanced project-building workflows.

It combines:
- a visible Tkinter desktop interface
- a loop-based agent runtime
- a project-local sandbox and sidecar state model
- tool execution and local process orchestration
- prompt inspection and prompt-source management
- a separate Prompt Lab subsystem for prompt/execution design and evaluation

It is not best understood as a chatbot app.
It is closer to a local agent workstation with:
- project attachment
- controlled tool use
- session persistence
- prompt/runtime inspection
- prompt/execution design infrastructure

## Primary Capabilities

At a high level, the system can:
- attach to a local project folder
- maintain project-local sidecar state under `.mindshard`
- run agent turns against the attached workspace
- use tools in a controlled local sandbox or Docker-backed environment
- inspect prompt sources and the compiled prompt bundle
- save and reload sessions
- record builder/project memory in an app journal
- launch Prompt Lab for separate prompt/execution design work

## Primary Surfaces

The app currently has two major user-facing surfaces.

### 1. Main App

The main app is the live operating surface.

It is where the operator:
- chats with the agent
- manages sessions
- attaches projects
- sees prompt workbench summaries
- uses the sandbox and other operational panels

### 2. Prompt Lab

Prompt Lab is a separate subsystem and dedicated workbench.

It is where the operator:
- inspects prompt profiles
- inspects execution plans
- inspects bindings
- inspects packages, validation, promotions, and evaluation history
- works toward prompt/execution design and publication workflows

Prompt Lab is intentionally not embedded deeply into the main app shell.

## Major System Idea

The system is built around a few distinct kinds of work:

- **Runtime agent work**
  - prompt submission
  - loop execution
  - tool use
  - chat/session behavior

- **Project/workspace work**
  - attaching and detaching projects
  - managing local sidecar state
  - controlling where the agent is operating

- **Prompt/workflow design work**
  - prompt-source reasoning
  - prompt profile management
  - execution plan reasoning
  - package publication and activation

- **Builder/project memory**
  - development notes
  - TODOs
  - doctrine
  - logs
  - onboarding continuity

These categories are intentionally separated.

## High-Level Concept Map

```text
Main App
  -> app-layer orchestration
  -> Engine runtime coordinator
  -> UI facade / panes / widgets
  -> Prompt Workbench bridge

Engine
  -> loops
  -> prompt builder
  -> sandbox and tools
  -> sessions / evidence / journal

Prompt Lab
  -> separate workbench
  -> prompt/execution design data
  -> validation / promotion / evaluation surfaces
  -> runtime-consumable active package state

Storage
  -> .mindshard/ sidecar for project-local state
  -> Prompt Lab JSON + SQLite state
  -> app journal SQLite for builder/project memory
```

## What Makes The System Large

The codebase is large because it is not doing only one thing.
It combines:
- desktop UI composition
- local agent runtime orchestration
- sandbox/process execution
- prompt build and inspection
- loop-driven reasoning paths
- session and knowledge persistence
- Prompt Lab design-state infrastructure
- MCP server surfaces

That means the repo has to be understood as a collection of cooperating subsystems, not as a single monolithic application script.

## Current Product Position

The core runtime and the Prompt Lab subsystem are both operational.

What is already in place:
- stabilized main app runtime
- separate Prompt Lab workbench
- Prompt Lab services, storage, validation, package contract, and MCP surface
- main-app Prompt Lab summary bridge
- active/published/draft Prompt Lab state model

What is next:
- authoring real prompt profiles, execution plans, bindings, and packages in Prompt Lab
- validating the first end-to-end authoring -> publish -> activate -> main-app-consume workflow
