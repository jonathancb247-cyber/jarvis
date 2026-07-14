# JarvisOS Project State

Status: Current / Project Snapshot

This document gives AI agents a compact project state snapshot. It points to the technical source documents instead of duplicating them.

For operational rules, read [../../AGENTS.md](../../AGENTS.md).

## Current Status

- Epics 1-9 are completed.
- Epic 10 is in progress.
- Phase 10.1 is completed as design: AI Adapter Boundary.
- Phase 10.2 is completed as design: Structured Plan and Safe Context Contracts.
- Phase 10.3 is completed: deterministic fake AI Adapter.
- Current snapshot commit: `9f7025a5e20d8d9f8cc3dbfb7cf156ad4576caed`.
- Phase 10.3 PR: #32 merged.
- Phase 10.3 implementation commit: `e374d30f2c28865c82fcb880f7079974ea1dfca4`.
- Full test suite after Phase 10.3: 444 tests passing.
- Epic 11 is in progress.
- Phase 11.1 is completed as design: Runtime API and Dashboard Adapter Boundary.
- Phase 11.2 is pending merge: Local Runtime API Minimal Implementation.
- Runtime API is experimental and localhost-only.
- No Dashboard is implemented.
- Current closing commit for Epic 9: `c3a6f78a72b9c08db550743cec6910934c44899d`.
- Full test suite at Epic 9 close: 420 tests passing.
- Default runtime remains empty, simulated, and offline-safe.

## Current Architecture

Runtime execution:

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

Configuration and persistence:

```text
JSON config
-> RuntimeConfigurationLoader
-> RuntimeProfile
-> bootstrap
-> DeviceRegistry
-> HttpDeviceBindingStore
-> optional JsonDeviceStateStore restore
-> Runtime
-> official DeviceState update
-> PersistingDeviceStateCoordinator
-> atomic snapshot
```

## Completed Epics

- Epics 1-2: runtime, adapter boundary, events, diagnostics, and CLI foundation.
- Epics 3-4: device domain, simulated driver boundary, routing, state coordination, and runtime bridge.
- Epics 5-6: device catalog and lifecycle.
- Epic 7: simulated discovery and onboarding.
- Epic 8: first experimental real driver through HTTP local, plus ESP32 hardware validation.
- Epic 9: JSON configuration, RuntimeProfile, DeviceState persistence, profile-based HTTP validation, and consolidation.

## Current Epic

Epic 10 — AI Adapter Boundary.

Current completed phase:

- Phase 10.3 — Deterministic Fake AI Adapter Minimal Implementation.

Next blocked phase:

- Phase 10.4 — First Optional AI Provider Adapter, blocked until explicitly opened.

Independent product line:

- Epic 11 - Runtime API and Dashboard is in progress.
- Phase 11.2 - Local Runtime API is pending merge.
- Phase 11.3 - Minimal Local Dashboard remains blocked until explicitly opened.
- Epic 10 remains unchanged and Phase 10.4 remains blocked.

## Stable Boundaries

Stable project rules:

- Configuration is not State.
- State is not Secrets.
- RuntimeProfile is declarative.
- Runtime does not read files directly.
- DeviceRegistry does not read or write files.
- Drivers do not receive `Command`.
- Drivers do not return `CapabilityResult`.
- Drivers do not persist.
- Restored state becomes `stale`.
- `stale` does not imply current availability.

## Experimental Boundaries

Current experimental areas:

- HTTP local transport.
- `HttpDeviceDriver`.
- `HttpDeviceBindingStore`.
- JSON configuration schema v1.
- `JsonDeviceStateStore`.
- State snapshot schema v1.
- ESP32 HTTP LED validation workflow.
- Deterministic Fake AI Adapter.
- Structured Plan models.
- Safe Context Builder.
- Plan Validator.
- Confirmation Gate.
- Sequential AI Plan Executor.
- Runtime API Adapter.
- Localhost REST/JSON Runtime API.
- Safe Runtime API projections.

## Current Transports

- Current / Experimental: HTTP local.
- Current / Simulated: in-memory simulated driver.
- Future / Not Implemented: MQTT, Serial/USB, GPIO, BLE, Zigbee, Tuya.

## Supported Platforms

See [platform guides](../platforms/README.md).

Current validated platform:

- ESP32 + ESP-IDF with HTTP local LED example.

Current host support:

- Linux PC.
- Windows PC.

