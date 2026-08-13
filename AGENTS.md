# JarvisOS Agent Working Guide

Status: Current / Operational Guide

This file is the first document an AI agent should read before working in this repository.

It defines operational guidance for agents. It is not product architecture and does not replace architecture documentation, ADRs, or project-state documentation.

For the current project snapshot, read:

- `docs/project/PROJECT_STATE.md`
- `docs/project/ARCHITECTURE_GUARDRAILS.md`
- `docs/project/CODEX_WORKFLOW.md`

---

## What JarvisOS Is

JarvisOS is an agent-oriented runtime for controlled interaction with physical and digital devices.

The current system includes:

- deterministic Runtime execution;
- semantic capabilities;
- device catalog and lifecycle boundaries;
- DeviceState management;
- persistence with stale-state restoration semantics;
- simulated discovery and onboarding;
- HTTP device transport;
- MQTT synchronous request/response transport;
- per-device HTTP/MQTT transport composition;
- optional Runtime API;
- optional local Dashboard;
- optional AI Adapter;
- experimentally validated Gemini structured planning;
- fake/simulated validation paths for hardware-independent testing.

The default Runtime remains:

- local-first;
- transport-neutral;
- AI-optional;
- offline-safe;
- deterministic at the execution boundary.

JarvisOS is designed so that transports, hardware, AI providers, interfaces, and future protocol adapters can evolve without making Runtime dependent on any specific implementation.

---

## What JarvisOS Is Not

JarvisOS is not currently:

- a production-secure home automation platform;
- a mandatory cloud service;
- a complete production authorization system;
- dependent on the Dashboard for operation;
- dependent on AI for core Runtime behavior;
- a general-purpose driver plugin marketplace;
- a complete hardware discovery/interoperability framework;
- a production remote-access platform;
- a production voice assistant stack;
- a medical system;
- a vehicle safety-critical control system.

Future vision documents must not be interpreted as evidence that those capabilities are implemented.

---

## Sources Of Truth

- GitHub is the source of truth for:
  - code;
  - tests;
  - exact commands;
  - technical implementation state;
  - protocols;
  - examples;
  - configuration behavior;
  - platform integration guides.

- Notion is the source of truth for:
  - architecture decisions;
  - ADRs;
  - roadmap status;
  - development journal;
  - releases;
  - long-term architectural knowledge;
  - vision.

Do not duplicate full ADRs, the Jarvis Reference Manual, or entire platform manuals inside this file.

`docs/project/PROJECT_STATE.md` is the repository snapshot of current implementation state.

`docs/vision/FUTURE_EXPERIENCE_IDEAS.md` is aspirational vision and must not be treated as current architecture or approved implementation scope.

---

## Mandatory Working Rules

Before making changes:

1. Read this file.
2. Read `docs/project/PROJECT_STATE.md`.
3. Read `docs/project/ARCHITECTURE_GUARDRAILS.md`.
4. Read `docs/project/CODEX_WORKFLOW.md`.
5. Inspect the current repository state.
6. Load only the specialized documentation relevant to the task.
7. Inspect applicable ADRs when the task touches architectural boundaries.

Additional rules:

- Work from `main` unless the task explicitly says otherwise.
- Keep changes scoped to the requested phase.
- Preserve existing user work.
- Do not reset, delete, or discard unrelated changes.
- Do not expand scope merely because adjacent improvements are available.
- Do not modify future-vision documentation unless explicitly requested.
- Do not interpret old legacy Jarvis behavior as approved JarvisOS architecture.

---

## Development Gates

Follow the project gate before implementation.

Typical lifecycle:

1. Design gate for architectural or boundary-changing decisions.
2. ADR or Notion architecture update when required.
3. Explicit opening of implementation scope.
4. Implementation branch and PR.
5. Validation.
6. Merge only when authorized.
7. Post-merge verification.
8. Project-state synchronization.
9. Notion closure when requested.

Do not skip directly from an idea to implementation when the work changes architecture, system boundaries, protocol ownership, security, persistence, or execution semantics.

If a phase is explicitly blocked, do not open it without instruction.

---

## Context Routing

Always read before implementation work:

- `docs/project/PROJECT_STATE.md`
- `docs/project/ARCHITECTURE_GUARDRAILS.md`
- `docs/project/CODEX_WORKFLOW.md`

Load specialized context only when relevant.

### Device interoperability / discovery / pairing / compatibility

Read:

- `docs/design/DEVICE_INTEROPERABILITY.md`

Use when working on:

- device discovery;
- protocol identification;
- capability probing;
- compatibility assessment;
- pairing;
- trust;
- onboarding;
- Matter;
- Zigbee;
- BLE;
- vendor protocol adapters;
- commercial-device compatibility.

### Voice / STT / TTS / conversational UX

