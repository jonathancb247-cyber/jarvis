# JarvisOS

JarvisOS is an agent-oriented cognitive operating system for future physical AI agents.

## AVP-001 — Architecture Validation Prototype

AVP-001 is the first executable architecture checkpoint for JarvisOS. It is intentionally small: the goal is not to build the full product yet, but to validate the smallest working loop that can grow into a modular physical AI operating system.

```text
CLI → Runtime Bootstrap → Event Bus → Planner → Capability Registry → Time Capability → CLI
```

In this phase, JarvisOS receives a user request, publishes it through an internal event bus, routes it through a simple planner, resolves a registered capability, executes it, and returns a response.

## Phase 1.0 Scope

Phase 1.0 keeps the AVP-001 behavior minimal while making the runtime cleaner and easier to test.

Included in Phase 1.0:

- Runtime/bootstrap module for wiring core components.
- Clean `python -m jarvis_core` entrypoint.
- Event bus, planner, capability registry, and clock capability.
- Unit tests for the current core loop.
- No external runtime dependencies.

Out of scope for Phase 1.0:

- MQTT.
- Raspberry Pi GPIO.
- ESP32 integration.
- Web interface.
- Device registry.
- Simulated devices.
- LLM-based planning.
- Persistent storage.

## Run

```bash
python -m jarvis_core
```

Example output:

```text
Jarvis AVP-001
jarvis> what time is it?
Jarvis: The current time is 17:30.
```

## Test

Run the unit test suite with the Python standard library:

```bash
python -m unittest
```

## Project Rule

Architecture is frozen until code forces a change. Notion documents decisions; GitHub validates them.
