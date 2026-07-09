# JarvisOS

JarvisOS is an agent-oriented cognitive operating system for future physical AI agents.

## AVP-001 - Architecture Validation Prototype

AVP-001 is the first executable architecture checkpoint for JarvisOS. It is intentionally small: the goal is not to build the full product yet, but to validate the smallest working loop that can grow into a modular physical AI operating system.

```text
Interactive CLI -> Runtime Bootstrap -> Event Bus -> Planner -> Capability Registry -> Time Capability -> CLI
```

In this phase, JarvisOS receives user requests from an interactive CLI, publishes them through an internal event bus, routes them through a simple planner, resolves registered capabilities, executes them, and returns responses.

## Phase 1.4 Scope

Phase 1.4 keeps the AVP-001 behavior, interactive CLI, command execution model, and internal device model while clarifying runtime boundaries.

Included in Phase 1.4:

- Runtime/bootstrap module for wiring core components.
- Clean `python -m jarvis_core` entrypoint.
- Interactive prompt that accepts user text until `exit` or `quit`.
- `Command` as the normalized executable action produced by the planner.
- `CapabilityResult` as the structured result returned by capabilities.
- `RuntimeContext` as the small container for runtime resources, including the device registry.
- Runtime-owned command execution.
- `Device` as the internal model of something controllable or observable.
- `DeviceState` as the known state snapshot for a device.
- `DeviceRegistry` for registering, looking up, listing, and updating internal device models.
- Event bus, planner, capability registry, and clock capability.
- Runtime-owned structured error handling for unknown commands, missing capabilities, and capability execution failures.
- Unit tests for the current core loop, CLI loop, runtime boundaries, domain execution flow, and device registry.
- No external runtime dependencies.

Out of scope for Phase 1.4:

- MQTT.
- Raspberry Pi GPIO.
- ESP32 integration.
- Zigbee or Tuya integration.
- Web interface.
- Device Capabilities.
- Real adapters.
- Intent.
- PlannerResult.
- Event as a domain entity.
- Real devices.
- Physical device actions.
- LLM-based planning.
- Persistent storage.

## Runtime Boundaries

Phase 1.4 defines the current internal boundaries without adding new product behavior.

### Core

Core is responsible for bootstrapping the executable AVP-001 loop:

- wire the event bus, registries, planner, runtime, and built-in capabilities;
- create the `RuntimeContext`;
- expose the `python -m jarvis_core` entrypoint;
- keep the system executable with no external runtime dependencies.

Core must not contain device-specific behavior, physical integrations, AI routing, persistence, or adapter-specific policy.

### Domain

Domain defines internal concepts and data structures:

- `Command`;
- `CapabilityResult`;
- `RuntimeContext`;
- `Device`;
- `DeviceState`;
- `DeviceRegistry`.

Domain objects do not execute commands, resolve capabilities, publish user interface output, or talk to external systems.

### Runtime

Runtime coordinates command execution:

- receive a `Command`;
- resolve a registered capability;
- execute the capability with the current `RuntimeContext`;
- return a `CapabilityResult`;
- convert runtime failures into structured `CapabilityResult` errors.

Runtime does not define new domain entities, parse natural language, manage physical devices, implement adapters, or access hardware/protocols directly.

### Adapters

Adapters are boundaries between JarvisOS and the outside world. In AVP-001, the CLI is the only adapter-like boundary.

Adapters may present messages and collect input, but they should not bypass the Runtime to execute commands or mutate domain state directly.

## Domain Concepts

Phase 1.4 uses only the internal concepts needed by the current AVP-001 loop:

- `Command`: a normalized executable action, such as `time.now`.
- `CapabilityResult`: a structured capability execution result with success, message, data, and error fields.
- `RuntimeContext`: the runtime resources needed while executing commands.
- `Device`: the internal model of something controllable or observable.
- `DeviceState`: the known state snapshot for a device.
- `DeviceRegistry`: the in-memory registry of known device models.

`Device` and `DeviceState` are internal models only. They do not communicate with hardware, external protocols, physical devices, or persistent storage in Phase 1.4.

## Run

```bash
python -m jarvis_core
```

Example session:

```text
Jarvis AVP-001
jarvis> what time is it?
Jarvis: The current time is 17:30.
jarvis> exit
Bye.
```

## Test

Run the unit test suite with the Python standard library:

```bash
python -m unittest
```

## Project Rule

Architecture is frozen until code forces a change. Notion documents decisions; GitHub validates them.