Read:

- `docs/design/VOICE_INTERACTION.md`

Use when working on:

- wake word;
- VAD;
- STT;
- TTS;
- turn-taking;
- barge-in;
- Voice Director;
- conversational sessions;
- speech latency;
- voice UX.

### Historical Jarvis behavior / previous experiments

Read:

- `docs/vision/LEGACY_JARVIS_LESSONS.md`

Use when historical evidence may help with:

- voice;
- remote interaction;
- personality;
- multimedia;
- legacy UX;
- previous failed approaches.

Do not port legacy architecture blindly.

### Aspirational product ideas

Read only when the task explicitly involves future vision:

- `docs/vision/FUTURE_EXPERIENCE_IDEAS.md`

Do not treat this document as:

- roadmap;
- approved implementation scope;
- current architecture;
- acceptance criteria.

Do not load unrelated specialized documents unless required by the task.

---

## Coding Rules

Prefer existing boundaries and local patterns.

Keep responsibilities separated across:

- Runtime;
- Planner;
- registry;
- drivers;
- persistence;
- API;
- Dashboard;
- AI adapters/providers;
- configuration;
- state coordination.

Use constructor injection or composition-root wiring.

Do not turn `RuntimeContext` or another shared object into a service locator.

Do not introduce a global `DriverRegistry` without explicit architectural approval.

Do not add:

- retries;
- backoff;
- asynchronous/background behavior;
- persistence;
- secrets infrastructure;
- new transports;
- provider fallback;
- discovery behavior;
- remote connectivity;

unless the approved phase explicitly includes them.

---

## Runtime Boundary

Runtime owns execution.

Runtime must remain:

- deterministic;
- transport-neutral;
- AI-provider-neutral;
- independent of Dashboard;
- independent of remote-access technology.

Runtime must not contain branching such as:

- if HTTP;
- if MQTT;
- if BLE;
- if Matter;
- if vendor X.

Transport selection belongs in composition/adapters.

---

## Planner And Command Boundary

Canonical commands remain the authoritative execution language.

Planner behavior must remain deterministic.

AI providers must not:

- directly construct Runtime `Command` objects unless an approved boundary explicitly changes this;
- directly call Runtime;
- directly call Drivers;
- directly mutate DeviceState;
- bypass confirmation or policy.

Free-form natural-language model output must never directly trigger physical mutations.

Structured AI output must still pass existing validation and deterministic execution boundaries.

---

## AI Boundary

AI may:

- interpret natural language;
- produce approved structured plans;
- converse;
- explain;
- summarize;
- suggest;
- ask for clarification.

AI does not own:

- Runtime;
- policy;
- authorization;
- DeviceState;
- persistence;
- device transport.

Core Runtime startup and deterministic device operation must remain possible without AI.

Real-provider work requires an explicitly opened and approved AI-related phase.

Do not add:

- automatic provider fallback;
- persistent AI memory;
- provider registries;
- default cloud dependency;
- new credentials;
- AI access to transport internals;

without explicit approval.

AI context should exclude unnecessary:

- IP addresses;
- URLs;
- broker hosts;
- MQTT topics;
- credentials;
- State Store paths;
- DriverResult internals;
- raw diagnostics.

---

## Driver Boundary

Drivers translate semantic device operations into transport-specific interactions.

Drivers receive semantic device/capability information and return bounded `DriverResult` values.

Drivers must not:

- receive full natural-language intent;
- own user authorization;
- own confirmation policy;
- mutate DeviceState directly;
- write the State Store;
- call Planner;
- call Runtime;
- expose raw transport exceptions upward;
- automatically retry mutations unless explicitly approved.

Transport details remain below the semantic device layer.

---

## DeviceState Boundary

DeviceState represents semantic knowledge about a device.

DeviceState is not:

- HTTP connectivity;
- MQTT broker state;
- socket status;
- process state;
- transport diagnostics.

State semantics:

- `unknown`: no trustworthy semantic state is known;
- `known`: semantic state was successfully observed or confirmed and is considered current;
- `stale`: prior semantic state exists but is not confirmed current.

Transport connectivity alone never implies `known`.

Restored persisted state must not automatically imply current physical availability.

A failed explicit read after prior known state must not falsely leave the UI/API claiming current physical state.

Technical transport errors must not become semantic properties.

---

## Persistence Boundary

Persistence stores approved semantic state.

It must not store:

- transport credentials;
- raw broker state;
- provider secrets;
- raw exceptions;
- transient connection details;
- AI prompts/responses unless explicitly designed.

Restored state is historical knowledge, not proof of current availability.

Persistence failure behavior must remain explicit and testable.

Shutdown ownership must preserve required ordering and idempotence.

---

## Configuration Boundary

Configuration is not Runtime state.

