# MQTT Driver

Status: Current / Experimental Request-Response Driver

JarvisOS includes an experimental MQTT driver boundary for CI-safe request/response validation. It is not a broker deployment guide and does not require Mosquitto, ESP32 hardware, credentials, TLS, subscriptions, retained messages or asynchronous Runtime state events.

## Boundary

The MQTT driver implements the same internal driver shape used by the existing HTTP driver:

```python
read(device, capability_name) -> DriverResult
apply(device, capability_name, parameters) -> DriverResult
```

It receives semantic `Device` and capability inputs from the existing `DeviceCommandRouter`. It does not receive `Command`, call Planner, call Runtime, mutate `DeviceRegistry`, mutate `DeviceState`, write State Store, perform confirmation or retry mutations.

## Binding Model

MQTT reachability is profile-owned binding data:

```json
{
  "transport": "mqtt",
  "device_id": "temperature_room",
  "request_topic": "jarvis/devices/temperature_room/request",
  "response_topic": "jarvis/devices/temperature_room/response",
  "timeout_seconds": 2.0,
  "allowed_capabilities": ["temperature.read"],
  "allowed_response_keys": ["temperature"]
}
```

Topics are transport-only. They are not exposed through `DeviceCapability`, Runtime API, Dashboard, `AISafeContext` or AI providers.

Bindings reject:

- empty topics;
- wildcard topics containing `#` or `+`;
- control characters;
- duplicate device bindings;
- orphan bindings;
- credentials or arbitrary metadata.

Existing HTTP profiles continue to work without adding `mqtt_bindings`. When present, `mqtt_bindings` is optional profile data and is not a migration requirement for HTTP-only profiles.

## Request Envelope

The driver publishes a bounded JSON request:

```json
{
  "request_id": "bounded-correlation-id",
  "device_id": "temperature_room",
  "capability": "temperature.read",
  "operation": "read",
  "parameters": {}
}
```

The envelope does not include URLs, IPs, credentials, AI content, Dashboard state or arbitrary metadata.

## Response Envelope

The driver accepts a strict JSON response:

```json
{
  "request_id": "bounded-correlation-id",
  "ok": true,
  "semantic": {
    "temperature": 22.5
  },
  "error": null
}
```

Failure responses use the same root fields:

```json
{
  "request_id": "bounded-correlation-id",
  "ok": false,
  "semantic": {},
  "error": "request_timeout"
}
```

The request ID must match exactly. Unknown root fields, malformed JSON, oversized responses and semantic keys not listed in the binding are rejected.

## Correlation

Each request uses one bounded correlation ID. A mismatched response cannot satisfy the request. Late responses after timeout do not update state. Duplicate responses are not persisted by the driver. The driver keeps no persistent correlation state after a call returns.

## State Behavior

Successful MQTT observations feed the existing `DeviceStateCoordinator` exactly like HTTP observations. Failed requests do not create false `known` state. Broker connectivity alone does not imply device availability. Retained-message ingestion and asynchronous state updates are not implemented.

## HTTP Coexistence

HTTP remains valid and supported. Profile composition can route one logical device to HTTP and another logical device to MQTT without Runtime branching on transport. Runtime, Planner, API, Dashboard and AI providers remain transport-neutral.

No AI provider is invoked by MQTT driver execution.

## Testing

CI uses fake MQTT clients only. Tests cover request envelope generation, response validation, correlation mismatch, duplicate/late behavior, timeout, broker unavailable, publish failure, malformed response, oversized response, invalid topic config, shutdown, HTTP+MQTT coexistence, no retry and no direct Registry or State Store mutation by the driver.

## Not Implemented

Phase 12.2 does not implement:

- Mosquitto setup;
- real broker calls;
- ESP32 firmware;
- MQTT subscriptions;
- retained messages;
- LWT or availability topics;
- background state updates;
- TLS/authentication;
- broker credentials;
- Dashboard MQTT UI;
- MQTT API routes;
- AI/provider changes.

Phase 12.3 remains blocked until explicitly opened for real broker validation.
