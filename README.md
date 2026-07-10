# JarvisOS

JarvisOS is an agent-oriented cognitive operating system for future physical AI agents.

## AVP-001 - Architecture Validation Prototype

AVP-001 is the first executable architecture checkpoint for JarvisOS. It is intentionally small: the goal is not to build the full product yet, but to validate the smallest working loop that can grow into a modular physical AI operating system.

```text
Interactive CLI -> Runtime-owned Adapter Boundary -> Event -> Planner -> Capability Registry -> Time Capability -> CLI
```

In this phase, JarvisOS receives user requests from an interactive CLI through a Runtime-owned adapter boundary. Runtime creates the internal event, routes the input through a simple planner, resolves registered capabilities, executes them, and returns structured results for the CLI to print.

## Phase 2.2 Scope

Phase 2.2 removes the temporary AVP wiring where CLI published directly into EventBus. The CLI now enters JarvisOS through `Runtime.handle_adapter_input(...)`.

Included in Phase 2.2:

- `Runtime.handle_adapter_input(...)` as the Runtime-owned adapter boundary for the current textual CLI input path.
- CLI uses only the Runtime-owned boundary.
- Runtime creates the internal `Event(type="user.input.received")`.
- EventBus remains internal to Runtime context and is not exposed as the CLI-facing API.
- Runtime still invokes Planner and executes Command.
- Runtime returns `CapabilityResult`.
- CLI prints `CapabilityResult.message`, preserving AVP-001 behavior.

Out of scope for Phase 2.2:

- New adapters.
- Driver interfaces.
- RuntimeResponse.
- AdapterInput.
- Security.
- Observability.
- Persistence.
- New lifecycle events.
- Async runtime.
- MQTT, GPIO, ESP32, Web UI, HTTP API, or AI.

## Phase 2.3 Scope

Phase 2.3 formalizes the command-line interface as the first official JarvisOS adapter without introducing a general adapter hierarchy.

Included in Phase 2.3:

- `CliAdapter` as a lightweight CLI adapter.
- `CliAdapter.run()` preserves the existing AVP-001 CLI behavior.
- `run_cli(...)` remains as a compatibility wrapper.
- CLI captures external text input, calls `Runtime.handle_adapter_input(text, source="cli")`, and prints `CapabilityResult.message`.
- CLI does not know EventBus, create Event, create or execute Command, resolve capabilities, or mutate DeviceRegistry.

Out of scope for Phase 2.3:

- BaseAdapter.
- Protocol.
- AdapterInput.
- RuntimeResponse.
- `adapters/` package.
- New adapters.
- EventBus, Domain, Planner, CapabilityRegistry, or DeviceRegistry changes.
- Security, observability, persistence, async runtime, MQTT, GPIO, ESP32, Web UI, HTTP API, or AI.

## Phase 2.4 Scope

Phase 2.4 adds minimal runtime operational diagnostics without changing AVP-001 visible behavior.

Included in Phase 2.4:

- Runtime generates a local `correlation_id` for each `handle_adapter_input(...)` flow.
- Runtime propagates that `correlation_id` through internal lifecycle events.
- Runtime emits internal lifecycle events for:
  - `user.input.received`;
  - `command.planned`;
  - `command.execution.started`;
  - `capability.execution.completed`;
  - `capability.execution.failed`;
  - `runtime.error`, where appropriate.
- Runtime uses Python standard-library logging for local technical diagnostics.
- Adapter-facing `CapabilityResult` values remain safe and do not expose stack traces or exception details.
- `user.input.received` records only `source`, `correlation_id`, `input_length`, and `timestamp`.

Privacy rule:

- Diagnostics do not record full adapter input text by default.
- Diagnostics do not record secrets, tokens, or full payloads.
- Capturing raw input for debugging would require an explicit future opt-in and is outside Phase 2.4.

Out of scope for Phase 2.4:

- Remote telemetry.
- Dashboards.
- OpenTelemetry.
- Persistence.
- Event Sourcing.
- Distributed tracing.
- EventBus as a logging system.
- New domain entities.
- New adapters.
- Security or permissions.
- MQTT, GPIO, ESP32, Web UI, HTTP API, or AI.

## Phase 2.6 Scope

Phase 2.6 hardens existing kernel contracts without adding new runtime features or changing AVP-001 visible behavior.

Included in Phase 2.6:

- Minimum domain invariants for `Command`, `Event`, and `RuntimeContext`.
- Minimum device model invariants for `Device` and `DeviceState`.
- `DeviceRegistry.register(...)` accepts only valid `Device` objects.
- `DeviceRegistry.update_state(...)` accepts only `DeviceState` objects.
- `EventBus.subscribe(...)` validates event type and handler inputs.
- Runtime error results do not expose complete `Command.args` back to adapters.
- Tests for domain validation, EventBus contract behavior, device registry hardening, and adapter-facing privacy.

Privacy rule for `Command.args`:

- `Command.args` may contain sensitive execution data.
- Runtime must not return complete `Command.args` in adapter-facing error results.
- Unknown textual input must not appear in `CapabilityResult.data`, lifecycle events, or logging.
- Diagnostics continue to record only minimum safe metadata, such as source, correlation ID, input length, command name, and error code.

Out of scope for Phase 2.6:

- CapabilityRegistry duplicate-policy changes.
- Protocols.
- BaseAdapter.
- State Store.
- Persistence.
- Drivers.
- New adapters.
- Advanced security.
- AI.
- Async runtime.
- Advanced observability.
- Event Sourcing.
- Runtime refactor or repository reorganization.

