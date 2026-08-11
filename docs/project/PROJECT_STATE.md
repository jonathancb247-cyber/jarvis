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
- Phase 10.4 is completed as design: First Optional Local AI Provider Boundary.
- Phase 10.5 is in progress / Draft: Ollama provider exists in PR #38, but no compatible local model has passed strict `AIActionPlan` validation.
- Phase 10.6 is completed as design: Optional Cloud AI Provider and Secret Injection Boundary.
- Phase 10.7 is in progress / Draft: Groq provider exists in PR #39, but real strict Structured Output validation is blocked by provider constrained generation.
- Phase 10.8 is completed as design: Gemini Structured Provider Boundary.
- Phase 10.9 is pending merge/manual validation: Gemini provider exists in the active implementation PR, but no real Gemini call has been made.
- Phase 10.10 is blocked.
- No real AI provider is approved for merge or production use.
- Current snapshot commit: `82432ac7bbbbd53b533e0a57594a9579646d8883`.
- Phase 10.3 PR: #32 merged.
- Phase 10.3 implementation commit: `e374d30f2c28865c82fcb880f7079974ea1dfca4`.
- Full test suite after Phase 10.3: 444 tests passing.
- Epic 11 is in progress.
- Phase 11.1 is completed as design: Runtime API and Dashboard Adapter Boundary.
- Phase 11.2 is completed: Local Runtime API Minimal Implementation.
- Phase 11.2 PR: #34 merged.
- Phase 11.2 implementation commit: `04dcef842784ad333c6f83226d09fb1d04183b64`.
- Full test suite after Phase 11.2: 461 tests passing.
- Runtime API is Current / Experimental.
- Runtime API is localhost-only REST/JSON with synchronous Runtime interaction.
- Runtime API submits canonical command text through the Runtime-owned boundary and exposes safe detached projections.
- Phase 11.3 is completed: Minimal Local Dashboard.
- Phase 11.3 PR: #36 merged.
- Phase 11.3 implementation commit: `575387a028586a7d51d0d46727b4d792ec95464d`.
- Phase 11.3 visual refinement commit: `1136bc89cba39a7ee09f3cd9b9f7c2156d76f5d3`.
- Full test suite after Phase 11.3: 471 tests passing.
- Dashboard is Current / Experimental.
- Dashboard is localhost-only, API-backed, responsive, and built with vanilla HTML/CSS/JavaScript.
- Dashboard uses capability-driven controls from formal API capabilities.
- Dashboard has no external frontend dependencies, AI chat, auth, LAN access, WebSocket, SSE or async Runtime.
- Phase 11.4 - Profile-based Hardware Dashboard Validation is completed for the PR validation scope and pending merge.
- Phase 11.4 PR snapshot: automated fake-transport validation is covered by tests; real hardware Dashboard validation passed; physical LED on/off, disconnect/reconnect, persistence/restart, stale-to-known recovery and visual desktop acceptance were confirmed manually.
- Phase 11.4 observed a temporary Dashboard `Loading` state while the ESP32 was unreachable; recovery after reconnect occurred automatically without Runtime/API/Dashboard crash. This is recorded as a non-blocking UX observation.
- Full test suite for the Phase 11.4 PR snapshot: 473 tests passing.
- Phase 11.5 remains blocked.
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

Current status:

- Phase 10.3 - Deterministic Fake AI Adapter Minimal Implementation is completed.
- Phase 10.5 - Local Ollama Provider Minimal Implementation remains in progress / Draft in PR #38.
- Phase 10.7 - Groq Strict Structured Provider Minimal Implementation remains in progress / Draft in PR #39.
- Phase 10.8 - Gemini Structured Provider Boundary is completed as architectural design.
- Phase 10.9 - Gemini Structured Provider Minimal Implementation is pending merge/manual Gemini validation.
- Phase 10.10 - Real Provider Validation and Consolidation is blocked.
- Gemini provider work is Experimental and not real-validated. No real Gemini API call has occurred.
- Epic 10 provider work remains unvalidated; no real provider is approved.

Independent product line:

- Epic 11 - Runtime API and Dashboard is in progress.
- Phase 11.2 - Local Runtime API is completed.
- Phase 11.3 - Minimal Local Dashboard is completed.
- Phase 11.4 - Profile-based Hardware Dashboard Validation is completed for PR validation scope and pending merge.
- Phase 11.5 remains blocked.
- Epic 10 remains unchanged.
- Epic 11 status: In progress - Local Runtime API and Minimal Dashboard implemented; hardware Dashboard validation completed for PR scope and pending merge.

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
- Optional Gemini Provider.
- Gemini AI-cloud entry point.
- Structured Plan models.
- Safe Context Builder.
- Plan Validator.
- Confirmation Gate.
- Sequential AI Plan Executor.
- Runtime API Adapter.
- Localhost REST/JSON Runtime API.
- Safe Runtime API projections.
- Minimal Local Dashboard.
- Vanilla Dashboard static assets.
- Profile-based Hardware Dashboard validation workflow.

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

Dashboard smoke:

```bash
python -m jarvis_core.dashboard --config profiles/http-lab.example.json
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
- Phase 10.9 does not wire Gemini into the default Runtime, Runtime API, or Dashboard.
- Gemini requires explicit `python -m jarvis_core.ai_cloud --provider gemini` usage and `GEMINI_API_KEY` in the active environment.
- Gemini real-provider validation remains gated by `GEMINI_AI_VALIDATION_REQUIRED`.
- The Runtime API is optional, localhost-only, and submits canonical command text through the existing Runtime-owned adapter boundary.
- The Runtime API exposes detached semantic projections only.
- The Runtime API remains the boundary consumed by the Dashboard and still does not implement LAN access, authentication, WebSocket, SSE, async Runtime, or direct internal access.
- The Dashboard is optional, local-only, API-backed, and does not import Runtime internals.

## Out Of Scope

Not currently implemented:

- real AI providers;
- real AI provider validation;
- `--profile`;
- DriverRegistry;
- retries/backoff;
- async/background I/O;
- secrets store;
- production authentication or authorization;
- SQLite;
- migrations;
- Dashboard validation beyond the Phase 11.4 profile-based hardware Dashboard validation;
- hardware discovery;
- persistent trust;
- persistent AI memory;
- AI/LLM scenario engine behavior.

## Key Technical Documents

- [Runtime Configuration](../getting-started/CONFIGURATION.md)
- [Device State Persistence](../getting-started/STATE_PERSISTENCE.md)
- [HTTP Profile Validation](../getting-started/HTTP_PROFILE_VALIDATION.md)
- [Runtime API](../api/README.md)
- [Dashboard](../dashboard/README.md)
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
- Dashboard: optional browser UI consuming the localhost Runtime API.

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
