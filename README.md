# JarvisOS

JarvisOS is an agent-oriented cognitive operating system for future physical AI agents.

## Documentation

- [Agent Working Guide](AGENTS.md)
- [Project State](docs/project/PROJECT_STATE.md)
- [Installation](docs/getting-started/INSTALLATION.md)
- [First run](docs/getting-started/FIRST_RUN.md)
- [First device](docs/getting-started/FIRST_DEVICE.md)
- [Runtime Configuration](docs/getting-started/CONFIGURATION.md)
- [Device State Persistence](docs/getting-started/STATE_PERSISTENCE.md)
- [HTTP Profile Validation](docs/getting-started/HTTP_PROFILE_VALIDATION.md)
- [AI Adapter](docs/ai/README.md)
- [Device Integration Guide](docs/device-integration/README.md)
- [ESP32 + ESP-IDF Guide](docs/platforms/ESP32_ESP_IDF.md)
- [HTTP LED Example](examples/http-led/README.md)
- [Driver Development](docs/device-integration/DRIVER_DEVELOPMENT.md)
- [Security Guidelines](docs/device-integration/SECURITY_GUIDELINES.md)

## Hardware Validated

JarvisOS has been physically validated with an ESP32 + ESP-IDF local HTTP LED example:

- ESP32-WROOM-32 / DevKit-style board.
- HTTP local experimental driver.
- Built-in LED on GPIO2.
- Phase 8.4 hardware validation.

This transport is experimental and not production secure. It does not provide authentication, TLS, persistence, automatic discovery, automatic onboarding, or public internet safety.

## Runtime Configuration

JarvisOS can start from an explicit declarative JSON profile:

```bash
python -m jarvis_core --config profiles/http-lab.local.json
```

The local profile file must be created by the user, usually by copying `profiles/http-lab.example.json`. The default runtime remains offline-safe, starts with no devices, and does not use the network.

Configuration is declarative: it recreates devices, capabilities, and bindings. When a profile enables `state_store_path`, JarvisOS restores the last semantic `DeviceState` as stale on startup. Secrets are not allowed in configuration or state files.

State persistence is experimental. It does not store bindings, raw payloads, trust, credentials, history, or hardware availability.

For the profile-based ESP32 validation flow, copy `profiles/http-lab.example.json` to `profiles/http-lab.local.json`, edit the local `base_url`, then run:

```bash
python -m jarvis_core --config profiles/http-lab.local.json
```

See [HTTP Profile Validation](docs/getting-started/HTTP_PROFILE_VALIDATION.md).

## AI Adapter

JarvisOS includes an experimental deterministic fake AI Adapter for boundary
validation only. It does not use a real model, network, credentials, provider
SDK, persistent memory, or default runtime wiring.

See [AI Adapter](docs/ai/README.md).

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

## Phase 3.2 Scope

Phase 3.2 introduces `DeviceCapability` as a minimal domain descriptor for what a device supports. It does not add execution, drivers, protocols, persistence, or hardware behavior.

Included in Phase 3.2:

- `DeviceCapability` as a device-domain descriptor.
- `Device.capabilities` accepts formal `DeviceCapability` descriptors.
- `Device.capabilities` temporarily keeps compatibility with non-empty legacy string descriptors.
- Device capability parameters are represented as a map of parameter name to declarative parameter descriptor.
- Unit tests cover `DeviceCapability` validation and registry compatibility.

Stable rule:

- `DeviceCapability` defines what a Device supports.
- `DeviceState` defines what is currently available or known.

Runtime Capability vs DeviceCapability:

- Runtime Capability is executable by `Runtime` through `CapabilityRegistry` and returns `CapabilityResult`.
- `DeviceCapability` is declared by a `Device` and does not execute, return `CapabilityResult`, register in `CapabilityRegistry`, or talk to hardware.

Parameter descriptors:

- `parameters` is a map of parameter name to descriptor.
- Parameter names are unique by construction.
- Parameter order has no semantic meaning.
- Parameter descriptors are declarative and may include `type`, `required`, `constraints`, and `metadata`.
- Validation of `Command.args` against parameter descriptors is outside Phase 3.2.

Legacy compatibility:

- Existing non-empty string descriptors in `Device.capabilities` remain supported temporarily.
- Strings are legacy-compatible descriptors and are not automatically converted to `DeviceCapability`.
- A future phase may remove legacy string descriptors after an explicit migration plan.

Out of scope for Phase 3.2:

- Public `ParameterDescriptor` class.
- Drivers or DriverRegistry.
- Protocols, MQTT, GPIO, ESP32, Zigbee, Tuya, or hardware.
- Command routing.
- Execution of `DeviceCapability`.
- Full validation of `Command.args`.
- Operational availability per capability.
- Persistence or State Store.
- Discovery.
- UI generation.
- Planner, Runtime, CapabilityRegistry, adapter, or AI changes.

## Phase 3.5 Scope

Phase 3.5 introduces `SimulatedDriver` as an experimental in-memory validation artifact for the Driver Boundary. It validates the separation between device-domain descriptors and physical/protocol communication without defining the final Driver API for JarvisOS.

Included in Phase 3.5:

- `DriverResult` as an internal result for experimental driver-boundary operations.
- `SimulatedDriver` with minimal experimental operations:
  - `is_available(device)`;
  - `read(device, capability_name)`;
  - `apply(device, capability_name, parameters)`.
- Read operations accept only `DeviceCapability` descriptors with `kind == "reading"`.
- Apply operations accept only `DeviceCapability` descriptors with `kind == "action"`.
- Structured internal errors for invalid devices, missing capabilities, kind mismatches, invalid parameters, unavailable driver state, simulated failures, and simulated timeout failures.
- Ephemeral technical state for simulation and tests only.

Stable boundary rules:

- `SimulatedDriver` is an experimental validation artifact.
- It does not define the final Driver API for JarvisOS.
- A `SimulatedDriver` owns simulated communication, not the semantic state of the Device.
- `DriverResult` is internal to the Driver Boundary, is not adapter-facing, does not replace `CapabilityResult`, has no user-facing message, and does not represent official `DeviceState`.
- `DeviceState` remains the only official representation of known device state.

State ownership:

- `SimulatedDriver` may keep in-memory technical simulation data.
- That data is not persisted, is not `DeviceState`, and is not the semantic source of truth.
- `SimulatedDriver` does not mutate `Device.state` or `DeviceRegistry`.

Exit criteria:

- `SimulatedDriver` remains a validation artifact.
- Before any real driver is implemented, JarvisOS must review the Driver Boundary again and decide whether the experimental interface becomes official, changes, or is replaced.

Out of scope for Phase 3.5:

- ABC or general Driver Protocol.
- DriverRegistry.
- Real drivers.
- MQTT, GPIO, ESP32, Zigbee, Tuya, protocols, or hardware.
- Runtime, Planner, CLI, EventBus, or adapter integration.
- Command routing.
- `DriverResult` to `DeviceState` transformation.
- `DriverResult` to `CapabilityResult` transformation.
- Persistence, async, security, or discovery.

## Phase 3.7 Scope

Phase 3.7 introduces `DeviceStateCoordinator` as the minimum boundary for transforming approved `DriverResult` observations into official `DeviceState`.

Purpose:

- keep `DriverResult` technical and experimental;
- keep `DeviceState` as the official known state;
- keep `DeviceRegistry` passive and in-memory;
- prevent drivers from mutating device state directly.

Ownership:

- Driver reports technical observations.
- `DriverResult` carries technical observations.
- `DeviceStateCoordinator` validates and transforms approved observations.
- `DeviceState` represents the official known state.
- `DeviceRegistry` stores that state in memory through `update_state(...)`.

Responsibilities:

- validate `DriverResult`;
- validate the target `DeviceCapability`;
- validate operation as `read` or `apply`;
- filter technical observations;
- build a new `DeviceState`;
- update state only through `DeviceRegistry.update_state(...)`.

`DriverResult` to `DeviceState` relationship:

- `DriverResult` is not `DeviceState`.
- Full `DriverResult` values are never copied into `DeviceState`.
- Technical metadata, technical errors, and sent action parameters are not copied into `DeviceState`.
- A successful action does not imply that state changed.
- Only approved reported observations may update `DeviceState`.

Limitations:

- no DriverRegistry;
- no Runtime integration;
- no command routing;
- no Planner or CLI changes;
- no EventBus integration;
- no persistence or State Store;
- no real drivers, hardware, MQTT, GPIO, ESP32, Zigbee, or Tuya;
- no async or real timeout behavior;
- no `desired_state`, `reported_state`, freshness model, availability model, TTL, or state history.

## Phase 3.9 Scope

Phase 3.9 introduces `DeviceCommandRouter` as the minimum internal Device Platform boundary for routing approved device commands to simulated driver operations.