## Phase 1.7 Scope

Phase 1.7 keeps the AVP-001 behavior while introducing `Event` as an internal Domain Signal and making the in-memory Event Bus transport `Event` objects.

Included in Phase 1.7:

- Runtime/bootstrap module for wiring core components.
- Clean `python -m jarvis_core` entrypoint.
- Interactive prompt that accepts user text until `exit` or `quit`.
- `Command` as the normalized executable action produced by the planner.
- `CapabilityResult` as the structured result returned by capabilities.
- `Event` as an internal structured signal describing something that happened.
- `RuntimeContext` as the small container for runtime resources, including the device registry.
- Runtime-owned command execution.
- `Device` as the internal model of something controllable or observable.
- `DeviceState` as the known state snapshot for a device.
- `DeviceRegistry` for registering, looking up, listing, and updating internal device models.
- In-memory Event Bus based on `Event`, plus planner, capability registry, and clock capability.
- Runtime-owned structured error handling for unknown commands, missing capabilities, and capability execution failures.
- Capability contract validation in `CapabilityRegistry`.
- Runtime protection when a capability returns something other than `CapabilityResult`.
- `ClockCapability` as the reference implementation of the executable capability contract.
- Unit tests for the current core loop, CLI loop, runtime boundaries, capability contracts, Event Bus, domain execution flow, and device registry.
- No external runtime dependencies.

Out of scope for Phase 1.7:

- MQTT.
- Raspberry Pi GPIO.
- ESP32 integration.
- Zigbee or Tuya integration.
- Web interface.
- Device Capabilities.
- Real adapters.
- Intent.
- PlannerResult.
- Event lifecycle emission such as `command.planned` or `capability.execution.completed`.
- Real devices.
- Physical device actions.
- LLM-based planning.
- Persistent storage.
- Observability.
- Async runtime.
- Scheduler.
- Event sourcing.

## Events

Phase 1.7 defines `Event` as a Domain Signal, not an infrastructure message.

An `Event` describes something that happened inside JarvisOS. It does not replace `Command`, `CapabilityResult`, `Runtime`, or `EventBus`.

Minimum fields:

- `type`: non-empty string naming the event.
- `source`: non-empty string naming the producer.
- `payload`: event-specific data.
- `timestamp`: event creation time.
- `correlation_id`: optional flow identifier.
- `causation_id`: optional cause identifier.

The public `EventBus` contract accepts `Event` objects, not raw event-name strings.

The CLI does not publish directly to EventBus. Runtime creates `Event(type="user.input.received", source="cli", payload={"input_length": ...})` internally through the Runtime-owned adapter boundary.

Current EventBus contract:

- `subscribe(event_type, handler)` requires a non-empty string event type and a callable handler.
- Handlers run in subscription order.
- `publish(event)` returns handler results in a list.
- Handler exceptions propagate to the caller.
- EventBus is internal kernel transport, not a logging system and not a public adapter API.

## Capability Contracts

Phase 1.7 preserves the minimum contract for executable capabilities.

A capability registered in `CapabilityRegistry` must provide:

- `name`: a non-empty string.
- `run(command, context)`: a callable method that returns `CapabilityResult`.

`CapabilityRegistry` validates the static part of the contract at registration time:

- registry name must be a non-empty string;
- capability must define `name`;
- capability `name` must match the registry name;
- capability must define callable `run`.

`Runtime` validates the execution result:

- a capability that returns `CapabilityResult` is accepted;
- a capability that raises an exception is converted into a structured failure;
- a capability that returns any other type is converted into an `invalid_capability_result` failure.

`ClockCapability` is the current reference implementation of this contract.

## Runtime Boundaries

Phase 1.7 preserves the current internal boundaries without adding external product behavior.

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
- `Event`;
- `RuntimeContext`;
- `Device`;
- `DeviceState`;
- `DeviceRegistry`.

Domain objects do not execute commands, resolve capabilities, publish user interface output, or talk to external systems.

### Runtime

Runtime coordinates command execution:

- receive external adapter input through `handle_adapter_input(...)`;
- create internal input events without exposing EventBus as an adapter API;
- receive a `Command`;
- resolve a registered capability;
- execute the capability with the current `RuntimeContext`;
- return a `CapabilityResult`;
- convert runtime failures into structured `CapabilityResult` errors.

Runtime does not define new domain entities, parse natural language, manage physical devices, implement adapters, or access hardware/protocols directly.

### Adapters

Adapters are boundaries between JarvisOS and the outside world. In AVP-001, `CliAdapter` is the first official adapter.

Adapters may present messages and collect input, but they must enter JarvisOS through exactly one Runtime-owned boundary. They must not bypass Runtime, publish directly to EventBus, execute commands, or mutate domain state directly.

## Domain Concepts

Phase 1.7 uses only the internal concepts needed by the current AVP-001 loop:

- `Command`: a normalized executable action, such as `time.now`.
- `CapabilityResult`: a structured capability execution result with success, message, data, and error fields.
- `Event`: a structured Domain Signal describing something that happened.
- `RuntimeContext`: the runtime resources needed while executing commands.
- `Device`: the internal model of something controllable or observable.
- `DeviceState`: the known state snapshot for a device.
- `DeviceRegistry`: the in-memory registry of known device models.

`Device` and `DeviceState` are internal models only. They do not communicate with hardware, external protocols, physical devices, or persistent storage in Phase 1.7.

`Device.capabilities` is currently a list of internal device descriptors. It is not the same concept as executable runtime `Capability` objects registered in `CapabilityRegistry`.

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
