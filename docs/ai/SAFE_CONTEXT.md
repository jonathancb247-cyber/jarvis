# AI Safe Context

Status: Experimental / Deterministic Fake Only

`AISafeContext` is a detached semantic snapshot for AI planning. It is built
from safe projections and does not expose live Runtime objects.

## Allowed

Safe context may contain:

- current user request;
- bounded session metadata;
- device ID;
- display name;
- device type;
- formal capabilities;
- safe parameter descriptors;
- safe semantic `DeviceState`;
- structured command grammar;
- confirmation and plan limits.

## Forbidden

Safe context must not contain:

- `RuntimeContext`;
- `EventBus`;
- live registries;
- binding stores;
- drivers;
- `DriverResult`;
- `DeviceExecutionResult`;
- raw `CapabilityResult.data`;
- raw configuration;
- State Store paths;
- URLs;
- IP addresses;
- ports;
- headers;
- credentials;
- tokens;
- certificates;
- secrets;
- discovery candidates;
- pairing data;
- trust internals;
- exceptions;
- stack traces;
- full diagnostics.

## Device Projection

`AISafeDevice` contains only:

- device ID;
- display name;
- device type;
- formal capabilities;
- safe state.

It excludes metadata, legacy capability strings, bindings, addresses, IP or MAC
values, protocol details, raw hardware identity, and credentials.

Device display names are untrusted data. They must not become instructions.

## State Projection

`AISafeDeviceState` contains:

- status;
- allowlisted primitive semantic properties;
- `updated_at`, if safe.

`stale` is exposed explicitly and does not imply current hardware availability.

The current implementation allows primitive semantic values only and excludes
technical observations, raw payloads, transport errors, request history, and
diagnostics.