Implemented flow:

```text
Command -> DeviceCommandRouter -> Device -> DeviceCapability -> SimulatedDriver -> DriverResult -> DeviceStateCoordinator -> DeviceState -> DeviceRegistry
```

Included in Phase 3.9:

- `DeviceExecutionResult` as an internal Device Platform routing result.
- `DeviceCommandRouter` in `jarvis_core/device_routing.py`.
- Routing for `Command(name="device.execute")`.
- Device lookup through `DeviceRegistry`.
- Execution only for formal `DeviceCapability` descriptors.
- `read` operations for capabilities with `kind == "reading"`.
- `apply` operations for capabilities with `kind == "action"`.
- Explicit single-driver injection for the current minimum implementation.
- Delegation to `DeviceStateCoordinator` for official state updates.
- Tests for successful reads, actions, routing errors, driver failures, simulated timeout, state update failure, privacy, and ownership boundaries.

Minimum command contract:

```python
Command(
    name="device.execute",
    args={
        "device_id": "...",
        "capability": "...",
        "operation": "read | apply",
        "parameters": {}
    },
    source="..."
)
```

Ownership:

- `DeviceCommandRouter` coordinates routing.
- `DeviceRegistry` remains passive and does not execute drivers.
- `SimulatedDriver` owns simulated communication only.
- `DriverResult` remains technical and internal to the Device Platform.
- `DeviceStateCoordinator` remains the only boundary that transforms approved observations into `DeviceState`.
- `DeviceState` remains the official known state.

Privacy and safety:

- `DeviceExecutionResult` is internal and not adapter-facing.
- It does not replace `CapabilityResult`.
- It does not contain user-facing messages.
- It does not expose raw `DriverResult`.
- It does not copy complete `Command.args`.
- It does not copy sent parameters, technical metadata, stack traces, or internal driver payloads.
- Legacy string descriptors in `Device.capabilities` are not executable.

Out of scope for Phase 3.9:

- Runtime integration.
- Runtime Capability wrapper.
- Planner changes.
- CLI changes.
- EventBus integration.
- DriverRegistry.
- Device-to-driver binding.
- Driver discovery.
- Real drivers.
- MQTT, GPIO, ESP32, Zigbee, Tuya, protocols, or hardware.
- Persistence or State Store.
- Async runtime.
- Advanced security.
- Automation, dashboard, new adapters, natural language, or AI.

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

## Phase 4.2 Scope

Phase 4.2 introduces `DeviceRuntimeCapability` as the minimum Runtime Capability
bridge from Runtime command execution to the internal Device Platform router.

Included in Phase 4.2:

- `DeviceRuntimeCapability` in `jarvis_core/capabilities/device.py`.
- Stable Runtime Capability name: `device.execute`.
- `DeviceRuntimeCapability.run(command, context) -> CapabilityResult`.
- Constructor injection of `DeviceCommandRouter`.
- Delegation from `DeviceRuntimeCapability` to `DeviceCommandRouter`.
- Conversion from internal `DeviceExecutionResult` to safe `CapabilityResult`.
- Registration of `device.execute` in `CapabilityRegistry`.
- Bootstrap wiring that keeps Runtime, Planner, and CLI behavior unchanged.
- Tests with manually constructed `Command(name="device.execute")` objects.

Boundary rules:

- Runtime does not know `SimulatedDriver`.
- Runtime does not call `DeviceCommandRouter` directly.
- Runtime only executes registered capabilities.
- Driver never receives `Command`.
- `DeviceExecutionResult` is not adapter-facing.
- `DriverResult` never leaves Device Platform.
- `DeviceStateCoordinator` remains the only boundary that updates `DeviceState`.
- Planner and CLI remain outside this phase.
- AVP-001 visible behavior remains unchanged.

Privacy and safety:

- `CapabilityResult` is the only safe output from the device runtime bridge.
- Full `Command.args` are not exposed.
- Sent parameters are not exposed.
- Raw `DriverResult` is not exposed.
- Technical metadata, stack traces, secrets, and raw driver payloads are not exposed.

Out of scope for Phase 4.2:

- Planner integration.
- Natural language.
- CLI device commands.
- Dashboard.
- New adapters.
- DriverRegistry.
- Real drivers.
- MQTT, GPIO, ESP32, Zigbee, Tuya, protocols, or hardware.
- Persistence.
- Async runtime.
- Advanced security.
- Automations.
- AI.
- Discovery.
- Stable real Driver API.