Configuration may describe:

- devices;
- capabilities;
- transport bindings;
- supported profile options.

Configuration must not silently become:

- secret storage;
- runtime event history;
- mutable DeviceState;
- AI memory.

Runtime and registries must not read files directly.

Configuration loading belongs at the composition/bootstrap boundary.

---

## API Boundary

The Runtime API is an optional adapter.

It must not become an alternative Runtime architecture.

The API must not expose:

- live Runtime objects;
- registries;
- Drivers;
- State Store implementation;
- transport clients;
- secrets;
- raw internal exceptions.

API mutation paths must continue using the same policy and Runtime boundaries as other interfaces.

Runtime API work requires an explicitly opened and approved phase.

---

## Dashboard Boundary

The Dashboard is an optional local control surface.

It must consume the Runtime API and safe projections.

The Dashboard must not import or directly control:

- Runtime internals;
- Drivers;
- registry internals;
- broker clients;
- State Store implementation;
- AI-provider internals.

Dashboard state must represent semantic device state, not transport implementation details.

Dashboard work requires an explicitly opened and approved phase.

---

## Device Interoperability Rules

JarvisOS follows:

- Protocol over ecosystem.
- Capability over brand.
- Capability over age.

Future device compatibility must preserve the distinction:

Discovery != Identification.

Identification != Compatibility.

Compatibility != Trust.

Trust != Authorization.

Discovering a device does not grant control.

A supported protocol does not automatically make a device trusted.

A trusted device does not automatically grant every user permission to every capability.

Protocol-specific details must remain below semantic capabilities.

---

## Hardware Reuse Principle

JarvisOS should not ask only:

> Can this device run all of JarvisOS?

It should also ask:

> What useful capability can this hardware still provide?

Examples may include:

- old phones as cameras, microphones, displays, bridges;
- old laptops as dashboards, voice satellites, lightweight nodes;
- Raspberry Pi systems as gateways, brokers, or adapter hosts;
- ESP32 nodes as physical sensors and actuators;
- smartwatches as sensors, interaction surfaces, or personal nodes.

Hardware age alone is not a compatibility decision.

Real capability, reliability, security, and resource limits remain authoritative.

---

## Voice Boundary

Voice is an interface to JarvisOS, not a separate execution architecture.

Speech may eventually flow through:

- wake word;
- VAD;
- STT;
- Turn Manager;
- Conversation Session;
- AI/intent boundary;
- Runtime/policy;
- Voice Director;
- TTS.

Voice must not bypass physical-action safety.

A successful TTS demo does not mean Voice Architecture is complete.

Voice work requires UX validation for:

- latency;
- naturalness;
- interruption;
- repeated-use comfort;
- contextual continuation;
- ambient-speech behavior.

---

## Security

Do not expose Runtime publicly for convenience.

Do not place secrets in source control.

Do not place secrets in normal Runtime profiles unless an approved secrets architecture explicitly permits it.

LAN/public/remote exposure requires explicit security design.

Temporary lab access methods must not silently become production architecture.

Never disable certificate or hostname verification merely to make integration work.

Do not introduce:

- `verify=False`;
- `CERT_NONE`;
- disabled hostname checking;
- insecure global SSL injection;

without explicit security approval.

Mutations remain subject to policy and confirmation.

---

## Remote Access

Remote access is not currently a production platform feature.

Lab tools or historical mechanisms such as temporary tunnels may be used only when explicitly authorized.

Future remote connectivity must preserve:

Remote client
-> authenticated/private path
-> controlled gateway/boundary
-> authorization/policy
-> Runtime

Do not expose Runtime, Dashboard, MQTT broker, or device drivers directly to the public Internet by convenience.

---

## Testing Policy

Run the full suite before reporting implementation work:

```bash
python -m unittest
```

Run the default Runtime smoke test:

```bash
python -m jarvis_core
```

When configuration is relevant, also validate an appropriate profile.

Example:

```bash
python -m jarvis_core --config profiles/http-lab.example.json
```

When API behavior changes, run API smoke validation.

When Dashboard behavior changes, run Dashboard smoke validation.

When persistence changes, test:

- save;
- restart;
- stale restore;
- recovery to known/current.

Hardware-dependent tests must not run in normal CI unless explicitly designed for that purpose.

Use fake transports and deterministic tests for automated validation.

Real broker, provider, hardware, or cloud validation is a separate integration gate.

---

## Hardware Validation Policy

Hardware validation is manual unless a phase explicitly states otherwise.

Current validation evidence includes:

- ESP32 + ESP-IDF reference node;
- physical HTTP local control path;
- GPIO2 LED reference behavior;
- profile-based Runtime configuration;
- real local MQTT request/response validation using Paho and loopback Mosquitto;
- HTTP/MQTT per-device transport composition.

