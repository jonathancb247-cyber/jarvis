# JarvisOS Coding Agent Workflow

Status: Current
Audience: Codex and other coding agents working on JarvisOS.

This document defines how coding agents should approach work in this repository.

It supplements AGENTS.md and does not replace it.

## 1. Required Context

Before implementation work:

1. Read `AGENTS.md`.
2. Read `docs/project/PROJECT_STATE.md`.
3. Read `docs/project/ARCHITECTURE_GUARDRAILS.md`.
4. Read documentation for the subsystem being modified.
5. Inspect relevant ADRs when architectural boundaries are involved.

Do not reconstruct project architecture from code alone when current documentation
already defines the boundary.

## 2. Context Loading

Load specialized context only when relevant.

Examples:

Driver work:
- driver documentation;
- applicable protocol documentation.

AI work:
- AI adapter/provider documentation.

Voice work:
- `docs/design/VOICE_INTERACTION.md`;
- legacy lessons when historical UX evidence is needed.

Device compatibility work:
- `docs/design/DEVICE_INTEROPERABILITY.md`.

Do not load unrelated vision documents merely because they exist.

## 3. Scope Discipline

Respect the task gate.

If the task is DESIGN:

- do not implement;
- do not modify source;
- do not add dependencies;
- do not commit;
- do not open a PR unless explicitly instructed.

If the task is IMPLEMENTATION:

- implement only approved scope;
- avoid opportunistic refactors;
- preserve unrelated behavior.

If the task is VALIDATION:

- do not convert validation tooling into product architecture;
- report failures accurately;
- do not fix unrelated defects without approval.

## 4. Architecture Discipline

Before changing a core boundary, verify compatibility with
`ARCHITECTURE_GUARDRAILS.md`.

Do not introduce:

- Runtime transport branching;
- direct AI execution;
- driver-owned policy;
- transport metadata into DeviceState;
- secret leakage;
- hidden automatic retries for mutations;
- new background behavior without an approved design.

## 5. Documentation Discipline

GitHub is the source of truth for implementation-level technical state.

Notion is used for architecture, vision, planning, and broader project knowledge.

Do not update Notion unless the task explicitly authorizes it.

Future Experience Ideas are aspirational and must not be interpreted as an
approved roadmap or implementation requirement.

Avoid duplicating existing documentation.

## 6. Testing

Run the repository's relevant test suite before completion.

At minimum, use the tests required by the affected subsystem.

When appropriate also validate:

- default CLI startup;
- relevant configured profile;
- API smoke;
- Dashboard smoke;
- persistence/restart behavior;
- failure behavior.

Real hardware or infrastructure validation must not silently replace deterministic
CI tests.

## 7. Hardware

Do not assume hardware is available.

Do not access physical hardware unless explicitly authorized.

Simulation/fakes should remain available for normal automated testing where
appropriate.

Physical validation is a separate acceptance gate when required.

## 8. Dependencies

Do not add a dependency merely because it simplifies implementation.

New dependencies require:

- a clear reason;
- appropriate scope;
- compatibility with project boundaries;
- explicit dependency-policy consideration when significant.

## 9. Completion Report

When implementation work is complete, report as applicable:

- summary;
- files changed;
- tests executed and results;
- smoke validation;
- architectural impact;
- commit SHA;
- PR number/state;
- mergeability;
- remaining validation gates;
- known risks/inconsistencies.

Do not report a phase as completed when a required acceptance gate remains open.

## 10. Snapshot Discipline

`PROJECT_STATE.md` should describe current repository/project state, not become
a development journal.

Update it when a meaningful project-state transition occurs.

Avoid transient implementation details that will immediately become stale.