## Phase 4.4 Scope

Phase 4.4 introduces deterministic technical device command input through the
Planner. It lets textual adapters request the existing `device.execute` Runtime
Capability without making CLI parse commands or making Runtime interpret device
grammar.

Canonical syntax:

```text
device read <device_id> <capability>
device apply <device_id> <capability> key=value [key=value ...]
```

Included in Phase 4.4:

- Planner recognizes the canonical `device read` and `device apply` syntax.
- Planner produces `Command(name="device.execute")` with structured args:
  - `device_id`;
  - `capability`;
  - `operation`;
  - `parameters`.
- Runtime passes the adapter `source` into Planner so the resulting Command
  preserves the adapter boundary source.
- CLI remains a non-privileged adapter and continues to call only
  `Runtime.handle_adapter_input(text, source="cli")`.
- Runtime does not parse device grammar.
- Device Platform does not know external text.
- Invalid technical device input is converted to a safe unknown command without
  copying the raw input into `Command.args`.

Privacy and safety:

- Full external input is not logged or persisted by default.
- Full `Command.args` are not exposed to adapters.
- Sent parameters are not exposed in adapter-facing results, lifecycle events,
  or logs.
- Parameter values parsed from text are treated as strings in this phase.
- Full validation against `DeviceCapability.parameters` is future work.

Out of scope for Phase 4.4:

- CLI parsing.
- Planner natural language for devices.
- AI.
- Demo device registration.
- Device Platform changes.
- DriverRegistry.
- Real drivers.
- MQTT, GPIO, ESP32, Zigbee, Tuya, protocols, or hardware.
- Persistence.
- Dashboard.
- New adapters.
- Advanced parameter typing or validation.

## Phase 5.2 Scope

Phase 5.2 introduces read-only device catalog inspection through a Runtime
Capability. It lets textual adapters inspect the current in-memory
`DeviceRegistry` without giving CLI direct access to device internals.

Canonical syntax:

```text
device list
device info <device_id>
device capabilities <device_id>
device state <device_id>
```

Included in Phase 5.2:

- `DeviceCatalogCapability` in `jarvis_core/capabilities/catalog.py`.
- Stable Runtime Capability name: `device.catalog`.
- Planner mapping from catalog syntax to `Command(name="device.catalog")`.
- Read-only queries against `RuntimeContext.device_registry`.
- Safe `CapabilityResult` output for:
  - catalog listing;
  - basic device info;
  - formal and legacy capability inspection;
  - official known `DeviceState`.
- Bootstrap registration of `device.catalog`.
- Tests for catalog behavior, Planner mapping, Runtime integration, privacy, and
  read-only behavior.

Catalog command contract:

```python
Command(
    name="device.catalog",
    args={
        "operation": "list | info | capabilities | state",
        "device_id": "...",
    },
    source="...",
)
```

Read-only and privacy rules:

- Catalog commands do not mutate `DeviceRegistry`, `DeviceState`, drivers, or
  Runtime state.
- `Device.metadata` is not exposed in catalog output.
- Formal `DeviceCapability` descriptors are separated from legacy string
  descriptors.
- Legacy string descriptors are not executable.
- Output crosses to adapters only through safe `CapabilityResult` values.

Out of scope for Phase 5.2:

- Device registration.
- Discovery.
- Demo devices in production bootstrap.
- Hardware or real drivers.
- DriverRegistry.
- DeviceCommandRouter changes.
- Driver or DeviceStateCoordinator participation in catalog queries.
- Persistence.
- Natural language.
- AI.
- Dashboard.
- CLI rendering changes.

## Phase 6.2 Scope

Phase 6.2 introduces the minimum in-memory device lifecycle boundary for
adding and removing devices from the current `DeviceRegistry`.

Canonical syntax:

```text
device add <device_id> name=<name> type=<type>
device remove <device_id>
```

Included in Phase 6.2:

- `DeviceLifecycleCapability` in `jarvis_core/capabilities/lifecycle.py`.
- Stable Runtime Capability name: `device.lifecycle`.
- Planner mapping from lifecycle syntax to `Command(name="device.lifecycle")`.
- `DeviceRegistry.unregister(device_id)` as the registry primitive for removal.
- `add` creates a minimal in-memory `Device` with empty capabilities, default
  unknown state, and empty metadata.
- `remove` deletes an existing in-memory device from the registry.
- Safe `CapabilityResult` output with only minimum operation and device ID data.
- Bootstrap registration of `device.lifecycle`.

