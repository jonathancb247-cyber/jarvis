# Driver Development

Status: Current Architecture / Experimental Driver Contract

JarvisOS drivers translate semantic device operations into technical communication.

## Provisional Contract

```python
read(device, capability_name) -> DriverResult
apply(device, capability_name, parameters) -> DriverResult
```

This is an experimental structural contract. JarvisOS does not yet expose a stable driver SDK, ABC, Protocol, plugin API, or DriverRegistry.

## Required Driver Rules

A driver:

- Does not receive `Command`.
- Does not return `CapabilityResult`.
- Does not mutate `DeviceState`.
- Does not call `DeviceRegistry`.
- Does not register devices.
- Does not interpret natural language.
- Does not persist state.
- Produces internal technical results.

## DriverResult

```python
DriverResult(
    success: bool,
    observations: dict,
    error: str | None,
)
```

`observations` may contain semantic readings such as:

```python
{"power": True}
```

It must not contain raw protocol payloads, stack traces, secrets, URLs, headers, or credentials.

## Execution Flow

```text
DeviceCommandRouter
-> Driver
-> DriverResult
-> DeviceStateCoordinator
-> DeviceState
```

## Internal Error Codes

- `configuration_invalid`
- `driver_unavailable`
- `connection_failed`
- `request_timeout`
- `protocol_error`
- `invalid_response`
- `authentication_failed`
- `operation_not_supported`

These are internal normalized codes. Adapter-facing messages must remain safe.

## Testing Expectations

Driver tests should cover:

- Fake transport.
- Success.
- Timeout.
- Unavailable transport.
- Malformed response.
- Privacy boundaries.
- No raw payload leakage.
- No hardware requirement in CI.