ESP32 MQTT reference-node validation remains a separate future hardware gate.

If required hardware is unavailable:

- stop;
- report the blocker;
- provide the smallest required manual step;
- do not fabricate validation evidence.

---

## Documentation Policy

Keep GitHub technical documentation concise.

Prefer linking to focused subsystem documents rather than copying large sections repeatedly.

Keep Notion:

- architectural;
- decision-oriented;
- roadmap-aware;
- vision-oriented where appropriate.

Update docs only when:

- behavior changes;
- commands change;
- project state changes;
- architectural guidance is approved;
- the task explicitly requests documentation work.

Do not document future work as Current.

Do not update Notion unless explicitly authorized.

---

## Architecture Pipelines

### Runtime execution pipeline

```text
CLI / Adapter
-> Planner
-> Runtime
-> Runtime Capability
-> DeviceCommandRouter
-> Driver / Transport Composition
-> DriverResult
-> DeviceStateCoordinator
-> DeviceState
-> CapabilityResult
```

### Configuration and persistence pipeline

```text
JSON config
-> RuntimeConfigurationLoader
-> RuntimeProfile
-> bootstrap / composition root
-> DeviceRegistry
-> transport bindings
-> per-device driver composition
-> optional JsonDeviceStateStore restore
-> Runtime
```

### AI-assisted path

```text
Natural language
-> AI provider / adapter
-> structured AIActionPlan
-> normalization / validation
-> canonical command
-> Planner
-> Runtime
```

AI never replaces the deterministic execution pipeline.

---

## Stable Rules

- Configuration is not Runtime state.
- Runtime state is not secrets.
- Drivers do not own authorization.
- Drivers do not persist.
- Runtime does not choose transport.
- Registries do not read configuration files directly.
- Restored state is `stale`, not proof of device availability.
- Transport connectivity does not imply semantic current state.
- AI provider success does not bypass validation.
- Dashboard is downstream of Runtime API.
- Future vision is not roadmap.
- Default Runtime remains optional-AI and offline-safe.
- Real infrastructure validation does not replace deterministic automated tests.

---

## Pull Request Rules

- Open one PR per phase unless explicitly instructed otherwise.
- Do not merge your own PR unless explicitly instructed.
- Keep PR scope aligned with the approved task.
- Do not silently include unrelated cleanup.

Report as applicable:

- tests;
- smoke tests;
- commit SHA;
- PR URL;
- PR number;
- draft/ready state;
- mergeability;
- remaining acceptance gates.

For post-merge closure:

1. verify the expected merge;
2. synchronize `main`;
3. run required gates again;
4. verify implementation containment;
5. verify project-state wording;
6. only then report completion.

---

## Phase Rules

- Do not open the next phase or Epic without explicit instruction.
- Do not implement out-of-scope future work during consolidation.
- If the phase is documentation-only, do not touch product behavior.
- If the phase is design-only, do not implement.
- If a required gate fails, stop and report the blocker.
- If a physical validation gate is pending, do not claim completion without evidence.

---

## What Not To Add Without Explicit Approval

Do not introduce any of the following casually:

- new Runtime behavior;
- global `DriverRegistry`;
- retries/backoff;
- background polling;
- async device-state mutation;
- secrets management;
- SQLite/migrations;
- new transports;
- automatic hardware discovery;
- production authentication;
- production authorization;
- production remote access;
- automatic AI-provider fallback;
- persistent AI memory;
- provider SDK proliferation;
- LLM-owned execution;
- new public network listeners;
- WebSocket/SSE infrastructure;
- health/medical decision logic;
- vehicle safety-critical control;
- hidden user profiling.

These require explicit phase/design approval when relevant.

---

## Legacy Jarvis Rule

Historical Jarvis implementations are research evidence, not architecture authority.

Useful legacy ideas may be classified as:

- REUSE;
- REDESIGN;
- REFERENCE;
- MERGE;
- RESEARCH;
- DROP.

Do not port legacy patterns that:

- couple LLM output directly to actions;
- execute extracted free-form JSON;
- mix voice, state, transport, and execution in one component;
- expose services publicly for convenience;
- embed secrets in source/config;
- bypass modern JarvisOS boundaries.

---

## Reporting Results

Reports should be concise and evidence-based.

Include when applicable:

- technical summary;
- branch used;
- files created;
- files modified;
- tests run;
- test results;
- CLI/API/Dashboard regressions;
- hardware/provider/broker validation status;
- architectural impact;
- defects or blockers;
- commit hash;
- PR URL;
- PR state;
- mergeability;
- remaining gates;
- explicit confirmation of out-of-scope areas left untouched.

Do not report assumptions as validated facts.

Do not report a phase as completed while a required acceptance gate remains open.