Lifecycle command contract:

```python
Command(
    name="device.lifecycle",
    args={
        "operation": "add | remove",
        "device_id": "...",
        "name": "...",
        "type": "...",
    },
    source="...",
)
```

Ownership:

- CLI remains a non-privileged adapter.
- Runtime executes the registered lifecycle capability and does not mutate
  `DeviceRegistry` directly.
- Planner parses deterministic syntax and does not register or remove devices.
- `DeviceLifecycleCapability` owns the mutation boundary.
- `DeviceRegistry` remains passive and in-memory.
- `DeviceCatalogCapability` remains read-only.
- `DeviceCommandRouter`, drivers, and `DeviceStateCoordinator` do not
  participate in lifecycle operations.

Out of scope for Phase 6.2:

- Rename.
- Enable or disable.
- Metadata updates.
- Capability editing.
- Reset state.
- Import or export.
- Persistence.
- Discovery or auto-pairing.
- Real drivers or DriverRegistry.
- MQTT, GPIO, ESP32, Zigbee, Tuya, protocols, or hardware.
- Dashboard.
- Natural language or AI.
- Users, roles, or permissions.

## Phase 7.2 Scope

Phase 7.2 introduces simulated, explicit device discovery as a minimal Runtime
Capability. Discovery only detects temporary candidates. It does not register,
pair, authenticate, trust, authorize, connect, or execute devices.

Canonical syntax:

```text
device discover
```

Included in Phase 7.2:

- `DiscoveryCandidate` as an immutable temporary candidate descriptor.
- `SimulatedDiscoveryProvider` as an experimental deterministic provider.
- `DeviceDiscoveryCapability` in `jarvis_core/capabilities/discovery.py`.
- Stable Runtime Capability name: `device.discovery`.
- Planner mapping from `device discover` to `Command(name="device.discovery")`.
- Bootstrap registration of `device.discovery`.
- Safe `CapabilityResult` output containing only sanitized candidate fields.

Discovery command contract:

```python
Command(
    name="device.discovery",
    args={
        "operation": "scan",
    },
    source="...",
)
```

Returned candidate data is limited to:

- `candidate_id`
- `display_name`
- `transport`
- `manufacturer`
- `model`
- `capability_hints`

Discovery privacy and ownership:

- `candidate_id` is opaque, temporary, and not a trust identity.
- `capability_hints` are descriptive only and not executable.
- Candidates are not stored in `DeviceRegistry`.
- Discovery does not call lifecycle, catalog, routing, drivers, EventBus, or
  persistence.
- CLI remains a non-privileged adapter and only displays
  `CapabilityResult.message`.

Out of scope for Phase 7.2:

- Background scanning.
- Pairing, trust, authentication, authorization, or registration.
- Automatic lifecycle operations.
- `DiscoverySession`.
- Persistent candidates, State Store, history, or Event Sourcing.
- Hardware discovery, BLE, Wi-Fi, USB, mDNS, SSDP, MQTT, Zigbee, or Tuya.
- DriverRegistry or DiscoveryProviderRegistry.
- Dashboard.
- Natural language, AI, LLM, or scenario engine.

## Phase 7.4 Scope

Phase 7.4 introduces the minimum simulated onboarding path from the latest
explicit discovery result to a registered in-memory Device.

Canonical syntax:

```text
device discover
device onboard <candidate_id> as <device_id>
```

Included in Phase 7.4:

- `DiscoveryCandidateStore` as an experimental in-memory store for candidates
  from the latest explicit discovery call.
- `DeviceDiscoveryCapability` can replace the store contents after a successful
  explicit discovery request.
- `SimulatedOnboardingProvider` as an experimental deterministic provider for
  simulated pairing, authentication, and ephemeral trust decisions.
- `DeviceRegistrationProposal` as an internal sanitized registration proposal.
- `DeviceLifecycleRegistrar` as an internal lifecycle registration primitive.
- `DeviceLifecycleCapability` uses the registration primitive for `add`.
- `DeviceOnboardingCapability` registered as `device.onboarding`.
- Planner mapping from `device onboard <candidate_id> as <device_id>` to
  `Command(name="device.onboarding")`.
- Bootstrap wiring keeps Runtime as capability executor and avoids adding
  onboarding services to `RuntimeContext`.

Onboarding command contract:

```python
Command(
    name="device.onboarding",
    args={
        "operation": "approve",
        "candidate_id": "...",
        "device_id": "...",
    },
    source="...",
)
```

