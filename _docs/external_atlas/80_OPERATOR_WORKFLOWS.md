# 80 Operator Workflows

## Purpose

This document describes practical operator-facing flows through the system.

It is meant to answer:
- what a user actually does
- which surfaces they use
- how state changes along the way

## Workflow 1: Start The Main App

The operator launches MindshardAGENT and gets:
- the main desktop shell
- session controls
- sandbox/project controls
- prompt workbench
- runtime status/logging

At startup the app prepares:
- engine runtime
- session/knowledge stores
- UI facade
- Prompt Lab summary state

## Workflow 2: Attach A Project

The operator chooses a project folder.

The system then:
- sets the active sandbox root
- loads or creates project metadata
- rebinds stores
- starts a new session context
- updates prompt inspector state
- updates Prompt Lab summary state

This is the main transition from “app open” to “project-focused operation.”

## Workflow 3: Use The Agent In The Main App

The operator submits input in the chat/compose area.

The runtime then:
- builds a request
- selects a loop
- runs the agent logic
- may execute tools
- updates history and UI

The operator sees:
- chat output
- activity/logging
- prompt workbench inspection surfaces

## Workflow 4: Inspect Prompt State In The Main App

The operator can use the Prompt Workbench to inspect:
- compiled prompt state
- source stack
- prompt-related surfaces
- Prompt Lab summary state

This is a live inspection surface, not the deep design environment.

## Workflow 5: Open Prompt Lab

The operator uses the main-app Prompt Lab bridge.

That bridge:
- reloads or displays current Prompt Lab summary state
- opens the dedicated Prompt Lab workbench

The dedicated workbench then exposes tabs for:
- Sources
- Build
- Execution
- Bindings
- Promotion
- Evaluation

## Workflow 6: Work Inside Prompt Lab

In its current phase, Prompt Lab is a restrained administrative/design surface.

It currently supports:
- inspection of prompt profiles
- inspection of execution plans
- inspection of bindings
- inspection of validation, promotion, and evaluation records
- state refresh and validation

It is intended to evolve into the place where real prompt/execution authoring and package publication are managed.

## Workflow 7: Publish And Activate Prompt Lab State

The intended model is:
1. create or modify Prompt Lab design state
2. validate it
3. publish a package
4. activate that package
5. let the main runtime consume only that active published state

This keeps experimentation separate from runtime truth.

## Workflow 8: Reload Prompt Lab Summary In The Main App

The main-app bridge can explicitly reload Prompt Lab summary state.

It also now updates automatically when projects are:
- attached
- self-attached
- detached successfully

That keeps the main-app summary aligned with the currently active project.

## Workflow 9: Detach A Project

When detaching:
- the app archives sidecar state
- may remove `.mindshard/` from the project
- clears project-facing runtime state
- clears prompt inspector state
- refreshes Prompt Lab summary state

This returns the app to a non-project-attached condition.

## Workflow 10: Builder / Maintainer Continuity

Builders and future agents should not rely only on the visible UI.

They should also use:
- the app journal
- this external atlas
- Prompt Lab CLI and MCP surfaces
- file tree and subsystem docs

That combination gives a much better orientation path than trying to reason from raw file dumps alone.
