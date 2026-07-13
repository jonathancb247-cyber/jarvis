# Capability Model

Status: Current / Implemented Domain Model

`DeviceCapability` describes what a device supports. It does not describe how JarvisOS reaches the device.

## Runtime Capability vs DeviceCapability

Runtime Capability:

- Registered in `CapabilityRegistry`.
- Executed by `Runtime`.
- Returns `CapabilityResult`.
- Examples: `device.discovery`, `device.lifecycle`, `device.execute`.

DeviceCapability:

- Stored on a `Device`.
- Describes semantic device behavior.
- Does not execute by itself.
- Does not return `CapabilityResult`.
- Does not contain URLs, topics, ports, GPIO numbers, credentials, or driver config.

## Kinds

`kind = "action"` describes an operation that changes something.

Examples:

- `power.switch`
- `brightness.set`
- `relay.set`
- `position.set`
- `gpio.write`

`kind = "reading"` describes an operation that reads state or observations.

Examples:

- `status.read`
- `temperature.read`
- `humidity.read`
- `gpio.read`
- `sensor.read`

## Parameters

Parameters are declarative descriptors. They explain expected inputs; they are not transport payload mappings.

Example:

```python
DeviceCapability(
    name="power.switch",
    kind="action",
    parameters={
        "state": {
            "type": "string",
            "required": True,
        }
    },
)
```

## Naming Rule

Capabilities describe intent and semantics, not implementation details.

Correct:

```text
power.switch
```

Incorrect as a public capability:

```text
esp32_gpio2_write
```

## Naming Guidelines

- Use lowercase names.
- Use semantic namespaces.
- Use a clear verb or reading name.
- Keep names transport-agnostic.
- Keep names hardware-agnostic.

## Constraints And Availability

`constraints`, `availability_policy`, and `metadata` are declarative fields. They must not be used to store transport configuration, credentials, URLs, topics, GPIO pins, or driver bindings.

## Legacy Compatibility

`Device.capabilities` still accepts legacy strings for compatibility. Legacy strings are not executable and should not be used for new device integrations.

JarvisOS does not yet define a global stable catalog of all possible capabilities.