Future/reference only:

- ESP32 Arduino.
- ESP8266.
- Arduino Uno.
- STM32.
- Raspberry Pi GPIO.
- Android bridge/node.

## Validation Status

- CI uses fake transports and must not require hardware.
- ESP32 validation is manual.
- Profile-based hardware validation uses `python -m jarvis_core --config profiles/http-lab.local.json`.
- Runtime API validation uses `python -m jarvis_core.api --config profiles/http-lab.local.json`.
- The older `tools/run_http_led_validation.py` script remains a direct helper, not the primary profile-based validation path.

## Testing Status

Standard tests:

```bash
python -m unittest
```

Default smoke:

```bash
python -m jarvis_core
```

Configuration smoke:

```bash
python -m jarvis_core --config profiles/http-lab.example.json
```

Runtime API smoke:

```bash
python -m jarvis_core.api --config profiles/http-lab.example.json
```

## Important Decisions

- GitHub is the source of truth for implementation, protocols, examples, exact commands, and platform integration guides.
- Notion is the source of truth for ADRs, architecture status, roadmap, development journal, and releases.
- Default runtime stays offline-safe and does not load devices, bindings, network, or State Store.
- Profiles are declarative data, not live objects or plugin systems.
- State Store persists only semantic `DeviceState`; it does not persist config, bindings, trust, candidates, diagnostics, raw payloads, or secrets.
- Hardware availability is never inferred from restored state.
- AI providers do not produce executable `Command` objects.
- AI Structured Plans are normalized and validated before canonical command text reaches the Runtime-owned adapter boundary.
- The deterministic fake AI Adapter uses no network, credentials, provider SDK, or real model.
- The default runtime remains AI-free.
- No provider registry exists.
- No persistent AI memory exists.
- Phase 10.3 did not change Runtime, Driver, Registry, Configuration, or State Store boundaries.
- The Runtime API is optional, localhost-only, and submits canonical command text through the existing Runtime-owned adapter boundary.
- The Runtime API exposes detached semantic projections only.
- The Runtime API does not implement a Dashboard, LAN access, authentication, WebSocket, SSE, async Runtime, or direct internal access.

## Out Of Scope

Not currently implemented:

- real AI providers;
- `--profile`;
- DriverRegistry;
- retries/backoff;
- async/background I/O;
- secrets store;
- production authentication or authorization;
- SQLite;
- migrations;
- Dashboard UI;
- hardware discovery;
- persistent trust;
- persistent AI memory;
- AI/LLM scenario engine behavior.

## Key Technical Documents

- [Runtime Configuration](../getting-started/CONFIGURATION.md)
- [Device State Persistence](../getting-started/STATE_PERSISTENCE.md)
- [HTTP Profile Validation](../getting-started/HTTP_PROFILE_VALIDATION.md)
- [Runtime API](../api/README.md)
- [Device Integration Guide](../device-integration/README.md)
- [Driver Development](../device-integration/DRIVER_DEVELOPMENT.md)
- [Security Guidelines](../device-integration/SECURITY_GUIDELINES.md)
- [ESP32 + ESP-IDF Guide](../platforms/ESP32_ESP_IDF.md)
- [HTTP LED Example](../../examples/http-led/README.md)
- [AI Adapter](../ai/README.md)

## Glossary

- Runtime Capability: executable capability registered in `CapabilityRegistry`.
- DeviceCapability: semantic descriptor of what a device supports.
- DriverResult: internal technical result from a driver.
- DeviceState: official semantic state known by JarvisOS.
- RuntimeProfile: validated declarative configuration data.
- State Store: persistence boundary for semantic `DeviceState`.
- Binding: non-sensitive infrastructure configuration for reaching a device.
- Stale: restored last-known state that is not proof of current availability.
- AIActionPlan: provider-neutral structured plan normalized by the AI Adapter.
- AISafeContext: detached semantic context snapshot for AI planning.
- Runtime API: optional localhost adapter exposing safe REST/JSON projections and command submission.

## Quick Onboarding For AI Agents

1. Read [../../AGENTS.md](../../AGENTS.md).
2. Read this file.
3. Inspect `git status -sb`.
4. Identify the requested phase and scope.
5. Read the referenced technical guide for the area being changed.
6. Do only the requested work.
7. Run `python -m unittest`.
8. Run relevant smoke tests.
9. Report scope confirmations explicitly.
