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
- Phase 10.9 is completed: Gemini Structured Provider Minimal Implementation merged in PR #41 and passed real provider validation.
- Phase 10.10 is blocked.
- Gemini is Current / Experimental: real provider validation passed with `gemini-3.6-flash`, full provider-neutral `AIActionPlan`, read, confirmed power on/off plans, ambiguity handling and destructive refusal.
- No AI provider is default or production-ready.
- Epic 12 is in progress.
- Phase 12.1 is completed as design: MQTT Driver Boundary.
- Phase 12.2 is completed: MQTT Request/Response Driver Minimal Implementation merged in PR #43.
- MQTT Driver is Current / Experimental: synchronous request/response only with fake-client CI validation, per-device HTTP/MQTT composition, and Runtime shutdown ownership verified.
- Phase 12.3 is completed: Local Mosquitto Integration Validation merged in PR #45.
- Phase 12.4 is blocked until explicitly opened for ESP32 MQTT reference node work.
- Voice Phase 1 is completed: Voice Experience Benchmark Harness - Fake Providers Only merged in PR #49.
- Voice Phase 1 merge commit: `1b4c6f7821900a55681087ffe8c591fd92b3f6c3`.
- Voice Phase 1 validation: 560 tests passing and default CLI smoke passed.
- Voice Phase 1 is fake-only: deterministic benchmark scenarios, fake STT/TTS providers, simulated metrics, and no real microphone, speaker, provider, network, cloud, hardware, Runtime/Driver execution path, persistent Conversation Session, or Second Brain.
- Voice Phase 1 does not provide real voice capability, real latency measurements, or provider compatibility.
- Voice Phase 2A is completed: STT/TTS Provider Bake-Off Foundation merged in PR #51.
- Voice Phase 2A merge commit: `6bcde6bade0e596789e27e142b3f2f66edbed2c9`.
- Voice Phase 2A implementation commit: `1f41b75aa053f7242731a568e661d4411ffbbf1f`.
- Voice Phase 2A validation: 581 tests passing and default CLI smoke passed.
- Voice Phase 2A provides provider-neutral STT/TTS evaluation contracts, synthetic/text-only fixture taxonomy, mock provider paths, normalized failure categories, a bake-off report model and synthetic/test metrics only.
- Voice Phase 2A does not validate real STT compatibility, real TTS compatibility, real provider latency, naturalness, real prerecorded-audio STT, real file-output TTS, microphones, speakers, credentials, network, cloud, hardware or Runtime/API/Dashboard/Driver/AI behavior.
- Current snapshot commit: `6bcde6bade0e596789e27e142b3f2f66edbed2c9`.
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
- Phase 11.4 - Profile-based Hardware Dashboard Validation is completed.
- Phase 11.4 final validation: ESP32 HTTP Dashboard path physically validated after PR #48 freshness fix merge; real read produced `known/current`, physical disconnect plus explicit read produced `stale/not current` with prior semantic properties preserved, and reconnect plus explicit read restored `known/current`.
- Phase 11.4 DeviceState freshness evidence: `power=false` was preserved during the failed disconnected read; no public transport URL, IP, socket, exception or driver details leaked into semantic properties or API/Dashboard responses.
- Phase 11.4 scope boundary: explicit `status.read` refreshes physical freshness in the current implementation. Dashboard auto-refresh refreshes projected Runtime API state only and does not imply hardware polling, heartbeat, automatic offline detection, MQTT availability monitoring or automatic discovery.
- Phase 11.4 validation notes: `stale` is not `unavailable`; `stale` means prior semantic state exists but is not confirmed current. The HTTP ESP32 path remains experimental and is not production-secure transport.
- Full test suite after PR #48 merge and Phase 11.4 closure: 595 tests passing.
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
- Phase 10.9 - Gemini Structured Provider Minimal Implementation is completed after PR #41 merge.
- Phase 10.10 - Real Provider Validation and Consolidation is blocked.
- Gemini provider work is Current / Experimental and real-provider validated with `gemini-3.6-flash`.
- Epic 10 remains in progress: deterministic AI Adapter implemented; Gemini real provider validated; Ollama and Groq remain experimental Draft paths.

Independent product line:

- Epic 11 - Runtime API and Dashboard is in progress.
- Phase 11.2 - Local Runtime API is completed.
- Phase 11.3 - Minimal Local Dashboard is completed.
- Phase 11.4 - Profile-based Hardware Dashboard Validation is completed after physical ESP32 HTTP freshness validation.
- Phase 11.5 remains blocked.
- Epic 10 remains unchanged.
- Epic 11 status: In progress - Local Runtime API and Minimal Dashboard implemented; hardware Dashboard validation completed with physical ESP32 HTTP freshness evidence.

Independent transport line:

- Epic 12 - Driver and MQTT Expansion is in progress.
- Phase 12.1 - MQTT Driver Boundary is completed as architectural design.
- Phase 12.2 - MQTT Request/Response Driver Minimal Implementation is completed after PR #43 merge.
- Phase 12.2 merge commit: `80e83fc77534e96da74dc440942845f911ae47b4`.
- Phase 12.2 validation: 529 tests passing, default CLI, profile CLI, API-only and Dashboard regressions passed.
- MQTT remains Current / Experimental: synchronous request/response only; HTTP remains supported; real local loopback Mosquitto validation was completed in PR #45; ESP32 MQTT, LAN/public MQTT, subscriptions, retained state, retries, MQTT auth/TLS and broker credentials are not validated or implemented.
- Phase 12.3 - Local Mosquitto Integration Validation is completed after validating a real loopback Mosquitto broker, Paho MQTT client adapter, local simulated MQTT lamp, read/on/off, persistence/restart, correlation failures, simulator failure/recovery, API/Dashboard projection and HTTP regression.
- Phase 12.3 merge commit: `871f5f02cdac5f00741534d3f87e2a799d060417`.
- Phase 12.3 validation: 538 tests passing, default CLI, HTTP profile CLI, API-only and Dashboard regressions passed.
- Phase 12.3 validation remains local only: no ESP32 MQTT hardware, MQTT auth/TLS, retained state, subscriptions, retries, cloud broker or Dashboard MQTT UI.
- Phase 12.4 - ESP32 MQTT Reference Node is blocked until explicitly opened.

Independent voice line:

- Voice Phase 1 - Voice Experience Benchmark Harness: Fake Providers Only is completed after PR #49 merge.
- Voice Phase 1 merge commit: `1b4c6f7821900a55681087ffe8c591fd92b3f6c3`.
- Voice Phase 1 implementation commit: `44b63731bc7d05931c0d6f2c47d33a180b439262`.
- Voice Phase 1 validation: 560 tests passing and default CLI smoke passed.
- Voice Phase 1 provides deterministic fake/scripted STT and TTS providers, minimal Turn Manager and in-memory Conversation Session behavior, fake intent/confirmation outcomes, simulated metrics, compact reports and safety-invariant tests.
- Voice Phase 1 does not provide real voice capability, real audio I/O, real STT/TTS provider compatibility, real-world latency measurements, wake-word behavior, AEC, realtime voice, hardware validation, Runtime/Driver execution, persistent Conversation Session, Second Brain, network, cloud, credentials or provider calls.
- Voice Phase 2A - STT/TTS Provider Bake-Off Foundation is completed after PR #51 merge.
- Voice Phase 2A merge commit: `6bcde6bade0e596789e27e142b3f2f66edbed2c9`.
- Voice Phase 2A implementation commit: `1f41b75aa053f7242731a568e661d4411ffbbf1f`.
- Voice Phase 2A validation: 581 tests passing and default CLI smoke passed.
- Voice Phase 2A provides provider-neutral STT/TTS evaluation contracts, synthetic/text-only fixture taxonomy, mock/fake provider paths, normalized failure categories, a bake-off report model and synthetic/test metrics only.
- Voice Phase 2A does not provide or validate real STT compatibility, real TTS compatibility, real provider latency, naturalness, real prerecorded-audio STT, real file-output TTS, microphone access, speaker output, network, cloud, credentials, hardware or Runtime/API/Dashboard/Driver/AI behavior.

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
- MQTT request/response driver boundary.
- MQTT profile binding model.
- MQTT fake-client validation workflow.
- Voice Experience Benchmark Harness.
- Fake STT/TTS providers.
- Minimal fake Turn Manager.
- In-memory fake Conversation Session.
- Simulated voice benchmark metrics.

## Current Transports

- Current / Experimental: HTTP local.
- Current / Experimental: MQTT request/response with injected client.
- Current / Simulated: in-memory simulated driver.
- Future / Not Implemented: Serial/USB, GPIO, BLE, Zigbee, Tuya.

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
- Gemini real-provider validation passed in Phase 10.9 using `gemini-3.6-flash`, the full provider-neutral `AIActionPlan`, strict JarvisOS validation, confirmation flow and destructive refusal.
- Gemini TLS and hostname verification remain enabled through the reviewed provider transport.
- MQTT request/response support is experimental and validated with fake clients plus local loopback Mosquitto in PR #45.
- MQTT local broker validation uses loopback Mosquitto with a validation-only simulated lamp; it is not production MQTT or ESP32 MQTT validation.
- MQTT topics are binding/config data and must not appear in DeviceCapability, Runtime API, Dashboard or AI context.
- MQTT does not implement subscriptions, retained state, LWT, availability topics, credentials, retries or background state updates.
- The Runtime API is optional, localhost-only, and submits canonical command text through the existing Runtime-owned adapter boundary.
- The Runtime API exposes detached semantic projections only.
- The Runtime API remains the boundary consumed by the Dashboard and still does not implement LAN access, authentication, WebSocket, SSE, async Runtime, or direct internal access.
- The Dashboard is optional, local-only, API-backed, and does not import Runtime internals.

## Out Of Scope

Not currently implemented:

- production AI providers;
- automatic provider fallback;
- `--profile`;
- DriverRegistry;
- retries/backoff;
- async/background I/O;
- secrets store;
- production authentication or authorization;
- SQLite;
- migrations;
- Dashboard validation beyond the Phase 11.4 profile-based hardware Dashboard validation;
- MQTT over LAN, public MQTT, cloud MQTT, production broker deployment or broker UI;
- ESP32 MQTT node validation;
- MQTT subscriptions, retained messages, availability topics, TLS/authentication or credentials;
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
- [MQTT Driver](../drivers/MQTT_DRIVER.md)
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