Ownership and privacy:

- Onboarding is explicit and uses candidates from the latest discovery result.
- Pairing, authentication, and trust are simulated.
- Trust is ephemeral and is not stored in `DeviceState`.
- `candidate_id` is temporary and is not `Device.id`.
- The resulting Device uses the user-provided `device_id`.
- The registered Device starts with no capabilities, unknown state, and empty
  metadata.
- Capability hints remain descriptive and are not converted into executable
  capabilities.
- Device registration remains owned by the Device Lifecycle Boundary through
  the internal lifecycle registration primitive.
- Onboarding does not expose full `Command.args`, raw pairing/authentication
  details, trust details, provider internals, physical identifiers, secrets, or
  stack traces.

Candidate consumption policy:

- Successful onboarding removes the candidate from the in-memory store.
- Pairing, authentication, trust, duplicate-device, and registration failures
  keep the candidate available for deterministic retry.
- A new `device discover` call replaces previous candidates.
- An empty discovery result clears the store.

Out of scope for Phase 7.4:

- Real hardware.
- BLE, Wi-Fi provisioning, USB enrollment, MQTT, Zigbee, or Tuya.
- Cryptography, certificates, PKI, credentials, or persistent trust.
- Authorization engine, users, roles, or remote administration.
- Background onboarding, automatic prompts, automatic pairing, or automatic
  registration.
- Reject lists, durable sessions, TTL, or DiscoverySession.
- DriverRegistry, provider registry, State Store, or persistence.
- Dashboard, voice, natural language, AI, LLM, fuzzy logic, neural networks, or
  scenario engine.

## Project Rule

Architecture is frozen until code forces a change. Notion documents decisions; GitHub validates them.

## Phase 8.3 Scope

Phase 8.3 introduces the first experimental real-driver transport boundary for
JarvisOS: synchronous HTTP local.

This phase validates a real communication path while keeping the default
AVP-001 runtime safe, in-memory, and free of production hardware assumptions.

Included in Phase 8.3:

- `HttpDeviceBinding` as explicit per-device HTTP reachability configuration.
- `HttpDeviceBindingStore` as an experimental in-memory binding store.
- `HttpDeviceDriver` as an experimental synchronous HTTP local driver.
- An injectable HTTP JSON transport so tests can run without network or
  hardware.
- Fixed protocol paths:
  - `POST /device/read`
  - `POST /device/apply`
- DriverResult error normalization for local HTTP configuration, connection,
  timeout, protocol, invalid response, authentication, and unsupported
  operation failures.
- A small bootstrap/composition module that preserves the default runtime while
  allowing explicit HTTP test/runtime construction.
- Tests for bindings, HTTP transport behavior, driver behavior, routing,
  bootstrap behavior, privacy, and regressions.

Example vertical slice commands:

```text
device apply lamp_1 power.switch state=true
device read lamp_1 status.read
device state lamp_1
```

The default runtime does not create `lamp_1`, does not register a real HTTP
binding, and does not contact the network. HTTP devices and bindings must be
created explicitly by tests or by a future approved composition path.

HTTP protocol shape:

```text
POST /device/read
```

```json
{
  "capability": "status.read"
}
```

```text
POST /device/apply
```

```json
{
  "capability": "power.switch",
  "parameters": {
    "state": "true"
  }
}
```

Successful endpoint responses use:

```json
{
  "success": true,
  "observations": {
    "power": true
  }
}
```

Failure endpoint responses use a normalized internal error:

```json
{
  "success": false,
  "error": "operation_not_supported"
}
```

Security and privacy limits:

- Experimental local-network transport only.
- Not production secure.
- Do not expose to the public internet.
- No authentication.
- No TLS.
- No credentials, tokens, certificates, or secrets store.
- No persistence or config files.
- No async, background loop, polling, subscriptions, reconnect manager, or
  automatic retries.
- No DriverRegistry.
- No HTTP discovery, mDNS, SSDP, auto-registration, or auto-onboarding.
- No required hardware in CI.
- ESP32 hardware validation is optional and manual.
- Full URLs, raw request payloads, raw responses, headers, exceptions, and stack
  traces are not adapter-facing output.

Parameter limitation:

- The deterministic Planner still parses command parameters as strings.
- `state=true` is sent to the HTTP endpoint as `"true"`.
- General type coercion and complete validation against
  `DeviceCapability.parameters` remain future work.
