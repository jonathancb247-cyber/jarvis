# JarvisOS

JarvisOS is an agent-oriented cognitive operating system for future physical AI agents.

## AVP-001 — Architecture Validation Prototype

AVP-001 is the first executable architecture checkpoint for JarvisOS. It is intentionally small: the goal is not to build the full product yet, but to validate the smallest working loop that can grow into a modular physical AI operating system.

```text
Interactive CLI → Runtime Bootstrap → Event Bus → Planner → Capability Registry → Time Capability → CLI
```

In this phase, JarvisOS receives user requests from an interactive CLI, publishes them through an internal event bus, routes them through a simple planner, resolves registered capabilities, executes them, and returns responses.

## Phase 1.2 Scope

Phase 1.2 keeps the AVP-001 behavior and interactive CLI while introducing a small internal domain language for command execution.

Included in Phase 1.2:

- Runtime/bootstrap module for wiring core components.
- Clean `python -m jarvis_core` entrypoint.
- Interactive prompt that accepts user text until `exit` or `quit`.
- `Command` as the normalized executable action produced by the planner.
- `CapabilityResult` as the structured result returned by capabilities.
- `RuntimeContext` as the small container for runtime resources.
- Runtime-owned command execution.
- Event bus, planner, capability registry, and clock capability.
- Unit tests for the current core loop, CLI loop, and domain execution flow.
- No external runtime dependencies.

Out of scope for Phase 1.2:

- MQTT.
- Raspberry Pi GPIO.
- ESP32 integration.
- Web interface.
- Intent.
- PlannerResult.
- Event as a domain entity.
- Device implementation.
- Device registry.
- Simulated devices.
- LLM-based planning.
- Persistent storage.

## Domain Concepts

Phase 1.2 implements only the internal concepts needed by the current AVP-001 loop:

- `Command`: a normalized executable action, such as `time.now`.
- `CapabilityResult`: a structured capability execution result with success, message, data, and error fields.
- `RuntimeContext`: the runtime resources needed while executing commands.

`Device` and `DeviceState` remain documented future concepts only. They will represent physical or simulated things and their known state in later phases, but they are not implemented in Phase 1.2.

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
