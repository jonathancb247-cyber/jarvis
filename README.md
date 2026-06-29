# Jarvis

Agent-Oriented Cognitive Operating System.

## AVP-001 — Architecture Validation Prototype

The first objective is not to build the full product. The first objective is to validate the core architecture with the smallest executable loop:

```text
CLI → Event Bus → Planner → Capability Registry → Time Capability → CLI
```

## Sprint 1 Goal

Run a local command-line prototype that receives a user request, routes it through an event bus, resolves a capability, executes it, and returns a response.

## Run

```bash
python -m jarvis_core
```

Example:

```text
jarvis> what time is it?
Jarvis: The current time is 17:30.
```

## Project Rule

Architecture is frozen until code forces a change. Notion documents decisions; GitHub validates them.
