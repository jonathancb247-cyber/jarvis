# JarvisOS Agent Working Guide

Status: Current / Operational Guide

This file is the first document an AI agent should read before working in this repository. It is operational guidance, not product architecture.

For the current project snapshot, read [docs/project/PROJECT_STATE.md](docs/project/PROJECT_STATE.md).

## What JarvisOS Is

JarvisOS is an agent-oriented runtime for controlled interaction with devices. The current system validates deterministic runtime execution, device catalog/lifecycle boundaries, simulated discovery/onboarding, an experimental HTTP local driver, declarative configuration, and DeviceState persistence.

## What JarvisOS Is Not

JarvisOS is not currently:

- a production-secure home automation platform;
- a cloud service;
- an authorization system;
- a dashboard;
- a natural-language automation engine;
- a driver plugin ecosystem;
- a hardware discovery framework.

## Sources Of Truth

- GitHub is the source of truth for code, tests, exact commands, protocols, examples, and platform integration guides.
- Notion is the source of truth for architecture decisions, ADRs, roadmap status, development journal, and releases.
- Do not duplicate ADRs, the Jarvis Reference Manual, or full platform manuals here.

## Mandatory Working Rules

- Read this file and [docs/project/PROJECT_STATE.md](docs/project/PROJECT_STATE.md) before making changes.
- Inspect the current repo state before editing.
- Work from `main` unless the task explicitly says otherwise.
- Keep changes scoped to the requested phase.
- Preserve existing user work; do not reset or discard unrelated changes.
- Do not modify `docs/vision/FUTURE_EXPERIENCE_IDEAS.md` unless explicitly asked. It is future concepts and research notes, not Current architecture.

## Development Gates

Follow the project gate before implementation:

1. Design gate for architectural decisions.
2. ADR or Notion update when the phase requires architecture approval.
3. Implementation PR after approval.
4. Post-merge verification.
5. Notion closure after verified merge.

Do not skip directly from idea to implementation when the phase changes architecture or project boundaries.

## Coding Rules

- Prefer existing boundaries and local patterns.
- Keep Runtime, Planner, registry, driver, and persistence responsibilities separate.
- Use constructor injection or composition root wiring; do not turn `RuntimeContext` into a service locator.
- Do not introduce a `DriverRegistry` without explicit design approval.
- Do not add retries, async/background I/O, persistence, secrets, or new transports unless the phase explicitly approves them.
- AI work is allowed only inside explicit Epic 10 phases. Local provider work must stay explicitly wired and must not install models, download models, add credentials, add persistent AI memory, or wire AI into the default runtime without explicit approval.
- Runtime API work is allowed only inside explicit Epic 11 phases. The API must remain an optional adapter and must not expose Runtime internals, registries, Drivers, State Store, or live objects.
- Dashboard work is allowed only inside explicit Epic 11 phases. The Dashboard must consume the Runtime API and must not import Runtime internals or device infrastructure.

## Testing Policy

Run the full suite before reporting implementation work:

```bash
python -m unittest
```

Run the default smoke test for runtime behavior:

```bash
python -m jarvis_core
```

When configuration is relevant, also validate:

```bash
python -m jarvis_core --config profiles/http-lab.example.json
```

Hardware-dependent tests must not run in CI. Use fake transports for automated validation.

## Documentation Policy

- Keep GitHub technical documentation concise and link to detailed guides instead of copying them.
- Keep Notion summaries architectural and decision-oriented.
- Update docs only when behavior, commands, or project state changes.
- Do not document future work as Current.

## Hardware Validation Policy

Hardware validation is manual unless a phase explicitly says otherwise.

Current hardware-validated path:

- ESP32 + ESP-IDF;
- HTTP local;
- GPIO2 LED example;
- profile-based runtime with `--config`.

Stop and report exact physical steps if a task requires hardware that is unavailable.

## Boundaries That Must Not Break

Runtime pipeline:

```text
CLI / Adapter
-> Planner
-> Runtime
-> Runtime Capability
-> DeviceCommandRouter
-> Driver
-> DriverResult
-> DeviceStateCoordinator
-> DeviceState
-> CapabilityResult
```

Configuration and persistence pipeline:

```text
JSON config
-> RuntimeConfigurationLoader
-> RuntimeProfile
-> bootstrap
-> DeviceRegistry
-> HttpDeviceBindingStore
-> optional JsonDeviceStateStore restore
-> Runtime
```

Stable rules:

- Configuration is not runtime state.
- Runtime state is not secrets.
- Drivers do not receive `Command`.
- Drivers do not return `CapabilityResult`.
- Drivers do not persist.
- Runtime and registries do not read files directly.
- Restored state is `stale`, not proof of device availability.
- Default runtime remains empty, simulated, and offline-safe.

## Pull Request Rules

- Open one PR per phase unless instructed otherwise.
- Do not merge your own PR unless explicitly instructed.
- Report tests, smoke tests, commit hash, PR URL, PR number, and mergeability.
- If post-merge closure is requested, verify `main`, run gates again, and only then report completion.

## Phase Rules

- Do not open the next epic or phase unless explicitly instructed.
- Do not implement out-of-scope future work during consolidation.
- If a phase is documentation-only, do not touch product code.
- If a gate fails, stop and report the blocker.

## What Not To Do

Do not add any of these without explicit approval:

- new runtime features;
- `DriverRegistry`;
- retries/backoff;
- async/background I/O;
- secrets management;
- SQLite or migrations;
- dashboard/API;
- new transports;
- hardware discovery;
- production authentication or authorization;
- real AI providers, credentials, provider SDKs, or default runtime AI behavior;
- LAN/public API exposure, Dashboard UI, WebSocket, SSE, or API authentication without explicit approval;
- LLM/scenario engine behavior.

## Reporting Results

Reports should be concise and evidence-based. Include:

- summary;
- files changed;
- tests run and result;
- smoke tests;
- commit hash;
- PR link and status;
- explicit confirmations for scope restrictions.
